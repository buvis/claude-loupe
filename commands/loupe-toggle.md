---
description: Flip loupe's per-project enabled flag via the .claude/loupe.json override and report the new state
user_invocable: true
---

# Loupe Toggle

Flip loupe on or off for the current project by running:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/toggle.py"
```

The helper resolves the project root, reads the effective config (global `~/.claude/loupe/config.json` overridden by the project's `.claude/loupe.json`), writes the project override with `enabled` flipped (preserving any other keys), and prints the new state. Relay the printed result to the user.

Notes:

- The change takes effect on the next hook invocation - no restart needed, hooks re-read config on every spawn.
- The helper is a pure toggle. If the user asked for a specific state ("disable loupe") and the printed result landed on the opposite side, run the command once more and relay the corrected result.
