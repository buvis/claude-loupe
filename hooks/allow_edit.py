#!/usr/bin/env python3
"""Grant a one-shot read-guard override for /loupe-allow-edit <path>.

Records one path in the session's ``runtime.allow_edit`` list.
``guard_edit.py`` removes the entry the next time it would have stopped
an edit to that file, so the override covers exactly one edit and cannot
silently become a permanent exemption. To turn the guard off for real,
set ``read_guard: "off"`` in the project config instead.

The override is session-scoped: it lives in the runtime block, which
``session_start.py`` resets. A grant you forget about does not survive
into tomorrow.

A command helper, not a hook: errors surface loudly instead of failing
open, and a missing path is refused rather than recorded.
"""

import os
import sys


def main(argv=None) -> int:
    from loupe.project import project_hash
    from loupe.state import load_state, save_state

    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or not args[0].strip():
        print(
            "usage: allow_edit.py <path>   (exactly one file path)",
            file=sys.stderr,
        )
        return 2

    target = os.path.abspath(os.path.expanduser(args[0].strip()))
    if not os.path.isfile(target):
        print(
            f"loupe: {target} is not an existing file - nothing to override "
            "(the read guard already allows creating new files).",
            file=sys.stderr,
        )
        return 1

    project = project_hash(os.getcwd())
    state = load_state(project)
    allowed = state["runtime"]["allow_edit"]
    if target in allowed:
        print(f"loupe: an override for {target} is already pending")
        return 0

    save_state(
        project,
        {
            **state,
            "runtime": {**state["runtime"], "allow_edit": [*allowed, target]},
        },
    )
    print(f"loupe: read guard will skip the next edit to {target}")
    print("(one edit only; the override is consumed when it fires)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
