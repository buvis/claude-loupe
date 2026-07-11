"""Import-light enabled gate shared by the loupe hook entry points.

loupe joins a per-edit hook stack where every Python spawn counts, so a
disabled project must exit before any ``loupe`` engine import happens.
This module therefore uses only the stdlib and deliberately duplicates
two tiny pieces of engine behavior:

- ``find_project_root`` mirrors ``loupe.project.project_root``: walk up
  from the start directory to the nearest ``.git`` marker, falling back
  to the resolved start.
- ``loupe_enabled`` mirrors how ``loupe.config.load_config`` resolves
  the ``enabled`` key: the project layer (``.claude/loupe.json``)
  overrides the global layer (``~/.claude/loupe/config.json``), and a
  wrong-typed value falls back to the default ``True`` - not to the
  other layer.

test_gate.py asserts parity with the engine so the copies cannot drift
silently.
"""

import json
import sys
from pathlib import Path


def read_hook_json():
    """Hook payload from stdin; ``None`` for anything but a JSON object."""
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def find_project_root(cwd) -> Path:
    """Mirror of ``loupe.project.project_root``; see module docstring."""
    start = Path(cwd).expanduser().resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


def loupe_enabled(cwd) -> bool:
    """Effective ``enabled`` flag; mirror of ``loupe.config`` resolution."""
    root = find_project_root(cwd)
    layers = (
        Path.home() / ".claude" / "loupe" / "config.json",
        root / ".claude" / "loupe.json",
    )
    value = True
    for path in layers:
        layer = _read_json_dict(path)
        if "enabled" in layer:
            value = layer["enabled"]
    return value if isinstance(value, bool) else True


def _read_json_dict(path: Path) -> dict:
    """One config layer; missing, unreadable, or non-object JSON is empty."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}
