# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **loupe**: read-coverage guarding, the two hook entry points PRD 00030 specified but v0.1.0 shipped without. `record_read.py` (`PostToolUse` on `Read`) merges each read's line range into per-session, per-file coverage, coalescing adjacent ranges so reads of 1-100 and 101-200 become one 1-200 span; `guard_edit.py` (`PreToolUse` on `Write|Edit|MultiEdit`) resolves an edit's target lines and reports the ones never read. New `read_guard` config key: `warn` (default, prints to stderr and allows), `block` (exit 2), `off`. The default is not `block` because the agent legitimately learns file contents through Grep output, subagent returns, and prior-session context, none of which pass through the `Read` hook. Markdown/text/log files, new-file creation, and unresolvable targets are exempt, and an unresolvable target never becomes a block
- **loupe**: `/loupe-allow-edit <path>` grants a one-shot read-guard override that `guard_edit.py` consumes when it fires, so it can never silently become a permanent exemption; session-scoped, and a non-existent path is refused rather than recorded
- **loupe**: Technical Debt Index. `loupe/tdi.py` counts a turn's findings by category, unweighted on purpose (raw counts trend honestly without weights nobody has data to tune), and `agent_end.py` banks one history entry per turn that produced findings, inside the same claim that clears the format queue so a re-fired `Stop` cannot double-count. History is capped at 500 entries, oldest dropped first
- **loupe**: `/loupe-show-tdi` renders the trend: latest turn, direction against the previous turn, lifetime total, and a per-turn breakdown. An empty history reports that it cannot distinguish "nothing found yet" from "loupe never ran here" rather than implying zero debt
- **loupe**: `/loupe-check-health` diagnoses loupe itself: every engine module imports, every entry point named in `hooks.json` exists on disk, the rule pack is present and `ast-grep` resolves, and state is readable and writable. Exits nonzero on any failure, so it can be trusted as a gate
- **loupe**: `/loupe-check-tools` shows which fast linter, autofixer(s), and slow linter resolve per language, calling out `ast-grep` separately because the whole rule pack is inert without it

### Fixed

- **loupe**: the self-referencing marketplace description claimed "engine foundation only, no hooks registered yet", which stopped being true when the four original entry points went live

## [0.1.0] - 2026-08-02

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
- **loupe**: hook registration goes live with four entry points: `SessionStart` bootstrap (per-session runtime reset that leaves `compact` alone), a `PreToolUse` secrets guard aborting Write/Edit/MultiEdit with exit 2 when credentials are detected, `PostToolUse` analysis running the ast-grep pack plus the fast linter per edit (stub and security findings block with file/rule/line on stderr, advisory findings print inline), and a `Stop` pass that drains the format queue exactly once per turn - safe autofix, config-gated formatting, one advisory clippy/svelte-check run per queued language, and once-per-project missing-tool nudges
- **loupe**: entry points stay import-light while disabled (a stdlib-only gate checks the effective `enabled` flag before any engine import) and fail open - malformed hook JSON, unknown fields, or an engine crash exit 0 so loupe can never break the session it watches
- **loupe**: `/loupe-report` command rendering the project's session finding counts by category, format queue, nudge status (pending/reported), and tool health for every tool loupe can use
- **loupe**: `/loupe-toggle` command flipping the per-project `enabled` flag through the `.claude/loupe.json` override (other keys preserved) and reporting the new state
