#!/usr/bin/env python3
"""Per-language tool coverage for /loupe-check-tools.

``report.py`` answers "is this tool present?"; this answers "what does
loupe actually do for each language here, and what is it not doing?".
For every language loupe knows, it resolves the fast linter, the safe
autofixers, and the slow linter, and flags what is missing.

The tool inventory is imported rather than restated: ``HEALTH_TOOLS``
from ``report``, the linter maps from ``loupe.linters``, the autofixer
map from ``loupe.formatters``. A tool added there shows up here with no
edit.

A command helper, not a hook: it takes no stdin JSON, works from the
invocation cwd, and does not fail open - a broken report should say so.
"""

import os
import sys

from report import HEALTH_TOOLS


def main() -> int:
    from loupe.formatters import AUTOFIXERS
    from loupe.linters import FAST_LINTERS, SLOW_LINTERS
    from loupe.project import project_hash, project_root
    from loupe.state import load_state
    from loupe.tools import resolve_tool

    cwd = os.getcwd()
    root = project_root(cwd)
    state = load_state(project_hash(cwd))

    print(f"loupe tool check - {root}")

    resolved = {tool: resolve_tool(tool) for tool in HEALTH_TOOLS}
    languages = sorted(set(FAST_LINTERS) | set(SLOW_LINTERS) | set(AUTOFIXERS))

    print("\nper language:")
    for language in languages:
        parts = [
            # FAST_LINTERS values are candidate tuples (first resolvable
            # wins); SLOW_LINTERS values are a single tool name.
            _slot("lint", FAST_LINTERS.get(language, ()), resolved),
            _slot("fix", _autofix_tools(AUTOFIXERS.get(language)), resolved),
            _slot("slow lint", _one(SLOW_LINTERS.get(language)), resolved),
        ]
        print(f"  {language}: " + "; ".join(part for part in parts if part))

    print("\nanalysis:")
    print(f"  ast-grep: {resolved.get('ast-grep') or 'MISSING'}")
    if not resolved.get("ast-grep"):
        print("    the whole rule pack is inert without it - stub and")
        print("    security findings will never fire. Install it first.")

    missing = [tool for tool, path in resolved.items() if not path]
    print("\nmissing: " + (", ".join(missing) if missing else "nothing"))

    nudged = state["persistent"]["nudged"]
    if nudged:
        reported = set(state["persistent"]["nudge_reported"])
        entries = ", ".join(
            f"{tool} ({'reported' if tool in reported else 'pending'})"
            for tool in nudged
        )
        print(f"nudges recorded: {entries}")
    return 0


def _one(tool) -> list:
    """A single optional tool name as a list."""
    return [tool] if tool else []


def _autofix_tools(entry) -> list:
    """Tool names from an ``AUTOFIXERS`` entry.

    An entry is a tuple of ``(tool, args)`` pairs because a language can
    have several candidates (javascript: biome or eslint); only the names
    matter for a presence check.
    """
    if not entry:
        return []
    return [pair[0] for pair in entry if isinstance(pair, (list, tuple)) and pair]


def _slot(label: str, tools, resolved: dict) -> str:
    """One ``label: tool (state)`` fragment; empty when nothing is mapped."""
    names = [tool for tool in tools if tool]
    if not names:
        return ""
    rendered = " or ".join(
        f"{tool} ({'ok' if _located(tool, resolved) else 'MISSING'})"
        for tool in names
    )
    return f"{label} {rendered}"


def _located(tool: str, resolved: dict):
    """Resolved path for ``tool``; clippy rides cargo, which is what resolves."""
    return resolved.get("cargo" if tool == "clippy" else tool)


if __name__ == "__main__":
    sys.exit(main())
