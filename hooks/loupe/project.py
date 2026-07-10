"""Project identity for loupe state and config scoping.

Mirrors cartographer's git-toplevel identity (``sha256(root)[:12]``)
without spawning a subprocess: loupe runs inside per-edit hooks, so a
``git`` call per spawn is latency the budget cannot afford. The root is
found by walking up from ``cwd`` to the nearest ``.git`` marker (a
directory in normal checkouts, a file in worktrees and submodules).
"""

import hashlib
from pathlib import Path

_HASH_LENGTH = 12


def project_root(cwd: str | Path) -> Path:
    """Nearest ancestor of ``cwd`` (or ``cwd`` itself) containing ``.git``.

    Falls back to the resolved ``cwd`` when no marker exists, so every
    directory maps to some stable root.
    """
    start = Path(cwd).expanduser().resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


def project_hash(cwd: str | Path) -> str:
    """Stable per-project identifier for a working directory.

    Any two directories inside the same checkout map to the same hash;
    distinct projects map to distinct hashes.
    """
    root = project_root(cwd)
    return hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:_HASH_LENGTH]
