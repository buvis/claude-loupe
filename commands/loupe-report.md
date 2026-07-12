---
description: Render the current project's loupe state - session finding counts by category, queued files, tool-nudge status, and tool health
user_invocable: true
---

# Loupe Report

Run the report helper from the current project directory:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/report.py"
```

The output is already formatted; relay it to the user as-is. Sections:

- **enabled / immediate_fix**: the effective config for this project (global `~/.claude/loupe/config.json` overridden by the project's `.claude/loupe.json`).
- **session findings**: analysis finding counts by category since session start.
- **format queue**: files waiting for the end-of-turn autofix/format pass.
- **tool nudges**: missing-but-needed tools; `pending` means the one-time notice has not printed yet, `reported` means it already did.
- **tool health**: where each tool loupe can use resolves from (`missing` = not found via PATH, mise shims, or `mise which`).

If the script itself fails, show the error verbatim - do not re-derive the report by reading state files by hand.
