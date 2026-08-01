---
description: Diagnose loupe itself - engine imports, registered hook entry points, ast-grep rule pack, and state readability
user_invocable: true
---

# Loupe Check Health

Run the health check from the current project directory:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/check_health.py"
```

Relay the output as-is. Every check prints `ok` or `FAIL` with a reason, and the script exits nonzero when anything failed, so treat a nonzero exit as a real problem rather than a formatting quirk.

Checks:

- **engine modules**: every module in `hooks/loupe/` imports. A failure here means the hooks are silently failing open on every edit - loupe looks installed and does nothing.
- **hook entry points**: every script named in `hooks.json` exists on disk.
- **rule pack**: rule files are present *and* `ast-grep` resolves. Without the binary the pack is inert, so stub and security findings never fire.
- **state**: the project's state file is readable and its directory writable.

This is the command to run when loupe seems installed but nothing happens. `/loupe-report` shows what loupe found; this shows whether loupe can find anything at all.

If the script itself fails, show the error verbatim - do not re-derive the diagnosis by hand.
