---
description: Show which linter, autofixer, and slow linter loupe resolves for each language, and what is missing
user_invocable: true
---

# Loupe Check Tools

Run the tool check from the current project directory:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/check_tools.py"
```

Relay the output as-is. Sections:

- **per language**: for each language loupe knows, the fast linter, safe autofixer(s), and slow linter it would use, each marked `ok` or `MISSING`. Where a language has several autofixer candidates (javascript: biome or eslint) all are listed.
- **analysis**: whether `ast-grep` resolves. It is called out separately because the entire rule pack depends on it - without the binary, stub and security findings never fire at all.
- **missing**: the flat list of tools loupe could use here but cannot find.
- **nudges recorded**: missing-but-needed tools loupe has already noticed; `pending` means the one-time notice has not printed yet.

`MISSING` is not an error - loupe skips absent tools silently and nudges once per project. It only means those checks are not running.

For "is loupe itself working", use `/loupe-check-health`. For "what has loupe found here", use `/loupe-report`.
