"""Tests for hooks/loupe/astgrep.py.

ast-grep is a stub executable planted on an isolated PATH; the canned
JSON mirrors the shape verified against a real ast-grep 0.44 run
(0-based range lines, ruleId/severity/message fields). The rule pack
itself is exercised against the real binary in test_rulepack.py.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loupe import astgrep
from loupe import state as state_mod
from loupe.astgrep import DEFAULT_RULES_DIR, FILE_LEVEL_LINE, run_astgrep
from loupe.project import project_hash

PAYLOAD = (
    '[{"ruleId": "security-python-eval", "severity": "error",'
    ' "message": "eval on dynamic input",'
    ' "range": {"start": {"line": 3, "column": 0}}},'
    ' {"ruleId": "stub-python-pass-only-body", "severity": "error",'
    ' "message": "stub body",'
    ' "range": {"start": {"line": 7, "column": 0}}},'
    ' {"ruleId": "weird-unprefixed-rule", "severity": "hint",'
    ' "message": "odd",'
    ' "range": {"start": {"line": 0, "column": 0}}}]'
)


class AstgrepTestCase(unittest.TestCase):
    """Isolated HOME and PATH so resolution only sees the planted stub."""

    def setUp(self) -> None:
        home_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(home_tmp.cleanup)
        self.home = Path(home_tmp.name)
        self.bin_dir = self.home / "bin"
        self.bin_dir.mkdir()
        env = mock.patch.dict(
            os.environ, {"HOME": home_tmp.name, "PATH": str(self.bin_dir)}
        )
        env.start()
        self.addCleanup(env.stop)

        self.project_dir = self.home / "proj"
        self.project_dir.mkdir()
        self.target = self.project_dir / "app.py"
        self.target.write_text("x = 1\n", encoding="utf-8")
        self.rules_dir = self.home / "rules"
        self.rules_dir.mkdir()

    def _plant_astgrep(self, payload: str = "[]", exit_code: int = 0) -> None:
        body = (
            f"#!{sys.executable}\n"
            "import sys\n"
            f"sys.stdout.write({payload!r})\n"
            f"raise SystemExit({exit_code})\n"
        )
        stub = self.bin_dir / "ast-grep"
        stub.write_text(body, encoding="utf-8")
        os.chmod(stub, 0o755)

    def _plant_argv_capture(self, capture: Path) -> None:
        body = (
            f"#!{sys.executable}\n"
            "import sys\n"
            f"open({str(capture)!r}, 'w').write(chr(10).join(sys.argv[1:]))\n"
            "sys.stdout.write('[]')\n"
        )
        stub = self.bin_dir / "ast-grep"
        stub.write_text(body, encoding="utf-8")
        os.chmod(stub, 0o755)


class ParseTests(AstgrepTestCase):
    def test_categories_come_from_rule_id_prefix(self) -> None:
        # Exit 1 mirrors the real binary when error-severity rules match.
        self._plant_astgrep(payload=PAYLOAD, exit_code=1)
        findings = run_astgrep(str(self.target), "python", self.rules_dir)

        self.assertEqual(len(findings), 3)
        security, stub, unknown = findings
        self.assertEqual(security.category, "security")
        self.assertEqual(security.severity, "error")
        self.assertEqual(
            security.message, "security-python-eval: eval on dynamic input"
        )
        self.assertEqual(stub.category, "stub")
        self.assertEqual(unknown.category, "style")
        self.assertEqual(unknown.severity, "hint")

    def test_lines_convert_from_zero_based(self) -> None:
        self._plant_astgrep(payload=PAYLOAD, exit_code=1)
        findings = run_astgrep(str(self.target), "python", self.rules_dir)
        self.assertEqual([f.line for f in findings], [4, 8, 1])

    def test_clean_scan_yields_no_findings(self) -> None:
        self._plant_astgrep(payload="[]")
        self.assertEqual(
            run_astgrep(str(self.target), "python", self.rules_dir), []
        )


class FailurePolicyTests(AstgrepTestCase):
    def test_crash_yields_one_advisory_warning(self) -> None:
        self._plant_astgrep(payload="thread panicked at rule parse", exit_code=101)
        findings = run_astgrep(str(self.target), "python", self.rules_dir)

        self.assertEqual(len(findings), 1)
        advisory = findings[0]
        self.assertEqual(advisory.category, "style")
        self.assertEqual(advisory.severity, "warning")
        self.assertIn("exit 101", advisory.message)
        self.assertEqual(advisory.line, FILE_LEVEL_LINE)
        self.assertEqual(advisory.path, str(self.target))

    def test_non_list_json_yields_one_advisory_warning(self) -> None:
        self._plant_astgrep(payload='{"error": "bad config"}')
        findings = run_astgrep(str(self.target), "python", self.rules_dir)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "style")

    def test_timeout_yields_one_advisory_warning(self) -> None:
        stub = self.bin_dir / "ast-grep"
        stub.write_text(
            f"#!{sys.executable}\nimport time\ntime.sleep(5)\n", encoding="utf-8"
        )
        os.chmod(stub, 0o755)
        with mock.patch.object(astgrep, "ASTGREP_TIMEOUT_SECONDS", 0.2):
            findings = run_astgrep(str(self.target), "python", self.rules_dir)
        self.assertEqual(len(findings), 1)
        self.assertIn("timeout", findings[0].message)


class DispatchTests(AstgrepTestCase):
    def test_uncovered_language_skips_without_spawning(self) -> None:
        self._plant_astgrep(payload=PAYLOAD, exit_code=1)
        self.assertEqual(run_astgrep(str(self.target), "css", self.rules_dir), [])
        self.assertEqual(
            run_astgrep(str(self.target), "unknown", self.rules_dir), []
        )

    def test_absent_binary_skips_and_nudges_once(self) -> None:
        findings = run_astgrep(str(self.target), "python", self.rules_dir)
        self.assertEqual(findings, [])

        project = project_hash(self.target.parent)
        on_disk = state_mod.load_state(project)
        self.assertEqual(on_disk["persistent"]["nudged"], ["ast-grep"])

        run_astgrep(str(self.target), "python", self.rules_dir)
        on_disk = state_mod.load_state(project)
        self.assertEqual(on_disk["persistent"]["nudged"], ["ast-grep"])

    def test_command_points_at_given_rules_dir(self) -> None:
        capture = self.home / "argv.txt"
        self._plant_argv_capture(capture)
        run_astgrep(str(self.target), "python", self.rules_dir)

        argv = capture.read_text(encoding="utf-8").splitlines()
        self.assertEqual(argv[0], "scan")
        self.assertIn("--config", argv)
        self.assertIn(str(self.rules_dir / "sgconfig.yml"), argv)
        self.assertIn("--json", argv)
        self.assertIn(str(self.target), argv)

    def test_default_rules_dir_is_the_packaged_pack(self) -> None:
        capture = self.home / "argv.txt"
        self._plant_argv_capture(capture)
        run_astgrep(str(self.target), "python")

        argv = capture.read_text(encoding="utf-8").splitlines()
        self.assertIn(str(DEFAULT_RULES_DIR / "sgconfig.yml"), argv)
        self.assertEqual(DEFAULT_RULES_DIR.name, "ast-grep")


if __name__ == "__main__":
    unittest.main()
