"""Locate lint/format tools and record one nudge per project when absent.

Resolution order: PATH, then the mise shims directory, then ``mise which``
(not every mise install gets a shim). loupe never installs anything; when
a needed tool is absent, ``record_nudge`` marks it once in the project's
persisted nudge log so the Stop summary can suggest it exactly one time.
"""

import os
import shutil
import subprocess
from pathlib import Path

from .state import save_state

MISE_TIMEOUT_SECONDS = 5


def mise_shims_dir() -> Path:
    return Path.home() / ".local" / "share" / "mise" / "shims"


def resolve_tool(name: str) -> str | None:
    """Absolute path to ``name`` via PATH, mise shim, or ``mise which``.

    Returns ``None`` when the tool cannot be resolved anywhere; the caller
    decides whether that deserves a nudge.
    """
    found = shutil.which(name)
    if found:
        return found
    shim = mise_shims_dir() / name
    if shim.is_file() and os.access(shim, os.X_OK):
        return str(shim)
    return _mise_which(name)


def _mise_which(name: str) -> str | None:
    """Ask mise for an unshimmed install; ``None`` when mise is absent or unaware."""
    try:
        result = subprocess.run(
            ["mise", "which", name],
            capture_output=True,
            text=True,
            timeout=MISE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    candidate = result.stdout.strip()
    if candidate and Path(candidate).is_file():
        return candidate
    return None


def record_nudge(state: dict, project: str, tool: str) -> tuple[dict, bool]:
    """Record a missing-but-needed tool at most once per project.

    Returns ``(state, recorded)``. When ``tool`` is already in the
    persisted nudge log, the input state comes back unchanged with
    ``False`` and nothing touches disk. Otherwise a new state with the
    nudge appended is saved and returned with ``True``.
    """
    nudged = state["persistent"]["nudged"]
    if tool in nudged:
        return state, False
    new_state = {
        **state,
        "persistent": {**state["persistent"], "nudged": [*nudged, tool]},
    }
    save_state(project, new_state)
    return new_state, True
