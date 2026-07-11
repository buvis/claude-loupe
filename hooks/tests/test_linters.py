"""Tests for hooks/loupe/linters.py.

Linters are stub executables planted on an isolated PATH; no real tool
is required. Canned outputs mirror shapes verified against real runs of
ruff 0.14, sqlfluff 3.x, shellcheck 0.11, and biome 2.5.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loupe import linters
from loupe import state as state_mod
from loupe.linters import FAST_LINTERS, SLOW_LINTERS, run_linter
from loupe.project import project_hash


class LinterTestCase(unittest.TestCase):
    """Isolated HOME and PATH so dispatch only sees planted stubs."""

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
        self.state = state_mod.default_state()

    def _plant_target(self, name: str, content: str = "x = 1\n") -> Path:
        target = self.project_dir / name
        target.write_text(content, encoding="utf-8")
        return target

    def _plant_linter(self, name: str, payload: str = "[]", exit_code: int = 0) -> None:
        # Python stubs with an absolute-interpreter shebang: the isolated
        # PATH holds no /bin, so shell builtins are all a stub could use.
        body = (
            f"#!{sys.executable}\n"
            "import sys\n"
            f"sys.stdout.write({payload!r})\n"
            f"raise SystemExit({exit_code})\n"
        )
        stub = self.bin_dir / name
        stub.write_text(body, encoding="utf-8")
        os.chmod(stub, 0o755)

    def _run(self, target: Path, language: str):
        return run_linter(str(target), language, {}, self.state)


class DispatchTests(LinterTestCase):
    def test_unknown_language_returns_nothing(self) -> None:
        target = self._plant_target("mystery.xyz")
        findings, state = self._run(target, "unknown")
        self.assertEqual(findings, [])
        self.assertIs(state, self.state)

    def test_markdown_has_no_fast_linter(self) -> None:
        target = self._plant_target("notes.md")
        findings, state = self._run(target, "markdown")
        self.assertEqual(findings, [])
        self.assertEqual(state["persistent"]["nudged"], [])

    def test_slow_linter_languages_are_not_dispatched_here(self) -> None:
        # clippy exists on PATH, yet rust must not run (Stop-queue concern)
        # and must not nudge either.
        self._plant_linter("clippy", payload="should never run")
        target = self._plant_target("lib.rs")
        findings, state = self._run(target, "rust")
        self.assertEqual(findings, [])
        self.assertEqual(state["persistent"]["nudged"], [])

    def test_absent_tool_skips_and_nudges_once(self) -> None:
        target = self._plant_target("app.py")
        findings, state = self._run(target, "python")
        self.assertEqual(findings, [])
        self.assertEqual(state["persistent"]["nudged"], ["ruff"])

        on_disk = state_mod.load_state(project_hash(target.parent))
        self.assertEqual(on_disk["persistent"]["nudged"], ["ruff"])

        again_findings, again_state = run_linter(str(target), "python", {}, state)
        self.assertEqual(again_findings, [])
        self.assertEqual(again_state["persistent"]["nudged"], ["ruff"])

    def test_javascript_nudges_biome_when_nothing_resolves(self) -> None:
        target = self._plant_target("app.js")
        _, state = self._run(target, "javascript")
        self.assertEqual(state["persistent"]["nudged"], ["biome"])

    def test_timeout_returns_no_findings(self) -> None:
        stub = self.bin_dir / "ruff"
        stub.write_text(
            f"#!{sys.executable}\nimport time\ntime.sleep(5)\n", encoding="utf-8"
        )
        os.chmod(stub, 0o755)
        target = self._plant_target("app.py")
        with mock.patch.object(linters, "LINTER_TIMEOUT_SECONDS", 0.2):
            findings, state = self._run(target, "python")
        self.assertEqual(findings, [])
        self.assertIs(state, self.state)

    def test_garbage_output_returns_no_findings(self) -> None:
        self._plant_linter("ruff", payload="ruff crashed: traceback", exit_code=2)
        target = self._plant_target("app.py")
        findings, _ = self._run(target, "python")
        self.assertEqual(findings, [])

    def test_state_is_untouched_when_tool_runs(self) -> None:
        self._plant_linter("ruff", payload="[]", exit_code=0)
        target = self._plant_target("app.py")
        _, state = self._run(target, "python")
        self.assertIs(state, self.state)
        self.assertEqual(state["persistent"]["nudged"], [])

    def test_slow_linters_contract_for_stop_queue(self) -> None:
        self.assertEqual(SLOW_LINTERS, {"rust": "clippy", "svelte": "svelte-check"})
        self.assertEqual(set(SLOW_LINTERS) & set(FAST_LINTERS), set())


class RuffParseTests(LinterTestCase):
    PAYLOAD = (
        '[{"code": "F401", "message": "`os` imported but unused",'
        ' "location": {"column": 8, "row": 1}},'
        ' {"code": "E501", "message": "Line too long",'
        ' "location": {"column": 89, "row": 3}}]'
    )

    def test_findings_parse_with_category_mapping(self) -> None:
        # Exit 1 mirrors real linters: nonzero when violations are found.
        self._plant_linter("ruff", payload=self.PAYLOAD, exit_code=1)
        target = self._plant_target("app.py")
        findings, _ = self._run(target, "python")

        self.assertEqual(len(findings), 2)
        unused, long_line = findings
        self.assertEqual(unused.category, "correctness")
        self.assertEqual(unused.message, "F401: `os` imported but unused")
        self.assertEqual(unused.line, 1)
        self.assertEqual(unused.path, str(target))
        self.assertEqual(long_line.category, "style")
        self.assertEqual(long_line.line, 3)


class BiomeParseTests(LinterTestCase):
    PAYLOAD = (
        "::error title=lint/suspicious/noDebugger,file=/p/app.js,line=3,"
        "endLine=3,col=3,endColumn=12::This is an unexpected use of the"
        " debugger statement.\n"
        "::warning title=lint/style/noVar,file=/p/app.js,line=1,endLine=1,"
        "col=1,endColumn=4::Use let or const instead of var.\n"
        "lint decoration line that is not a workflow command"
    )

    def test_biome_is_preferred_over_eslint(self) -> None:
        self._plant_linter("biome", payload=self.PAYLOAD, exit_code=1)
        self._plant_linter(
            "eslint",
            payload='[{"messages": [{"ruleId": "eslint-marker", "severity": 2,'
            ' "message": "x", "line": 9}]}]',
        )
        target = self._plant_target("app.js")
        findings, _ = self._run(target, "javascript")

        self.assertEqual(len(findings), 2)
        debugger_use, var_use = findings
        self.assertEqual(debugger_use.category, "correctness")
        self.assertEqual(debugger_use.severity, "error")
        self.assertEqual(debugger_use.line, 3)
        self.assertTrue(
            debugger_use.message.startswith("lint/suspicious/noDebugger:")
        )
        self.assertEqual(var_use.category, "style")
        self.assertEqual(var_use.severity, "warning")
        self.assertEqual(var_use.line, 1)


class EslintParseTests(LinterTestCase):
    PAYLOAD = (
        '[{"filePath": "/p/app.js", "messages": ['
        '{"ruleId": "no-unused-vars", "severity": 2,'
        ' "message": "x is not used", "line": 4},'
        '{"ruleId": "semi", "severity": 1, "message": "Missing semicolon",'
        ' "line": 7}]}]'
    )

    def test_eslint_runs_when_biome_is_absent(self) -> None:
        self._plant_linter("eslint", payload=self.PAYLOAD, exit_code=1)
        target = self._plant_target("app.js")
        findings, state = self._run(target, "javascript")

        self.assertEqual(len(findings), 2)
        error, warning = findings
        self.assertEqual(error.category, "correctness")
        self.assertEqual(error.severity, "error")
        self.assertEqual(error.message, "no-unused-vars: x is not used")
        self.assertEqual(error.line, 4)
        self.assertEqual(warning.category, "style")
        self.assertEqual(warning.severity, "warning")
        self.assertEqual(state["persistent"]["nudged"], [])


class StylelintParseTests(LinterTestCase):
    PAYLOAD = (
        '[{"source": "/p/app.css", "warnings": ['
        '{"line": 2, "column": 3, "rule": "block-no-empty",'
        ' "severity": "error", "text": "Unexpected empty block"}]}]'
    )

    def test_stylelint_findings_stay_style_category(self) -> None:
        self._plant_linter("stylelint", payload=self.PAYLOAD, exit_code=2)
        target = self._plant_target("app.css")
        findings, _ = self._run(target, "css")

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.category, "style")
        self.assertEqual(finding.severity, "error")
        self.assertEqual(finding.message, "block-no-empty: Unexpected empty block")
        self.assertEqual(finding.line, 2)


class SqlfluffParseTests(LinterTestCase):
    PAYLOAD = (
        '[{"filepath": "/p/q.sql", "violations": ['
        '{"start_line_no": 1, "start_line_pos": 1, "code": "LT09",'
        ' "description": "Select targets should be on a new line."},'
        '{"line_no": 4, "code": "CP01", "description": "Keywords must be'
        ' consistently upper case."}]}]'
    )

    def test_sqlfluff_handles_current_and_legacy_line_keys(self) -> None:
        self._plant_linter("sqlfluff", payload=self.PAYLOAD, exit_code=1)
        target = self._plant_target("q.sql")
        findings, _ = self._run(target, "sql")

        self.assertEqual(len(findings), 2)
        current, legacy = findings
        self.assertEqual(current.category, "style")
        self.assertEqual(
            current.message, "LT09: Select targets should be on a new line."
        )
        self.assertEqual(current.line, 1)
        self.assertEqual(legacy.line, 4)


class RubocopParseTests(LinterTestCase):
    PAYLOAD = (
        '{"files": [{"path": "app.rb", "offenses": ['
        '{"severity": "error", "message": "unexpected token",'
        ' "cop_name": "Lint/Syntax", "location": {"line": 2, "column": 1}},'
        '{"severity": "convention", "message": "Use snake_case.",'
        ' "cop_name": "Naming/MethodName", "location": {"line": 5, "column": 3}}'
        "]}]}"
    )

    def test_rubocop_severity_maps_to_category(self) -> None:
        self._plant_linter("rubocop", payload=self.PAYLOAD, exit_code=1)
        target = self._plant_target("app.rb")
        findings, _ = self._run(target, "ruby")

        self.assertEqual(len(findings), 2)
        syntax, naming = findings
        self.assertEqual(syntax.category, "correctness")
        self.assertEqual(syntax.severity, "error")
        self.assertEqual(syntax.message, "Lint/Syntax: unexpected token")
        self.assertEqual(syntax.line, 2)
        self.assertEqual(naming.category, "style")
        self.assertEqual(naming.severity, "convention")


class ShellcheckParseTests(LinterTestCase):
    PAYLOAD = (
        '[{"file": "/p/s.sh", "line": 2, "column": 6, "level": "error",'
        ' "code": 1073, "message": "Couldn\'t parse this function."},'
        '{"file": "/p/s.sh", "line": 4, "column": 5, "level": "info",'
        ' "code": 2086, "message": "Double quote to prevent globbing."}]'
    )

    def test_shellcheck_level_maps_to_category(self) -> None:
        self._plant_linter("shellcheck", payload=self.PAYLOAD, exit_code=1)
        target = self._plant_target("s.sh")
        findings, _ = self._run(target, "shell")

        self.assertEqual(len(findings), 2)
        parse_error, quoting = findings
        self.assertEqual(parse_error.category, "correctness")
        self.assertEqual(parse_error.message, "SC1073: Couldn't parse this function.")
        self.assertEqual(parse_error.line, 2)
        self.assertEqual(quoting.category, "style")
        self.assertEqual(quoting.severity, "info")
        self.assertEqual(quoting.line, 4)


if __name__ == "__main__":
    unittest.main()
