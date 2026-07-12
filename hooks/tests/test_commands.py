"""Tests for the /loupe-report and /loupe-toggle command helpers.

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

import report
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


if __name__ == "__main__":
    unittest.main()
