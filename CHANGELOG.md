# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **loupe**: plugin skeleton that installs with empty hook registration
- **loupe**: per-project identity hashing (git-root aware, subprocess-free) and state persistence with a session-reset runtime block and a surviving persistent block; malformed state rebuilds from defaults
- **loupe**: config resolution deep-merging global `~/.claude/loupe/config.json` with per-project `.claude/loupe.json` (keys: `enabled` default true, `immediate_fix` default false); malformed layers fall back to defaults
- **loupe**: language detection by extension, tool resolution via PATH then mise shims then `mise which` with a nudge-once-per-project log, and the `Finding` model with its blocking (stub, security) vs advisory (correctness, style) classification
- **loupe**: pre-write secrets scan engine matching AWS keys, GitHub and Slack tokens, JWTs, private key blocks, connection strings with embedded passwords, and long or high-entropy credential assignments; obvious placeholders (`example`, `changeme`, `xxx`, `<...>`, `$`/`{` interpolation) never match
- **loupe**: fast per-edit linter dispatch (ruff, biome or eslint, stylelint, sqlfluff, rubocop, shellcheck) with per-tool timeout, advisory-only findings, silent skip plus one nudge per project for absent tools; clippy and svelte-check stay named in `SLOW_LINTERS` for the Stop queue
- **loupe**: ast-grep rule-pack dispatch mapping matches to categorized findings via the `<category>-<language>-<slug>` rule-id convention; crash, timeout, or bad JSON degrade to one advisory warning finding, absent binary nudges once per project
