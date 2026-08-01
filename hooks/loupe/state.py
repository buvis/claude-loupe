"""Per-project loupe state with a runtime vs persistent split.

State lives at ``~/.claude/loupe/state/<project-hash>.json``. The runtime
block (format queue, session findings) is per-session scratch and resets
at session start; the persistent block survives across sessions: the
nudge log (``nudged`` guards re-recording, ``nudge_reported`` marks which
nudges the Stop summary has already delivered, so each prints exactly
once per project). Loading never raises on bad content: missing files, non-JSON,
non-dict JSON, and wrong-typed blocks or fields all rebuild from the
defaults, field by field.

Writes are atomic (tmp file + ``os.replace``). Concurrent hook writes are
last-wins, the same accepted limitation the other buvis hook plugins
document.
"""

import json
import os
from pathlib import Path

STATE_VERSION = 1


def default_runtime() -> dict:
    """Fresh runtime block: per-session scratch.

    ``read_ranges`` maps a file path to the merged line ranges the agent
    has read this session; ``allow_edit`` lists paths a one-shot
    ``/loupe-allow-edit`` override has exempted from the read guard. Both
    are session-scoped on purpose: coverage earned in a previous session
    is not coverage this one can claim.
    """
    return {
        "format_queue": [],
        "findings": [],
        "read_ranges": {},
        "allow_edit": [],
    }


def default_persistent() -> dict:
    """Fresh persistent block: survives across sessions.

    ``tdi_history`` is the Technical Debt Index trend, one appended entry
    per turn that produced findings.
    """
    return {"nudged": [], "nudge_reported": [], "tdi_history": []}


def default_state() -> dict:
    return {
        "version": STATE_VERSION,
        "runtime": default_runtime(),
        "persistent": default_persistent(),
    }


def state_dir() -> Path:
    return Path.home() / ".claude" / "loupe" / "state"


def state_path(project: str) -> Path:
    return state_dir() / f"{project}.json"


def load_state(project: str) -> dict:
    """Load the project's state; missing or malformed content rebuilds defaults."""
    try:
        raw = json.loads(state_path(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default_state()
    return _repair(raw)


def save_state(project: str, state: dict) -> None:
    """Atomically persist ``state`` for ``project``.

    Raises ``OSError`` when the write fails; hook entry points own the
    fail-open wrapping.
    """
    path = state_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def reset_runtime(state: dict) -> dict:
    """New state with a fresh runtime block; the persistent block carries over."""
    return {**state, "runtime": default_runtime()}


def _repair(raw: object) -> dict:
    """Coerce arbitrary decoded JSON into a schema-valid state dict.

    Starts from the defaults and copies over only the known keys whose
    values carry the expected type, so a corrupt field never leaks into
    the engine.
    """
    state = default_state()
    if not isinstance(raw, dict):
        return state
    for block_name in ("runtime", "persistent"):
        block = raw.get(block_name)
        if not isinstance(block, dict):
            continue
        for key, default in state[block_name].items():
            value = block.get(key, default)
            if isinstance(value, type(default)):
                state[block_name][key] = value
    return state
