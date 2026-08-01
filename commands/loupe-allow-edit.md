---
description: Permit one edit to a file the read guard would otherwise stop, without turning the guard off
argument-hint: <path>
user_invocable: true
---

# Loupe Allow Edit

Grant a one-shot read-guard override for the path the user named:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/allow_edit.py" "$ARGUMENTS"
```

Relay the output as-is.

What it does: records the file in this session's override list. The next time the read guard would have stopped an edit to it, the guard steps aside and **consumes the override**. One edit, not a standing exemption.

Notes:

- The override is session-scoped. It does not survive into the next session.
- A path that is not an existing file is refused, not recorded - the guard already permits creating new files, so there would be nothing to override.
- If the same path already has a pending override, this reports that and changes nothing.
- To stop the guard permanently for a project, set `"read_guard": "off"` in its `.claude/loupe.json` instead. To make it block rather than warn, set `"block"`. The default is `warn`, because the agent legitimately learns file contents through Grep output, subagent returns, and prior-session context, none of which pass through the Read hook.

If the script exits nonzero, show the error verbatim rather than editing the state file by hand.
