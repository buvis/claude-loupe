#!/usr/bin/env python3
"""Stop entry point: deferred autofix/format, slow linters, tool nudges.

Drains the runtime format queue exactly once per turn: every queued
file gets the safe autofixer plus the config-gated formatter, and each
queued language named in ``SLOW_LINTERS`` (clippy for Rust,
svelte-check for Svelte - too slow for the per-edit budget) gets one
advisory run. Missing-tool nudges recorded during the session print
here, once per project ever, tracked in the persistent
``nudge_reported`` log.

Idempotence: the state is saved with the queue cleared and the nudges
marked as reported *before* the work runs, so a re-fired Stop finds
nothing to claim and is a no-op. Always exits 0 - a nonzero exit from a
Stop hook would force the agent to continue, which analysis feedback
must never do. When there is nothing to report, nothing is printed.
"""

import os
import sys

import gate

SLOW_LINTER_TIMEOUT_SECONDS = 120
_OUTPUT_TAIL_LINES = 30


def main() -> int:
    try:
        payload = gate.read_hook_json()
        if payload is None:
            return 0
        cwd = str(payload.get("cwd") or "") or os.getcwd()
        if not gate.loupe_enabled(cwd):
            return 0
        _finish_turn(cwd)
    except Exception:  # fail open: never break the user's session
        return 0
    return 0


def _finish_turn(cwd: str) -> None:
    from loupe.config import load_config
    from loupe.project import project_hash, project_root
    from loupe.state import load_state, save_state

    project = project_hash(cwd)
    state = load_state(project)
    queue = [
        path for path in state["runtime"]["format_queue"] if isinstance(path, str)
    ]
    pending_nudges = [
        tool
        for tool in state["persistent"]["nudged"]
        if tool not in state["persistent"]["nudge_reported"]
    ]
    if not queue and not pending_nudges:
        return

    # Claim the work before doing it: a re-fired Stop sees an empty
    # queue and fully reported nudges, making its run a no-op.
    state = {
        **state,
        "runtime": {**state["runtime"], "format_queue": []},
        "persistent": {
            **state["persistent"],
            "nudge_reported": [
                *state["persistent"]["nudge_reported"],
                *pending_nudges,
            ],
        },
    }
    save_state(project, state)

    config = load_config(project_root(cwd))
    sections = []
    if queue:
        sections.extend(_fix_and_format(queue, config))
        slow_lines, state = _slow_lint(queue, project, state, cwd)
        sections.extend(slow_lines)
    sections.extend(
        f"nudge: '{tool}' was needed but not found - install it to enable "
        "its checks (this notice fires once per project)"
        for tool in pending_nudges
    )
    if sections:
        print("loupe stop summary:")
        print("\n".join(sections))


def _fix_and_format(queue, config) -> list:
    from loupe.formatters import apply_autofix, apply_formatters, format_summary
    from loupe.languages import detect_language

    results = []
    for path in queue:
        if not os.path.isfile(path):
            continue
        results.append(apply_autofix(path, detect_language(path), config))
        results.append(apply_formatters(path, config))
    # Only files where a step actually ran make the summary: languages
    # loupe cannot fix or format (markdown, shell, ...) queue silently,
    # and an all-skipped line every turn would be noise. Failures stay.
    worked = [result for result in results if result["status"] != "skipped"]
    summary = format_summary(worked)
    return summary.splitlines() if summary else []


def _slow_lint(queue, project: str, state: dict, cwd: str):
    """One advisory run per queued SLOW_LINTERS language; nudge when absent."""
    import subprocess

    from loupe.languages import detect_language
    from loupe.linters import SLOW_LINTERS
    from loupe.tools import record_nudge

    by_language = {}
    for path in queue:
        by_language.setdefault(detect_language(path), []).append(path)

    lines = []
    for language, tool in SLOW_LINTERS.items():
        paths = by_language.get(language)
        if not paths:
            continue
        command, workdir = _slow_command(tool, paths[0], cwd)
        if command is None:
            state, _ = record_nudge(state, project, tool)
            continue
        if workdir is None:
            continue  # e.g. a Rust file outside any cargo crate
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=SLOW_LINTER_TIMEOUT_SECONDS,
                cwd=workdir,
            )
        except (OSError, subprocess.TimeoutExpired):
            lines.append(f"slow lint ({tool}): did not complete")
            continue
        output = (result.stdout + result.stderr).strip()
        if output:
            lines.append(f"slow lint ({tool}), advisory:")
            lines.extend(
                f"  {line}" for line in output.splitlines()[-_OUTPUT_TAIL_LINES:]
            )
        else:
            lines.append(f"slow lint ({tool}): clean")
    return lines, state


def _slow_command(tool: str, sample_path: str, cwd: str):
    """(command, workdir): command None = tool absent, workdir None = skip."""
    from loupe.project import project_root
    from loupe.tools import resolve_tool

    if tool == "clippy":
        cargo = resolve_tool("cargo")
        if cargo is None:
            return None, None
        return (
            [cargo, "clippy", "--quiet", "--message-format=short"],
            _nearest_cargo_root(sample_path),
        )
    binary = resolve_tool(tool)
    if binary is None:
        return None, None
    return [binary, "--output", "human"], str(project_root(cwd))


def _nearest_cargo_root(path: str):
    """Closest ancestor with a Cargo.toml; ``None`` outside any crate."""
    from pathlib import Path

    start = Path(path).resolve().parent
    for candidate in (start, *start.parents):
        if (candidate / "Cargo.toml").is_file():
            return str(candidate)
    return None


if __name__ == "__main__":
    sys.exit(main())
