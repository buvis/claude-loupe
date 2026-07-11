"""Tests for hooks/loupe/formatters.py.

Fixers and formatters are stub executables on an isolated PATH; config
files are planted per test to drive nearest-config-wins resolution.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loupe import formatters
from loupe.formatters import apply_autofix, apply_formatters, format_summary


class FormatterTestCase(unittest.TestCase):
    """Isolated HOME/PATH plus a .git-rooted project tree."""

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

        self.project = self.home / "proj"
        (self.project / ".git").mkdir(parents=True)
        self.subdir = self.project / "pkg"
        self.subdir.mkdir()

    def _plant_target(self, name: str, directory: Path | None = None) -> Path:
        target = (directory or self.project) / name
        target.write_text("original\n", encoding="utf-8")
        return target

    def _plant_tool(
        self, name: str, mutate: bool = True, capture: Path | None = None
    ) -> None:
        lines = [f"#!{sys.executable}", "import sys"]
        if capture is not None:
            lines.append(
                f"open({str(capture)!r}, 'w')" ".write(chr(10).join(sys.argv[1:]))"
            )
        if mutate:
            lines.append("open(sys.argv[-1], 'a').write('# fixed' + chr(10))")
        stub = self.bin_dir / name
        stub.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.chmod(stub, 0o755)

    def _argv(self, capture: Path) -> list[str]:
        return capture.read_text(encoding="utf-8").splitlines()


class AutofixTests(FormatterTestCase):
    def test_python_runs_ruff_check_fix(self) -> None:
        capture = self.home / "argv.txt"
        self._plant_tool("ruff", capture=capture)
        target = self._plant_target("app.py")

        result = apply_autofix(str(target), "python", {})

        self.assertEqual(result["tool"], "ruff")
        self.assertEqual(result["status"], "changed")
        self.assertEqual(result["step"], "autofix")
        self.assertEqual(self._argv(capture), ["check", "--fix", str(target)])

    def test_biome_is_preferred_over_eslint(self) -> None:
        capture = self.home / "argv.txt"
        self._plant_tool("biome", capture=capture)
        self._plant_tool("eslint")
        target = self._plant_target("app.js")

        result = apply_autofix(str(target), "javascript", {})

        self.assertEqual(result["tool"], "biome")
        self.assertEqual(self._argv(capture), ["check", "--write", str(target)])

    def test_eslint_runs_when_biome_is_absent(self) -> None:
        capture = self.home / "argv.txt"
        self._plant_tool("eslint", capture=capture)
        target = self._plant_target("app.js")

        result = apply_autofix(str(target), "javascript", {})

        self.assertEqual(result["tool"], "eslint")
        self.assertEqual(self._argv(capture), ["--fix", str(target)])

    def test_languages_without_safe_fixers_skip(self) -> None:
        target = self._plant_target("lib.rs")
        for language in ("rust", "svelte", "markdown", "unknown"):
            with self.subTest(language=language):
                result = apply_autofix(str(target), language, {})
                self.assertEqual(result["status"], "skipped")
                self.assertIsNone(result["tool"])

    def test_absent_tool_skips(self) -> None:
        target = self._plant_target("app.py")
        result = apply_autofix(str(target), "python", {})
        self.assertEqual(result["status"], "skipped")
        self.assertIsNone(result["tool"])

    def test_no_op_run_reports_unchanged(self) -> None:
        self._plant_tool("ruff", mutate=False)
        target = self._plant_target("app.py")
        result = apply_autofix(str(target), "python", {})
        self.assertEqual(result["status"], "unchanged")

    def test_timeout_reports_failed(self) -> None:
        stub = self.bin_dir / "ruff"
        stub.write_text(
            f"#!{sys.executable}\nimport time\ntime.sleep(5)\n", encoding="utf-8"
        )
        os.chmod(stub, 0o755)
        target = self._plant_target("app.py")
        with mock.patch.object(formatters, "FORMAT_TIMEOUT_SECONDS", 0.2):
            result = apply_autofix(str(target), "python", {})
        self.assertEqual(result["status"], "failed")

    def test_missing_target_reports_failed(self) -> None:
        self._plant_tool("ruff")
        result = apply_autofix(str(self.project / "ghost.py"), "python", {})
        self.assertEqual(result["status"], "failed")


class FormatterResolutionTests(FormatterTestCase):
    def test_unconfigured_python_defaults_to_ruff_format(self) -> None:
        capture = self.home / "argv.txt"
        self._plant_tool("ruff", capture=capture)
        target = self._plant_target("app.py")

        result = apply_formatters(str(target), {})

        self.assertEqual(result["tool"], "ruff")
        self.assertEqual(result["status"], "changed")
        self.assertEqual(result["step"], "format")
        self.assertEqual(self._argv(capture), ["format", str(target)])

    def test_pyproject_black_section_selects_black(self) -> None:
        (self.project / "pyproject.toml").write_text(
            "[tool.black]\nline-length = 100\n", encoding="utf-8"
        )
        capture = self.home / "argv.txt"
        self._plant_tool("black", capture=capture)
        target = self._plant_target("app.py")

        result = apply_formatters(str(target), {})

        self.assertEqual(result["tool"], "black")
        self.assertEqual(self._argv(capture), [str(target)])

    def test_pyproject_ruff_section_selects_ruff(self) -> None:
        (self.project / "pyproject.toml").write_text(
            "[tool.ruff]\nline-length = 100\n", encoding="utf-8"
        )
        self._plant_tool("ruff")
        target = self._plant_target("app.py")
        self.assertEqual(apply_formatters(str(target), {})["tool"], "ruff")

    def test_nearest_config_wins_over_project_root(self) -> None:
        (self.project / "pyproject.toml").write_text(
            "[tool.black]\n", encoding="utf-8"
        )
        (self.subdir / "ruff.toml").write_text("", encoding="utf-8")
        self._plant_tool("ruff")
        self._plant_tool("black")
        target = self._plant_target("nested.py", directory=self.subdir)

        self.assertEqual(apply_formatters(str(target), {})["tool"], "ruff")

    def test_nearest_prettier_beats_root_biome(self) -> None:
        (self.project / "biome.json").write_text("{}", encoding="utf-8")
        (self.subdir / ".prettierrc").write_text("{}", encoding="utf-8")
        capture = self.home / "argv.txt"
        self._plant_tool("prettier", capture=capture)
        self._plant_tool("biome")
        target = self._plant_target("app.js", directory=self.subdir)

        result = apply_formatters(str(target), {})

        self.assertEqual(result["tool"], "prettier")
        self.assertEqual(self._argv(capture), ["--write", str(target)])

    def test_biome_config_selects_biome_format(self) -> None:
        (self.project / "biome.json").write_text("{}", encoding="utf-8")
        capture = self.home / "argv.txt"
        self._plant_tool("biome", capture=capture)
        target = self._plant_target("app.js")

        result = apply_formatters(str(target), {})

        self.assertEqual(result["tool"], "biome")
        self.assertEqual(self._argv(capture), ["format", "--write", str(target)])

    def test_package_json_prettier_key_counts_as_config(self) -> None:
        (self.project / "package.json").write_text(
            '{"name": "x", "prettier": {"semi": false}}', encoding="utf-8"
        )
        self._plant_tool("prettier")
        target = self._plant_target("app.js")
        self.assertEqual(apply_formatters(str(target), {})["tool"], "prettier")

    def test_package_json_without_prettier_key_is_not_config(self) -> None:
        (self.project / "package.json").write_text('{"name": "x"}', encoding="utf-8")
        self._plant_tool("biome")
        target = self._plant_target("app.js")
        # Falls through to the unconfigured JS default: biome.
        self.assertEqual(apply_formatters(str(target), {})["tool"], "biome")

    def test_css_formats_only_with_prettier_config(self) -> None:
        self._plant_tool("prettier")
        target = self._plant_target("style.css")
        self.assertEqual(apply_formatters(str(target), {})["status"], "skipped")

        (self.project / ".prettierrc").write_text("{}", encoding="utf-8")
        self.assertEqual(apply_formatters(str(target), {})["tool"], "prettier")

    def test_rust_formats_only_with_rustfmt_toml(self) -> None:
        self._plant_tool("rustfmt")
        target = self._plant_target("lib.rs")
        self.assertEqual(apply_formatters(str(target), {})["status"], "skipped")

        (self.project / "rustfmt.toml").write_text("", encoding="utf-8")
        result = apply_formatters(str(target), {})
        self.assertEqual(result["tool"], "rustfmt")
        self.assertEqual(result["status"], "changed")

    def test_markdown_never_formats(self) -> None:
        target = self._plant_target("notes.md")
        result = apply_formatters(str(target), {})
        self.assertEqual(result["status"], "skipped")
        self.assertIsNone(result["tool"])

    def test_configured_formatter_with_missing_binary_skips(self) -> None:
        (self.project / ".prettierrc").write_text("{}", encoding="utf-8")
        target = self._plant_target("app.js")
        result = apply_formatters(str(target), {})
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["tool"], "prettier")


class FormatSummaryTests(unittest.TestCase):
    def test_one_line_per_file_grouping_steps(self) -> None:
        results = [
            {"path": "a.py", "step": "autofix", "tool": "ruff", "status": "changed"},
            {"path": "a.py", "step": "format", "tool": "ruff", "status": "unchanged"},
            {"path": "b.rs", "step": "autofix", "tool": None, "status": "skipped"},
            {"path": "b.rs", "step": "format", "tool": None, "status": "skipped"},
        ]
        summary = format_summary(results)
        lines = summary.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(
            lines[0], "a.py: autofix ruff (changed), format ruff (unchanged)"
        )
        self.assertEqual(lines[1], "b.rs: nothing to do")

    def test_empty_results_yield_empty_summary(self) -> None:
        self.assertEqual(format_summary([]), "")

    def test_failed_step_is_visible(self) -> None:
        results = [
            {"path": "q.sql", "step": "autofix", "tool": "sqlfluff", "status": "failed"}
        ]
        self.assertEqual(format_summary(results), "q.sql: autofix sqlfluff (failed)")


if __name__ == "__main__":
    unittest.main()
