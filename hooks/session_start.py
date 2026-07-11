#!/usr/bin/env python3
"""SessionStart bootstrap: reset the per-session runtime state block.

Thin entry point per the PRD's hook-entrypoints module: parse the hook
JSON defensively, short-circuit while still import-light when loupe is
disabled, and fail open (exit 0) on any internal error - loupe must
never break the session it watches.

A ``compact`` SessionStart fires mid-conversation, so it keeps the
runtime block (resetting there would drop the turn's format queue);
every other source (``startup``, ``clear``, ``resume``) begins a fresh
session and resets. Prints nothing: SessionStart stdout is injected
into the model context.
"""

import os
import sys

import gate


def main() -> int:
    try:
        payload = gate.read_hook_json()
        if payload is None:
            return 0
        if payload.get("source") == "compact":
            return 0
        cwd = str(payload.get("cwd") or "") or os.getcwd()
        if not gate.loupe_enabled(cwd):
            return 0
        _bootstrap(cwd)
    except Exception:  # fail open: never break the user's session
        return 0
    return 0


def _bootstrap(cwd: str) -> None:
    from loupe.project import project_hash
    from loupe.state import load_state, reset_runtime, save_state

    project = project_hash(cwd)
    save_state(project, reset_runtime(load_state(project)))


if __name__ == "__main__":
    sys.exit(main())
