# Loupe

[![GitHub license](https://img.shields.io/github/license/buvis/claude-loupe)](https://github.com/buvis/claude-loupe/blob/master/LICENSE)

> A loupe is the jeweler's lens: held right against the work, merciless about flaws.

Code-quality feedback for [Claude Code](https://claude.ai/code) edits. When complete, loupe blocks secret leaks, stub bodies, and security violations before they land, runs ast-grep rules and fast linters on every `Write`/`Edit`, defers autofix, formatting, and slow linters to end of turn, and nudges once per project when a needed tool is missing.

**Status: pre-release.** This repo currently ships the engine foundation. The plugin installs cleanly but registers no hooks yet; hook entry points, the ast-grep rule pack, and the `/loupe-report` and `/loupe-toggle` commands land in later phases.

## What's inside

| Module | Role |
|--------|------|
| `hooks/loupe/project.py` | stable per-project hash, git-root aware without spawning `git` |
| `hooks/loupe/state.py` | per-project state: a runtime block that resets each session, a persistent block that survives |
| `hooks/loupe/config.py` | global config deep-merged with a per-project override; malformed input falls back to defaults |
| `hooks/loupe/languages.py` | language detection by file extension |
| `hooks/loupe/tools.py` | tool resolution via PATH, mise shims, then `mise which`; nudge-once tracking for missing tools |
| `hooks/loupe/findings.py` | the `Finding` record and the blocking (stub, security) vs advisory (correctness, style) split |

State lives at `~/.claude/loupe/state/<project-hash>.json`. Config reads `~/.claude/loupe/config.json`, overridden per project by `.claude/loupe.json`. Keys: `enabled` (default `true`), `immediate_fix` (default `false`).

## Install

Not yet published to the buvis-plugins marketplace; that happens with the v1 release. Once published:

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
