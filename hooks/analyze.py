#!/usr/bin/env python3
"""PostToolUse analysis for Write|Edit|MultiEdit: ast-grep + fast linter.

Runs the packaged rule pack and the language's fast linter on the
edited file and classifies the findings. Blocking findings (stub and
security categories) exit 2 with a concise stderr naming file, rule,
and line. PostToolUse exit 2 cannot undo the write - the edit has
landed and Claude Code feeds the stderr back to the model as
must-fix feedback, so the message asks for a fix rather than
claiming a block. Advisory findings print inline and exit 0. Every analyzed
file is queued for the Stop-time autofix/format pass - unless
``immediate_fix`` is on and nothing blocks, in which case the fix and
format run inline instead. Session findings accumulate in runtime
state for ``/loupe-report``.

Parsing is defensive (unknown or missing fields exit 0) and the whole
hook fails open (exit 0) on internal errors.
"""

import os
import sys

import gate

_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit"})
_MAX_REPORTED = 10


def main() -> int:
    try:
        payload = gate.read_hook_json()
        if payload is None:
            return 0
        if payload.get("tool_name") not in _WRITE_TOOLS:
            return 0
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0
        file_path = tool_input.get("file_path")
        if not isinstance(file_path, str) or not os.path.isfile(file_path):
            return 0
        cwd = str(payload.get("cwd") or "") or os.getcwd()
        if not gate.loupe_enabled(cwd):
            return 0
        return _analyze(file_path, cwd)
    except Exception:  # fail open: never break the user's session
        return 0


def _analyze(file_path: str, cwd: str) -> int:
    from dataclasses import asdict

    from loupe.astgrep import run_astgrep
    from loupe.config import load_config
    from loupe.findings import classify
    from loupe.languages import detect_language
    from loupe.linters import run_linter
    from loupe.project import project_hash, project_root
    from loupe.state import load_state, save_state

    language = detect_language(file_path)
    if language == "unknown":
        return 0

    config = load_config(project_root(cwd))
    project = project_hash(cwd)
    state = load_state(project)

    findings = list(run_astgrep(file_path, language))
    linted, state = run_linter(file_path, language, config, state)
    findings.extend(linted)
    blocking, advisory = classify(findings)

    fix_now = bool(config.get("immediate_fix")) and not blocking
    runtime = dict(state["runtime"])
    runtime["findings"] = [
        *runtime["findings"],
        *(asdict(finding) for finding in findings),
    ]
    if not fix_now and file_path not in runtime["format_queue"]:
        runtime["format_queue"] = [*runtime["format_queue"], file_path]
    save_state(project, {**state, "runtime": runtime})

    if fix_now:
        _fix_inline(file_path, language, config)
    if blocking:
        _report(blocking, file_path, "fix before moving on", sys.stderr)
        return 2
    if advisory:
        _report(advisory, file_path, "advisory findings", sys.stdout)
    return 0


def _fix_inline(file_path: str, language: str, config: dict) -> None:
    from loupe.formatters import apply_autofix, apply_formatters, format_summary

    results = [
        apply_autofix(file_path, language, config),
        apply_formatters(file_path, config),
    ]
    # Mirror the Stop summary: steps that skipped are not worth a line.
    worked = [result for result in results if result["status"] != "skipped"]
    summary = format_summary(worked)
    if summary:
        print(f"loupe immediate fix:\n{summary}")


def _report(findings, file_path: str, heading: str, stream) -> None:
    lines = [f"loupe: {heading} - {file_path}:"]
    for finding in findings[:_MAX_REPORTED]:
        location = f"line {finding.line}" if finding.line else "file"
        lines.append(f"  {location} [{finding.category}] {finding.message}")
    overflow = len(findings) - _MAX_REPORTED
    if overflow > 0:
        lines.append(f"  ... and {overflow} more")
    print("\n".join(lines), file=stream)


if __name__ == "__main__":
    sys.exit(main())
