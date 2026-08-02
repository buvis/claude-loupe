# Loupe

[![GitHub license](https://img.shields.io/github/license/buvis/claude-loupe)](https://github.com/buvis/claude-loupe/blob/master/LICENSE)

> A loupe is the jeweler's lens: held right against the work, merciless about flaws.

Code-quality feedback for [Claude Code](https://claude.ai/code) edits. Loupe blocks secret leaks before they land, flags stub bodies and security violations as must-fix the moment they do, runs ast-grep rules and fast linters on every `Write`/`Edit`, defers autofix, formatting, and slow linters (clippy, svelte-check) to end of turn, and nudges once per project when a needed tool is missing.

**Status: released and dogfooded.** All six hook entry points and all six commands are in place. Measured 2026-08-02 over 60 real source files: `analyze.py` adds 47 ms p50 (budget was ~1s), the whole per-edit chain 82 ms.

## Hooks

| Event | Script | What it does |
|-------|--------|--------------|
| `SessionStart` | `session_start.py` | resets the runtime block, caches the language and tool profile |
| `PreToolUse` (`Write\|Edit\|MultiEdit`) | `scan_secrets.py` | exit 2 on a credential in the content about to land |
| `PreToolUse` (`Write\|Edit\|MultiEdit`) | `guard_edit.py` | warns or blocks an edit to lines never read this session |
| `PostToolUse` (`Read`) | `record_read.py` | records the read's line range for the guard above |
| `PostToolUse` (`Write\|Edit\|MultiEdit`) | `analyze.py` | ast-grep pack plus fast linter; stub and security findings come back as must-fix feedback (the edit itself has already landed) |
| `Stop` | `agent_end.py` | autofix, format, slow linters, tool nudges, TDI bookkeeping |

Every entry point fails open: malformed hook JSON, unknown fields, or an engine crash exits 0, so loupe can never break the session it watches.

## Commands

| Command | What it answers |
|---------|-----------------|
| `/loupe-report` | what has loupe found in this project |
| `/loupe-check-health` | is loupe itself wired correctly (engine imports, entry points, rule pack, state) |
| `/loupe-check-tools` | which linter, autofixer, and slow linter resolve for each language |
| `/loupe-show-tdi` | how is the Technical Debt Index trending |
| `/loupe-toggle` | turn loupe on or off for this project |
| `/loupe-allow-edit <path>` | permit one edit the read guard would stop |

## What's inside

| Module | Role |
|--------|------|
| `hooks/loupe/project.py` | stable per-project hash, git-root aware without spawning `git` |
| `hooks/loupe/state.py` | per-project state: a runtime block that resets each session, a persistent block that survives |
| `hooks/loupe/config.py` | global config deep-merged with a per-project override; malformed input falls back to defaults |
| `hooks/loupe/languages.py` | language detection by file extension |
| `hooks/loupe/tools.py` | tool resolution via PATH, mise shims, then `mise which`; nudge-once tracking for missing tools |
| `hooks/loupe/findings.py` | the `Finding` record and the blocking (stub, security) vs advisory (correctness, style) split |
| `hooks/loupe/readcoverage.py` | read line-range merge and coverage math behind the edit guard |
| `hooks/loupe/tdi.py` | unweighted Technical Debt Index counts and their trend |

State lives at `~/.claude/loupe/state/<project-hash>.json`. Config reads `~/.claude/loupe/config.json`, overridden per project by `.claude/loupe.json`.

| Key | Default | Meaning |
|-----|---------|---------|
| `enabled` | `true` | master switch for every hook |
| `immediate_fix` | `false` | fix and format inline instead of deferring to `Stop` |
| `read_guard` | `"warn"` | `warn`, `block`, or `off` for edits to unread lines |

`read_guard` defaults to `warn` rather than `block` on purpose: the agent legitimately learns a file's contents through Grep output, subagent returns, and prior-session context, none of which pass through the `Read` hook, so `block` false-positives on valid edits. Opt into it per project.

`ast-grep` is the one tool worth installing: without it the entire rule pack is inert and no stub or security finding ever fires. Every other tool is optional and skipped silently with one nudge per project.

## Install

```
/plugin marketplace add buvis/claude-plugins
/plugin install loupe@buvis-plugins
```

### Alternative: install directly from this repo

```
/plugin marketplace add buvis/claude-loupe
/plugin install loupe@claude-loupe
```

## Development

```
python3 -m pytest hooks/tests
```

Engine code is stdlib-only Python; no runtime dependencies.

## Why "loupe"

Loupe reimplements `pi-lens`, the Pi ecosystem's real-time edit-feedback extension, natively for Claude Code. A loupe is the lens you hold up close to inspect every cut.

## License

[MIT](LICENSE)
