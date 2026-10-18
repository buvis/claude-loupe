---
prd: docs/dev/project-management/prds/wip/00001-honor-unattended-sessions-v1.md
review: 1
date: 2026-10-18
head_sha: e3c25f9081641b8baf6c0daefe8f027bdd6de659
codex_thread_id: 01a150e7-6448-7273-81f3-0a68ca242231
reviewers: alice,blake,bob,carl
agents:
  alice: available
  blake: available
  bob: available
  carl: available
dispatch_rows:
  bob: 626ae90b
  carl: b3f3b33a
---

# Review: 00001-honor-unattended-sessions-v1

Diff range: `43410230e0c6eef53da4272c081136c66f5ce857..e3c25f9081641b8baf6c0daefe8f027bdd6de659`

codex_rung_guard: not fired

## Review Summary

Reviewed: 4 completed tasks
PRDs checked: 00001-honor-unattended-sessions-v1.md

### Agent Status

- Alice: ✅ Available (consensus lens, legacy engine)
- Blake: ✅ Available (blind lens, PRD-only)
- Bob: ✅ Available (codex, doubt + de-slop lens)
- Carl: ✅ Available (gemini CLI backend)

### Cycle notes

- Engram context pack unavailable this cycle: `pack: failed (engram pack exit 1: not inside a registered repo)`. Review degraded, not invalid; `(no pack available this cycle)` was substituted for the pack placeholders.
- The `review-stage` call omitted `--replay-cmd`, so the fail-first replay was run separately with `replay_tests_against_base.py --base 43410230e0c6 --cmd "uv run --no-project --with pytest python -m pytest"`. Its `[MECH]` lines are absorbed as R12-R14 below.
- Tautological-shape check: 68 test functions in 3 test files, no `[MECH]` lines.
- Flaky suite observation (orchestrator, not a reviewer finding): repeated full `pytest` runs at repo root fail non-deterministically in untouched files under machine load — Carl's run failed `hooks/tests/test_tools.py::test_resolves_via_mise_which_as_last_resort`, a later run failed three `hooks/tests/test_astgrep.py::ParseTests` cases with "ast-grep did not complete within the timeout". Both files are outside this PRD's diff, and the `unittest` gate ran green twice (313 tests, OK). Recorded as a pre-existing flakiness note, not charged to this PRD.

## Consolidated Findings

| Ref | Consensus | Severity | Issue | File | Task | Found By |
|-----|-----------|----------|-------|------|------|----------|
| R1 | [2/4] | 🟡 | Module docstring still states every analyzed file is queued "unless `immediate_fix` is on and nothing blocks" - the new unattended exception is missing, so the hook's contract doc is now wrong | hooks/analyze.py:11 | 3 | ALICE, BLAKE |
| R2 | [2/4] | 🟡 | PRD acceptance criterion "still prints ... the TDI line when there is something to report" has no test: the unattended Stop test plants `ast-grep` returning `[]` and ruff is absent during the analyze calls, so `findings` is empty and the TDI branch never executes | hooks/tests/test_entrypoints.py:276 | 2 | ALICE, BLAKE |
| R3 | [2/4] | ⚪ | Pre-existing, not introduced: `_finish_turn` is 63 lines, over the 50-line guideline (64 at base, so the diff improved it by one). Flagging per the surface-pre-existing-smells rule, not as rework for this PRD | hooks/agent_end.py:45 | general | ALICE, BOB |
| R4 | [1/4] | 🟡 | Module docstring still states the Stop hook drains the queue and gives "every queued file ... the safe autofixer plus the config-gated formatter" plus one slow-linter run per language; no mention of the unattended skip | hooks/agent_end.py:5 | 2 | ALICE |
| R5 | [1/4] | 🟡 | Phase 1 acceptance criterion places `test_unattended_stop_skips_fix_and_format` in `hooks/tests/test_hooks_inprocess.py`; it landed in `test_entrypoints.py` instead, so the PRD's own Success Criteria command collects only 3 tests and exercises neither the unattended Stop nor the interactive `test_stop_runs_deferred_fix_and_format_exactly_once` it claims to cover (ran it: "3 passed, 46 deselected") | hooks/tests/test_entrypoints.py:250 | 2 | BLAKE |
| R6 | [1/4] | 🟡 | Unattended Stop tests omit slow-lint suppression and TDI reporting/persistence, leaving required behavior untested. Add queued Rust or Svelte input and seeded findings; assert no slow-linter invocation and preserved TDI output/history. | hooks/tests/test_entrypoints.py:250 | 2 | BOB |
| R7 | [1/4] | ⚪ | README claims nudges still print under unattended, but `record_nudge` for cargo/clippy and svelte-check only fires inside the now-skipped `_slow_lint`, so those two nudges are never recorded in an unattended session | README.md:60 | 4 | ALICE |
| R8 | [1/4] | ⚪ | Diff carries ~40 lines of unrelated trailing-comma formatter churn across agent_end.py and three test files (e.g. the `queue = [...]` collapse), none of it traceable to the request; isolated in commit e3c25f9 but still noise in the reviewed diff | hooks/agent_end.py:52 | general | ALICE |
| R9 | [1/4] | ⚪ | Unattended Stop clears `format_queue` before deciding to skip the work, so any file queued by an earlier interactive turn in the same session loses its deferred fix permanently (no requeue, no retention). Spec says "clears the queue", so this is intended, but the data loss is silent and nothing logs it | hooks/agent_end.py:70 | 2 | BLAKE |
| R10 | [1/4] | ⚪ | PRD Success Criteria check `rg -l 'unattended' hooks --glob '*.py' --glob '!tests/*'` returns six files, not the three claimed: the glob contains a slash so ripgrep anchors it at the search root and it never excludes `hooks/tests/`. Intent holds (exactly `gate.py`, `agent_end.py`, `analyze.py` among non-test modules); the literal criterion does not | N/A | general | BLAKE |
| R11 | [1/4] | ⚪ | Unrelated formatter churn rode along in the PRD diff (trailing-comma/reflow hunks in `agent_end.py` and ~15 test hunks, plus a dedicated `style(hooks)` commit at HEAD). Harmless, but it is exactly the uncommitted-rewrite noise this PRD exists to stop, and it dilutes the reviewable diff | hooks/agent_end.py:52 | general | BLAKE |
| R12 | [1/4] | 🟡 | 5 touched test(s) pass against the pre-change code: test_blocking_findings_still_land_in_session_state, test_advisory_file_is_queued_for_stop, test_advisory_finding_prints_inline_and_passes, test_unknown_fields_exit_zero, test_session_start_fails_open_when_state_cannot_persist | hooks/tests/test_entrypoints.py | general | mech-check |
| R13 | [1/4] | 🟡 | 3 touched test(s) pass against the pre-change code: test_parity_from_a_nested_directory, test_parity_without_a_git_marker, test_gate_imports_only_the_stdlib | hooks/tests/test_gate.py | general | mech-check |
| R14 | [1/4] | 🟡 | 14 touched test(s) pass against the pre-change code: test_compact_keeps_the_turns_queue, test_disabled_project_is_untouched, test_poisoned_engine_fails_open, test_resume_resets_runtime, test_startup_resets_runtime_and_prints_nothing +8 more | hooks/tests/test_hooks_inprocess.py | general | mech-check |

Fail-first replay totals: 25 touched tests ran against base, 3 failed there (the three new unattended tests, which therefore pin this change), 22 passed. Every passing one lives in a file this diff touched only with formatter churn.

## Alice

Verified end to end: `gate.unattended()` reads only `"1"` (hooks/gate.py:64); `agent_end.py` gates `_fix_and_format` and `_slow_lint` behind `queue and not gate.unattended()` after the claim/save, so the queue still clears and nudges/TDI still flow; `analyze.py` suppresses both `fix_now` and the queue append. CHANGELOG and README are in place and correctly scoped.

Evidence run, not reasoned: full suite `313 passed, 198 subtests passed`; fail-first replay in a throwaway base worktree gave `3 failed, 65 deselected` with the right causes (`module 'gate' has no attribute 'unattended'`, file rewritten, `'autofix' unexpectedly found`); `_finish_turn` measures 63 lines now against 64 at base, so the diff shrank the one pre-existing overrun.

Findings: R1, R2, R3, R4, R7, R8 (see table).

R1: fail
R2: pass
R3: pass
R4: pass
R6: pass
R7: pass
R8: pass
R9: pass
R10: pass
R11: pass
R12: pass
R13: pass

R1 fails only on the untested TDI-under-unattended criterion.

## Blake

Blind, PRD-only. Located and read `hooks/gate.py`, `hooks/agent_end.py`, `hooks/analyze.py`, the three test files, `CHANGELOG.md`, `README.md`. Production diff since the PRD-filing commit is 22 changed lines across the three named modules and nothing else.

Verified: exact-value-only predicate, stdlib `os` only, import-light contract intact; Stop gating with claim/clear and TDI banking ahead of the gate; analyze gating that leaves linting, classification, state recording and the blocking exit 2 untouched; both named pre-existing interactive tests unmodified and passing; CHANGELOG under `[Unreleased]` / `### Changed` prefixed `**loupe**:`; README sentence in the configuration section. Ambient-env robustness holds: `env CLAUDE_UNATTENDED=1` over the three test files gave 68 passed, 60 subtests passed. No new flags, config keys, dependencies or schema changes.

No Critical or High findings. Findings: R1, R2, R5, R9, R10, R11 (see table).

B1: pass
B2: pass
B3: pass
B4: pass
B5: pass
B6: pass
B7: pass
B8: pass
B9: pass
B10: pass
B11: pass
B12: pass
B13: pass
B14: pass
B15: fail
B16: pass
B17: pass
B18: pass
B19: pass

B15 fails on the Phase 1 test-location criterion and the resulting hole in the PRD's own verification command, not on behavior.

## Bob

Doubt + de-slop lens (codex, static sandbox). Findings: R6, R3 (see table).

FIX:
- Missing unattended Stop coverage — hooks/tests/test_entrypoints.py:250 — Add assertions for slow-linter suppression, TDI output, and persisted TDI history.

VERIFY:
- (none)

KNOWN:
- `_finish_turn` exceeds 50 lines — hooks/agent_end.py:45 — Pre-existing size violation; restructuring this lightly modified function is outside this change's scope.

R1: fail
R2: pass
R3: pass
R4: pass
R6: pass
R7: pass
R8: pass
R9: pass
R10: pass
R11: pass
R12: fail
R13: pass

D1: pass
D2: pass
D3: pass
D4: pass
D5: pass

## Carl

Gemini backend. `[CARL] ✅ No issues found`. He independently reproduced the PRD success-criteria command and the `rg -l` criterion, and flagged neither as blocking.

R1: pass
R2: pass
R3: pass
R4: pass
R6: pass
R7: pass
R8: pass
R9: pass
R10: pass
R11: pass
R12: pass
R13: pass

Verdict: 14 findings
Tests: 313 passed, 0 failed, 0 skipped (suite run this cycle)
