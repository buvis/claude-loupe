#!/usr/bin/env python3
"""Self-diagnosis for /loupe-check-health.

``report.py`` reports the project's state; this reports whether loupe
itself is wired correctly. Each check prints ``ok`` or ``FAIL`` with the
reason, and the exit code is nonzero when any check fails, so the
command can be trusted as a gate rather than read as prose.

Checks:

- every engine module imports (a syntax error in one would otherwise
  only surface as hooks silently failing open)
- every entry point named in ``hooks.json`` exists on disk
- the ast-grep rule pack is present and its binary resolves
- the state file is readable and its directory writable

A command helper, not a hook: it does not fail open. Reporting that
everything is fine when it is not is the one thing a health check must
never do.
"""

import json
import os
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = HOOKS_DIR.parent

ENGINE_MODULES = (
    "astgrep",
    "config",
    "findings",
    "formatters",
    "languages",
    "linters",
    "project",
    "readcoverage",
    "secrets",
    "state",
    "tdi",
    "tools",
)


def main() -> int:
    results = []
    print("loupe health check")

    print("\nengine modules:")
    results.append(_check_engine())

    print("\nhook entry points:")
    results.append(_check_entry_points())

    print("\nrule pack:")
    results.append(_check_rule_pack())

    print("\nstate:")
    results.append(_check_state())

    failed = [name for name, ok in results if not ok]
    print()
    if failed:
        print(f"FAIL: {', '.join(failed)}")
        return 1
    print("ok: loupe is wired correctly")
    return 0


def _check_engine() -> tuple:
    import importlib

    broken = []
    for name in ENGINE_MODULES:
        try:
            importlib.import_module(f"loupe.{name}")
        except Exception as err:  # any import failure is a real defect
            broken.append(f"{name} ({err})")
    if broken:
        for entry in broken:
            print(f"  FAIL {entry}")
        return ("engine modules", False)
    print(f"  ok all {len(ENGINE_MODULES)} modules import")
    return ("engine modules", True)


def _check_entry_points() -> tuple:
    manifest = HOOKS_DIR / "hooks.json"
    try:
        registered = json.loads(manifest.read_text(encoding="utf-8"))["hooks"]
    except (OSError, ValueError, KeyError, TypeError) as err:
        print(f"  FAIL hooks.json unreadable ({err})")
        return ("hooks.json", False)

    missing = []
    count = 0
    for event, blocks in registered.items():
        for block in blocks:
            for entry in block.get("hooks", []):
                count += 1
                script = _script_of(entry.get("command", ""))
                if script and not (HOOKS_DIR / script).is_file():
                    missing.append(f"{event}: {script}")
    for entry in missing:
        print(f"  FAIL missing script {entry}")
    if missing:
        return ("hook entry points", False)
    print(f"  ok all {count} registered entry points exist")
    return ("hook entry points", True)


def _script_of(command: str) -> str:
    """Basename of the .py file a hooks.json command runs, if any."""
    for token in command.split():
        if token.endswith(".py"):
            return os.path.basename(token)
    return ""


def _check_rule_pack() -> tuple:
    from loupe.tools import resolve_tool

    pack = PLUGIN_ROOT / "rules" / "ast-grep"
    rules = sorted(pack.rglob("*.yml")) + sorted(pack.rglob("*.yaml"))
    binary = resolve_tool("ast-grep")

    if not rules:
        print(f"  FAIL no rule files under {pack}")
        return ("rule pack", False)
    print(f"  ok {len(rules)} rule file(s) under {pack}")
    if not binary:
        print("  FAIL ast-grep not found - the rule pack cannot run")
        return ("rule pack", False)
    print(f"  ok ast-grep at {binary}")
    return ("rule pack", True)


def _check_state() -> tuple:
    from loupe.project import project_hash
    from loupe.state import load_state, state_path

    project = project_hash(os.getcwd())
    path = state_path(project)
    try:
        load_state(project)
    except Exception as err:
        print(f"  FAIL state unreadable ({err})")
        return ("state", False)
    print(f"  ok state readable ({path})")

    probe = path.parent / ".loupe-health-probe"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as err:
        print(f"  FAIL state dir not writable ({err})")
        return ("state", False)
    print(f"  ok state dir writable ({path.parent})")
    return ("state", True)


if __name__ == "__main__":
    sys.exit(main())
