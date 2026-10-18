---
catchup: skip
design: skip
default_model: sonnet
model_tier_rationale: one environment check in one gate function, two call sites, additive tests
---

# Honor unattended sessions

## Problem

Loupe's hooks do not know when they run inside an unattended autopilot session. `hooks/agent_end.py` drains the format queue at every Stop and rewrites edited Python files (`_fix_and_format`), and `hooks/analyze.py` can fix inline when the config says so (`_fix_inline`). Inside a loop session those rewrites land as uncommitted diffs between an implementor's commits; the autopilot work skill had to grow a `reflow` field just to track them. In the week to 2026-09-05 three of 132 recorded attempts across the agent-skills and claude-autopilot loops carried a reflow (`skills/sweep-fix/scripts/sweep.py:24`, `skills/distil-memory/scripts/test_funnel_report.py:20`, `skills/use-codex/scripts/test_codex_hook_doctor.py:28`). The autopilot runner sets `CLAUDE_UNATTENDED=1` in every session it spawns (`claude-autopilot/skills/run-autopilot/cli/runner.py`, `LAUNCH_ENV`), and no loupe module reads it (`rg -l 'UNATTENDED' hooks` is empty).

## Solution

Add one stdlib-only predicate to `hooks/gate.py`, `unattended()`, true exactly when `os.environ.get("CLAUDE_UNATTENDED") == "1"`. When it is true, `agent_end.py` skips the autofix, format and slow-lint passes but still claims the queue, reports pending nudges and banks the TDI entry; `analyze.py` still lints and reports findings but neither fixes inline nor queues the file for Stop. Interactive sessions never set the variable, so nothing changes for them.

## Requirements

### Must have
- `gate.unattended()` returns `True` only for the exact value `"1"`; `"0"`, `"true"`, empty and unset all return `False`.
- Under `CLAUDE_UNATTENDED=1`, a Stop with a queued Python file leaves the file byte-identical, prints no `loupe stop summary` format lines, clears the queue, and still prints nudges and the TDI line when there is something to report.
- Under `CLAUDE_UNATTENDED=1`, an analyze call on a file with an advisory finding prints the finding, records it in session state, and leaves `format_queue` empty; an immediate-fix config still does not rewrite the file.
- Interactive behavior is unchanged: the existing `test_stop_runs_deferred_fix_and_format_exactly_once` and `test_immediate_fix_runs_inline_instead_of_queuing` keep passing untouched.
- CHANGELOG entry under `[Unreleased]` / `### Changed`, prefixed `**loupe**:`.

### Nice to have
- README sentence under the configuration section stating the variable and what it disables.

## Implementation

### Module: gate
- **Location**: `hooks/gate.py`
- **Responsibility**: import-light predicates every entry point checks before engine work
- **Exports**: `unattended()`, alongside the existing `loupe_enabled(cwd)`

### Module: agent_end
- **Location**: `hooks/agent_end.py`
- **Responsibility**: Stop entry point; under `unattended()` it skips `_fix_and_format` and `_slow_lint` and keeps claim, nudges and TDI
- **Exports**: `main()` (unchanged signature)

### Module: analyze
- **Location**: `hooks/analyze.py`
- **Responsibility**: per-edit entry point; under `unattended()` it reports findings and never rewrites or queues
- **Exports**: `main()` (unchanged signature)

### Dependencies
- gate: No dependencies (foundation)
- agent_end: Depends on [gate]
- analyze: Depends on [gate]

## Tasks

### Phase 0: Foundation
- [ ] Add `unattended()` to `hooks/gate.py` and `test_unattended_reads_only_the_exact_value` to `hooks/tests/test_gate.py` - the test passes for `"1"` and fails-closed for `"0"`, `"true"`, `""` and unset (monkeypatched environment).

### Phase 1: Core
- [ ] Gate `_fix_and_format` and `_slow_lint` in `hooks/agent_end.py` behind `not gate.unattended()` (depends on: Phase 0) - `test_unattended_stop_skips_fix_and_format` in `hooks/tests/test_hooks_inprocess.py` passes: a queued Python file with a fixable lint stays byte-identical, the queue is empty afterwards, and a pending nudge still prints.
- [ ] Gate `_fix_inline` and the queue append in `hooks/analyze.py` behind `not gate.unattended()` (depends on: Phase 0) - `test_unattended_analyze_reports_but_never_fixes` passes: the advisory finding is printed and recorded, `format_queue` stays empty, and with an immediate-fix config the file is byte-identical.
- [ ] Add the CHANGELOG entry and the README sentence (depends on: Phase 1 code tasks) - `rg -n 'CLAUDE_UNATTENDED' CHANGELOG.md README.md` returns one hit in each.

## Success Criteria

- `uv run --no-project --with pytest python -m pytest -q hooks/tests/test_gate.py hooks/tests/test_hooks_inprocess.py -k "unattended or deferred_fix or immediate_fix"` passes, including the two pre-existing interactive tests unchanged.
- `rg -l 'unattended' hooks --glob '*.py' --glob '!tests/*'` lists exactly `hooks/gate.py`, `hooks/agent_end.py`, `hooks/analyze.py`.
- After the next loupe release is installed, an autopilot batch's attempts ledger records no `reflow` entries (checked by the operator with `jq -c 'select(.attempt.reflow)' dev/local/autopilot/ledger/attempts.jsonl` on the loop repo).
