#!/usr/bin/env python3
"""PostToolUse recorder for Read: remember which lines the agent has seen.

Merges the read's line range into the session's per-file coverage map,
which ``guard_edit.py`` later checks an edit against. Observation only -
this hook never blocks anything and always exits 0.

Parsing is defensive (unknown or missing fields exit 0) and the whole
hook fails open (exit 0) on internal errors.
"""

import os
import sys

import gate


def main() -> int:
    try:
        payload = gate.read_hook_json()
        if payload is None:
            return 0
        if payload.get("tool_name") != "Read":
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
        _record(cwd, path, tool_input.get("offset"), tool_input.get("limit"))
    except Exception:  # fail open: never break the user's session
        return 0
    return 0


def _record(cwd: str, path: str, offset, limit) -> None:
    from loupe.project import project_hash
    from loupe.readcoverage import merge_range, read_range
    from loupe.state import load_state, save_state

    project = project_hash(cwd)
    state = load_state(project)
    ranges = state["runtime"]["read_ranges"]
    key = os.path.abspath(path)
    existing = ranges.get(key, [])
    start, end = read_range(offset, limit)
    save_state(
        project,
        {
            **state,
            "runtime": {
                **state["runtime"],
                "read_ranges": {**ranges, key: merge_range(existing, start, end)},
            },
        },
    )


if __name__ == "__main__":
    sys.exit(main())
