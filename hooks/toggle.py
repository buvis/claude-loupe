#!/usr/bin/env python3
"""Flip the per-project loupe enabled flag for /loupe-toggle.

Resolves the effective ``enabled`` value the hooks would see (global
config overridden by the project layer), writes the opposite into the
project override at ``.claude/loupe.json`` - preserving any other keys
the file carries - and reports the new state. A command helper, not a
hook: errors surface loudly instead of failing open.

Lives in hooks/ beside the ``loupe`` package so the engine imports
resolve from the script directory, exactly like the hook entry points.
"""

import json
import os
import sys


def main() -> int:
    from loupe.config import load_config, project_config_path
    from loupe.project import project_root

    root = project_root(os.getcwd())
    effective = load_config(root)["enabled"]
    target = project_config_path(root)

    try:
        existing = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        existing = {}
    if not isinstance(existing, dict):
        existing = {}

    updated = {**existing, "enabled": not effective}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")

    verdict = "enabled" if updated["enabled"] else "disabled"
    print(f"loupe is now {verdict} for {root}")
    print(f"(project override written to {target})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
