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
- **loupe**: ast-grep rule pack (26 rules: python 8, javascript 7, typescript twins 7, rust 4) covering stub bodies, swallowed exceptions, eval/exec, shell-injection subprocess use, pickle.loads, innerHTML, NaN comparisons, mutable default args, todo!/unimplemented!, unsafe blocks, and non-test unwrap; authored fresh for loupe (no local pi-lens source to port, so no MIT NOTICE applies) with a positive and negative fixture per rule verified against ast-grep 0.44
- **loupe**: safe autofix dispatch (ruff --fix, biome check --write or eslint --fix, stylelint --fix, sqlfluff fix, rubocop -a) and nearest-config-wins formatter dispatch (prettier/biome/ruff/black/rustfmt; Biome and Ruff defaults for unconfigured JS-TS and Python, nothing for other languages) with per-file change detection and a one-line-per-file summary
- **loupe**: persistent `nudge_reported` state field marking which missing-tool nudges the Stop summary has already delivered, so each nudge prints exactly once per project
