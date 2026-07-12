#!/usr/bin/env python3
"""Render the current project's loupe state for /loupe-report.

A command helper, not a hook: it takes no stdin JSON, works from the
invocation cwd, and does not mask failures behind fail-open - a broken
report should say so. It reads the same engine state the hooks write,
and it works for disabled projects too (the report is how you find
out loupe is off).

Lives in hooks/ beside the ``loupe`` package so the engine imports
resolve from the script directory, exactly like the hook entry points.
"""

import os
import sys
from collections import Counter

# Tools loupe can use anywhere in the pipeline: analysis (ast-grep),
# fast linters, slow linters (clippy rides cargo), and formatters.
HEALTH_TOOLS = (
    "ast-grep",
    "ruff",
    "biome",
    "eslint",
    "stylelint",
    "sqlfluff",
    "rubocop",
    "shellcheck",
    "cargo",
    "svelte-check",
    "prettier",
    "black",
    "rustfmt",
)


def main() -> int:
    from loupe.config import load_config
    from loupe.project import project_hash, project_root
    from loupe.state import load_state
    from loupe.tools import resolve_tool

    cwd = os.getcwd()
    root = project_root(cwd)
    project = project_hash(cwd)
    config = load_config(root)
    state = load_state(project)

    print(f"loupe report - {root} (project {project})")
    print(
        f"enabled: {config['enabled']}    "
        f"immediate_fix: {config['immediate_fix']}"
    )

    counts = Counter(
        finding.get("category", "unknown")
        for finding in state["runtime"]["findings"]
        if isinstance(finding, dict)
    )
    if counts:
        rendered = ", ".join(
            f"{category}: {count}" for category, count in sorted(counts.items())
        )
        print(f"session findings: {rendered}")
    else:
        print("session findings: none")

    queue = state["runtime"]["format_queue"]
    if queue:
        print(f"format queue: {len(queue)} file(s)")
        for path in queue:
            print(f"  {path}")
    else:
        print("format queue: empty")

    nudged = state["persistent"]["nudged"]
    reported = set(state["persistent"]["nudge_reported"])
    if nudged:
        entries = ", ".join(
            f"{tool} ({'reported' if tool in reported else 'pending'})"
            for tool in nudged
        )
        print(f"tool nudges: {entries}")
    else:
        print("tool nudges: none")

    print("tool health:")
    for tool in HEALTH_TOOLS:
        located = resolve_tool(tool)
        print(f"  {tool}: {located or 'missing'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
