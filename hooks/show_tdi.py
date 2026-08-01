#!/usr/bin/env python3
"""Technical Debt Index trend for /loupe-show-tdi.

Renders the banked TDI history: the latest turn's finding count, the
direction against the previous turn, the lifetime total, and a per-turn
tail with category breakdowns. Entries are appended at ``Stop``, one per
turn that produced findings, so an empty history means either a fresh
project or a clean one - the output says it cannot distinguish those
rather than implying zero debt.

A command helper, not a hook: it takes no stdin JSON, works from the
invocation cwd, and does not fail open.
"""

import os
import sys

TAIL_ENTRIES = 10

_DIRECTION_WORDS = {"up": "worse", "down": "better", "flat": "unchanged"}


def main() -> int:
    from loupe.project import project_hash, project_root
    from loupe.state import load_state
    from loupe.tdi import trend

    cwd = os.getcwd()
    root = project_root(cwd)
    state = load_state(project_hash(cwd))
    history = state["persistent"]["tdi_history"]
    summary = trend(history)

    print(f"loupe TDI - {root}")

    if summary["entries"] == 0:
        print("no history yet: either no turn has produced findings, or")
        print("loupe has not run here. /loupe-check-health tells you which.")
        return 0

    print(
        f"latest turn: {summary['latest']} finding(s) "
        f"({_DIRECTION_WORDS[summary['direction']]} vs previous turn)"
    )
    print(
        f"lifetime: {summary['lifetime']} finding(s) over "
        f"{summary['entries']} recorded turn(s)"
    )

    tail = history[-TAIL_ENTRIES:]
    print(f"\nlast {len(tail)} turn(s):")
    for entry in tail:
        counts = entry.get("counts", {})
        breakdown = ", ".join(
            f"{category}: {count}" for category, count in sorted(counts.items())
        )
        print(f"  {entry['ts']}  total {entry['total']}  ({breakdown})")

    print("\nCounts are unweighted on purpose: raw numbers trend honestly")
    print("without weights nobody has data to tune yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
