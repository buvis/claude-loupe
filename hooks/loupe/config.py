"""Effective loupe config: defaults, then global file, then project override.

The global config lives at ``~/.claude/loupe/config.json``; a project may
override it with ``.claude/loupe.json`` at its root. Layers deep-merge in
that order. A missing or malformed layer contributes nothing, and a
wrong-typed value for a known key falls back to its default, so
``load_config`` always returns a usable config.

Known keys:

- ``enabled`` (bool, default ``True``): master switch for all loupe hooks.
- ``immediate_fix`` (bool, default ``False``): fix/format inline at edit
  time instead of deferring to Stop.
"""

import json
from pathlib import Path

DEFAULTS = {
    "enabled": True,
    "immediate_fix": False,
}


def global_config_path() -> Path:
    return Path.home() / ".claude" / "loupe" / "config.json"


def project_config_path(root: str | Path) -> Path:
    return Path(root) / ".claude" / "loupe.json"


def load_config(root: str | Path | None = None) -> dict:
    """Merged effective config for a project root (default: cwd)."""
    root_path = Path(root) if root is not None else Path.cwd()
    merged = _deep_merge(dict(DEFAULTS), _read_layer(global_config_path()))
    merged = _deep_merge(merged, _read_layer(project_config_path(root_path)))
    for key, default in DEFAULTS.items():
        if not isinstance(merged.get(key), type(default)):
            merged[key] = default
    return merged


def _read_layer(path: Path) -> dict:
    """One config layer; missing, unreadable, or non-object JSON is empty."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _deep_merge(base: dict, override: dict) -> dict:
    """New dict with ``override`` merged over ``base``, recursing into dicts."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
