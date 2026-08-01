"""Tests for the loupe command helpers.

Covers /loupe-report, /loupe-toggle, /loupe-show-tdi, /loupe-check-tools
and /loupe-check-health. (/loupe-allow-edit is exercised in
test_readguard.py, beside the guard whose behavior it changes.)

Subprocess classes prove the scripts work the way the command markdown
invokes them (python3 <script> from the project directory); in-process
classes cover the same logic where coverage can measure it.
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_tools
import report
import show_tdi
import toggle
from loupe import state as state_mod
from loupe.project import project_hash

HOOKS_DIR = Path(__file__).resolve().parents[1]


class CommandTestCase(unittest.TestCase):
    """Isolated HOME/PATH and a temp project to run the helpers against."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.bin_dir = self.home / "bin"
        self.bin_dir.mkdir()
        env = mock.patch.dict(
            os.environ, {"HOME": str(self.home), "PATH": str(self.bin_dir)}
        )
        env.start()
        self.addCleanup(env.stop)
        self.project = self.home / "proj"
        (self.project / ".git").mkdir(parents=True)

    def run_helper(self, script: str):
        return subprocess.run(
            [sys.executable, str(HOOKS_DIR / script)],
            cwd=str(self.project),
            env={"HOME": str(self.home), "PATH": str(self.bin_dir)},
            capture_output=True,
            text=True,
            timeout=60,
        )

    def call_inprocess(self, module) -> tuple:
        stdout = io.StringIO()
        with mock.patch("os.getcwd", return_value=str(self.project)):
            with contextlib.redirect_stdout(stdout):
                code = module.main()
        return code, stdout.getvalue()

    def override_path(self) -> Path:
        return self.project / ".claude" / "loupe.json"

    def read_override(self) -> dict:
        return json.loads(self.override_path().read_text(encoding="utf-8"))

    def seed_state(self, runtime=None, persistent=None) -> None:
        state = state_mod.default_state()
        state["runtime"].update(runtime or {})
        state["persistent"].update(persistent or {})
        state_mod.save_state(project_hash(self.project), state)


class ReportTests(CommandTestCase):
    def test_fresh_project_reports_empty_sections(self) -> None:
        code, out = self.call_inprocess(report)
        self.assertEqual(code, 0)
        self.assertIn(f"project {project_hash(self.project)}", out)
        self.assertIn("enabled: True", out)
        self.assertIn("session findings: none", out)
        self.assertIn("format queue: empty", out)
        self.assertIn("tool nudges: none", out)
        self.assertIn("ast-grep: missing", out)

    def test_findings_count_by_category(self) -> None:
        self.seed_state(
            runtime={
                "findings": [
                    {"category": "stub"},
                    {"category": "style"},
                    {"category": "style"},
                ],
                "format_queue": ["a.py", "b.rs"],
            },
            persistent={
                "nudged": ["ruff", "shellcheck"],
                "nudge_reported": ["ruff"],
            },
        )
        code, out = self.call_inprocess(report)
        self.assertEqual(code, 0)
        self.assertIn("stub: 1", out)
        self.assertIn("style: 2", out)
        self.assertIn("format queue: 2 file(s)", out)
        self.assertIn("a.py", out)
        self.assertIn("ruff (reported)", out)
        self.assertIn("shellcheck (pending)", out)

    def test_resolved_tool_shows_its_path(self) -> None:
        planted = self.bin_dir / "ruff"
        planted.write_text("#!/bin/sh\n", encoding="utf-8")
        os.chmod(planted, 0o755)
        _, out = self.call_inprocess(report)
        self.assertIn(f"ruff: {planted}", out)

    def test_disabled_project_still_reports(self) -> None:
        self.override_path().parent.mkdir(parents=True)
        self.override_path().write_text('{"enabled": false}', encoding="utf-8")
        code, out = self.call_inprocess(report)
        self.assertEqual(code, 0)
        self.assertIn("enabled: False", out)

    def test_runs_as_a_subprocess_the_way_the_command_invokes_it(self) -> None:
        result = self.run_helper("report.py")
        self.assertEqual(result.returncode, 0)
        self.assertIn("loupe report", result.stdout)
        self.assertIn("tool health:", result.stdout)


class ToggleTests(CommandTestCase):
    def test_first_toggle_disables_an_enabled_project(self) -> None:
        code, out = self.call_inprocess(toggle)
        self.assertEqual(code, 0)
        self.assertIn("loupe is now disabled", out)
        self.assertEqual(self.read_override()["enabled"], False)

    def test_second_toggle_reenables(self) -> None:
        self.call_inprocess(toggle)
        code, out = self.call_inprocess(toggle)
        self.assertEqual(code, 0)
        self.assertIn("loupe is now enabled", out)
        self.assertEqual(self.read_override()["enabled"], True)

    def test_toggle_preserves_unrelated_override_keys(self) -> None:
        self.override_path().parent.mkdir(parents=True)
        self.override_path().write_text(
            '{"immediate_fix": true}', encoding="utf-8"
        )
        self.call_inprocess(toggle)
        override = self.read_override()
        self.assertEqual(override["immediate_fix"], True)
        self.assertEqual(override["enabled"], False)

    def test_toggle_flips_a_global_disable_locally(self) -> None:
        global_config = self.home / ".claude" / "loupe" / "config.json"
        global_config.parent.mkdir(parents=True)
        global_config.write_text('{"enabled": false}', encoding="utf-8")
        code, out = self.call_inprocess(toggle)
        self.assertEqual(code, 0)
        self.assertIn("loupe is now enabled", out)
        self.assertEqual(self.read_override()["enabled"], True)

    def test_malformed_override_is_replaced(self) -> None:
        self.override_path().parent.mkdir(parents=True)
        self.override_path().write_text("{{{ not json", encoding="utf-8")
        code, _ = self.call_inprocess(toggle)
        self.assertEqual(code, 0)
        self.assertEqual(self.read_override(), {"enabled": False})

    def test_runs_as_a_subprocess_the_way_the_command_invokes_it(self) -> None:
        result = self.run_helper("toggle.py")
        self.assertEqual(result.returncode, 0)
        self.assertIn("loupe is now disabled", result.stdout)
        self.assertEqual(self.read_override()["enabled"], False)


class ShowTdiTests(CommandTestCase):
    def test_empty_history_says_it_cannot_tell_which(self) -> None:
        """No entries means "clean" or "never ran"; do not imply zero debt."""
        code, out = self.call_inprocess(show_tdi)
        self.assertEqual(code, 0)
        self.assertIn("no history yet", out)
        self.assertIn("/loupe-check-health", out)

    def test_renders_totals_direction_and_breakdown(self) -> None:
        self.seed_state(
            persistent={
                "tdi_history": [
                    {
                        "ts": "2026-08-02T09:00:00Z",
                        "counts": {"stub": 2},
                        "total": 2,
                    },
                    {
                        "ts": "2026-08-02T09:15:00Z",
                        "counts": {"style": 3, "stub": 2},
                        "total": 5,
                    },
                ]
            }
        )
        code, out = self.call_inprocess(show_tdi)
        self.assertEqual(code, 0)
        self.assertIn("latest turn: 5 finding(s) (worse vs previous turn)", out)
        self.assertIn("lifetime: 7 finding(s) over 2 recorded turn(s)", out)
        self.assertIn("2026-08-02T09:15:00Z", out)
        self.assertIn("stub: 2, style: 3", out)

    def test_single_entry_reads_as_unchanged(self) -> None:
        self.seed_state(
            persistent={
                "tdi_history": [
                    {"ts": "2026-08-02T09:00:00Z", "counts": {"stub": 1}, "total": 1}
                ]
            }
        )
        _, out = self.call_inprocess(show_tdi)
        self.assertIn("unchanged vs previous turn", out)

    def test_runs_as_a_subprocess_the_way_the_command_invokes_it(self) -> None:
        result = self.run_helper("show_tdi.py")
        self.assertEqual(result.returncode, 0)
        self.assertIn("loupe TDI", result.stdout)


class CheckToolsTests(CommandTestCase):
    def _language_line(self, out: str, language: str) -> str:
        return next(
            line
            for line in out.splitlines()
            if line.strip().startswith(f"{language}:")
        )

    def test_reports_every_language_and_flags_missing_tools(self) -> None:
        code, out = self.call_inprocess(check_tools)
        self.assertEqual(code, 0)
        self.assertIn("per language:", out)
        self.assertIn("python:", out)
        self.assertIn("MISSING", out)

    def test_renders_tool_names_not_container_reprs(self) -> None:
        """FAST_LINTERS values are tuples; rendering the tuple instead of
        its names silently broke every lint-slot lookup once."""
        _, out = self.call_inprocess(check_tools)
        self.assertNotIn("('", out)
        self.assertIn("lint ruff", self._language_line(out, "python"))

    def test_present_tool_reads_ok_in_every_slot_that_uses_it(self) -> None:
        binary = self.bin_dir / "ruff"
        binary.write_text(f"#!{sys.executable}\n", encoding="utf-8")
        os.chmod(binary, 0o755)
        _, out = self.call_inprocess(check_tools)
        python = self._language_line(out, "python")
        self.assertIn("lint ruff (ok)", python)
        self.assertIn("fix ruff (ok)", python)
        self.assertNotIn("MISSING", python)

    def test_clippy_resolves_through_cargo(self) -> None:
        binary = self.bin_dir / "cargo"
        binary.write_text(f"#!{sys.executable}\n", encoding="utf-8")
        os.chmod(binary, 0o755)
        _, out = self.call_inprocess(check_tools)
        self.assertIn("slow lint clippy (ok)", self._language_line(out, "rust"))

    def test_calls_out_astgrep_as_the_pack_blocker(self) -> None:
        """With no ast-grep on PATH the whole rule pack is inert; say so."""
        code, out = self.call_inprocess(check_tools)
        self.assertEqual(code, 0)
        self.assertIn("ast-grep: MISSING", out)
        self.assertIn("rule pack is inert", out)

    def test_lists_both_javascript_autofix_candidates(self) -> None:
        _, out = self.call_inprocess(check_tools)
        javascript = next(
            line for line in out.splitlines() if line.strip().startswith("javascript:")
        )
        self.assertIn("biome", javascript)
        self.assertIn("eslint", javascript)

    def test_runs_as_a_subprocess_the_way_the_command_invokes_it(self) -> None:
        result = self.run_helper("check_tools.py")
        self.assertEqual(result.returncode, 0)
        self.assertIn("loupe tool check", result.stdout)


class CheckHealthTests(CommandTestCase):
    def test_fails_when_astgrep_is_absent(self) -> None:
        """A health check that reports ok while the pack cannot run is the
        one failure mode it must never have."""
        result = self.run_helper("check_health.py")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ast-grep not found", result.stdout)
        self.assertIn("FAIL: rule pack", result.stdout)

    def test_engine_modules_and_entry_points_resolve(self) -> None:
        result = self.run_helper("check_health.py")
        self.assertIn("ok all", result.stdout)
        self.assertIn("modules import", result.stdout)
        self.assertIn("registered entry points exist", result.stdout)

    def test_passes_when_astgrep_is_present(self) -> None:
        binary = self.bin_dir / "ast-grep"
        binary.write_text(f"#!{sys.executable}\n", encoding="utf-8")
        os.chmod(binary, 0o755)
        result = self.run_helper("check_health.py")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("loupe is wired correctly", result.stdout)


if __name__ == "__main__":
    unittest.main()
