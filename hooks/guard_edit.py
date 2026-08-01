#!/usr/bin/env python3
"""PreToolUse read guard for Write|Edit|MultiEdit.

Blocks (or warns about) an edit whose target lines were never read this
session, on top of Claude Code's own staleness guards. Behavior follows
the ``read_guard`` config key: ``warn`` (default) prints to stderr and
allows, ``block`` exits 2, ``off`` skips entirely.

Exemptions, in the order they are checked:

- ``read_guard: off``.
- Prose files (markdown, plain text, logs) - appending a line to a
  changelog is not the failure mode this guard exists for.
- Creating a new file: there is nothing to have read.
- A one-shot ``/loupe-allow-edit <path>`` override, which this hook
  consumes so it covers exactly one edit.

The default is ``warn`` on purpose. The agent legitimately learns file
contents through Grep output, subagent returns, and prior-session
context, none of which pass through the Read hook, so ``block``
false-positives on valid edits. Projects opt into ``block``.

Parsing is defensive (unknown or missing fields exit 0) and the whole
hook fails open (exit 0) on internal errors - a guard that cannot decide
must never be the thing that stops a session.
"""

import os
import sys

import gate

_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit"})

# Prose, not code: the guard protects against clobbering logic the agent
# has not seen, and these formats are appended to routinely.
_EXEMPT_SUFFIXES = frozenset({".md", ".markdown", ".txt", ".log", ".rst"})


def main() -> int:
    try:
        payload = gate.read_hook_json()
        if payload is None:
            return 0
        tool_name = payload.get("tool_name")
        if tool_name not in _WRITE_TOOLS:
            return 0
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0
        path = tool_input.get("file_path")
        if not isinstance(path, str) or not path:
            return 0
        cwd = str(payload.get("cwd") or "") or os.getcwd()
        if not gate.loupe_enabled(cwd):
            return 0
        return _guard(cwd, tool_name, tool_input, path)
    except Exception:  # fail open: never break the user's session
        return 0


def _guard(cwd: str, tool_name: str, tool_input: dict, path: str) -> int:
    from loupe.config import load_config
    from loupe.project import project_hash, project_root
    from loupe.readcoverage import is_covered
    from loupe.state import load_state

    mode = load_config(project_root(cwd))["read_guard"]
    if mode == "off":
        return 0
    if os.path.splitext(path)[1].lower() in _EXEMPT_SUFFIXES:
        return 0

    target = os.path.abspath(path)
    if not os.path.isfile(target):
        return 0  # creating a new file: nothing to have read

    spans = _target_spans(tool_name, tool_input, target)
    if not spans:
        return 0  # cannot resolve a target: never guess a block

    project = project_hash(cwd)
    state = load_state(project)
    if _spend_override(project, state, target):
        return 0

    ranges = state["runtime"]["read_ranges"].get(target, [])
    uncovered = [span for span in spans if not is_covered(ranges, *span)]
    if not uncovered:
        return 0
    return _verdict(mode, path, uncovered)


def _verdict(mode: str, path: str, uncovered) -> int:
    """Emit the guard's message and return the hook exit code."""
    rendered = ", ".join(f"{start}-{end}" for start, end in uncovered)
    verb = "blocked" if mode == "block" else "warning"
    detail = (
        f"loupe read guard ({verb}): {path} lines {rendered} were not read "
        "this session."
    )
    if mode == "block":
        print(
            f"{detail} Read the file (or that range) first, or run "
            f"/loupe-allow-edit {path} to permit this one edit.",
            file=sys.stderr,
        )
        return 2
    print(
        f"{detail} Proceeding - set read_guard to 'block' to stop these.",
        file=sys.stderr,
    )
    return 0


def _spend_override(project: str, state: dict, target: str) -> bool:
    """Consume a one-shot ``/loupe-allow-edit`` override for ``target``."""
    from loupe.state import save_state

    allowed = state["runtime"]["allow_edit"]
    if target not in allowed:
        return False
    save_state(
        project,
        {
            **state,
            "runtime": {
                **state["runtime"],
                "allow_edit": [p for p in allowed if p != target],
            },
        },
    )
    return True


def _target_spans(tool_name: str, tool_input: dict, target: str) -> list:
    """Inclusive line spans an edit will touch; ``[]`` when unresolvable."""
    try:
        lines = _read_lines(target)
    except OSError:
        return []
    if tool_name == "Write":
        return [(1, len(lines))] if lines else []
    if tool_name == "Edit":
        span = _span_of(lines, tool_input.get("old_string"))
        return [span] if span else []
    edits = tool_input.get("edits")
    if not isinstance(edits, list):
        return []
    spans = []
    for edit in edits:
        if not isinstance(edit, dict):
            continue
        span = _span_of(lines, edit.get("old_string"))
        if span:
            spans.append(span)
    return spans


def _read_lines(target: str) -> list:
    with open(target, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read().splitlines()


def _span_of(lines: list, old_string) -> tuple | None:
    """Where ``old_string`` sits in ``lines``, as an inclusive span.

    Matches the needle's lines against the haystack. Returns ``None``
    when the needle is empty or absent - in either case the guard defers
    rather than blocking on a guess.
    """
    if not isinstance(old_string, str) or not old_string:
        return None
    needle = old_string.splitlines()
    if not needle:
        return None
    for index in range(len(lines) - len(needle) + 1):
        if lines[index : index + len(needle)] == needle:
            return (index + 1, index + len(needle))
    return None


if __name__ == "__main__":
    sys.exit(main())
