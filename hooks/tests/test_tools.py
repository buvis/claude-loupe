"""Tests for hooks/loupe/tools.py."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loupe import state as state_mod
from loupe import tools

PROJECT = "abc123def456"


class ToolsTestCase(unittest.TestCase):
    """Isolated HOME and PATH so resolution only sees planted fixtures."""

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

    def _plant_executable(self, directory: Path, name: str, body: str = "#!/bin/sh\n") -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_text(body, encoding="utf-8")
        os.chmod(path, 0o755)
        return path

    def _plant_fake_mise(self, script_body: str) -> None:
        self._plant_executable(self.bin_dir, "mise", script_body)


class ResolveToolTests(ToolsTestCase):
    def test_resolves_from_path_first(self) -> None:
        planted = self._plant_executable(self.bin_dir, "ruff")
        self.assertEqual(tools.resolve_tool("ruff"), str(planted))

    def test_resolves_from_mise_shims_when_not_on_path(self) -> None:
        shim = self._plant_executable(tools.mise_shims_dir(), "ruff")
        self.assertEqual(tools.resolve_tool("ruff"), str(shim))

    def test_path_wins_over_shim(self) -> None:
        on_path = self._plant_executable(self.bin_dir, "ruff")
        self._plant_executable(tools.mise_shims_dir(), "ruff")
        self.assertEqual(tools.resolve_tool("ruff"), str(on_path))

    def test_resolves_via_mise_which_as_last_resort(self) -> None:
        # A real file for the fake mise to point at, not shimmed, not on PATH.
        target = self._plant_executable(self.home / "installs", "sqlfluff")
        self._plant_fake_mise(f"#!/bin/sh\necho {target}\n")
        self.assertEqual(tools.resolve_tool("sqlfluff"), str(target))

    def test_mise_which_failure_yields_none(self) -> None:
        self._plant_fake_mise("#!/bin/sh\nexit 1\n")
        self.assertIsNone(tools.resolve_tool("sqlfluff"))

    def test_mise_reporting_nonexistent_path_yields_none(self) -> None:
        self._plant_fake_mise("#!/bin/sh\necho /nonexistent/tool/path\n")
        self.assertIsNone(tools.resolve_tool("sqlfluff"))

    def test_absent_everywhere_without_mise_yields_none(self) -> None:
        # Empty PATH dir, no shim, no mise binary at all.
        self.assertIsNone(tools.resolve_tool("shellcheck"))


class RecordNudgeTests(ToolsTestCase):
    def test_first_nudge_is_recorded_and_persisted(self) -> None:
        state = state_mod.default_state()
        new_state, recorded = tools.record_nudge(state, PROJECT, "clippy")
        self.assertTrue(recorded)
        self.assertEqual(new_state["persistent"]["nudged"], ["clippy"])
        on_disk = state_mod.load_state(PROJECT)
        self.assertEqual(on_disk["persistent"]["nudged"], ["clippy"])

    def test_second_nudge_for_same_tool_is_a_no_op(self) -> None:
        state = state_mod.default_state()
        state, _ = tools.record_nudge(state, PROJECT, "clippy")
        before = state_mod.state_path(PROJECT).stat().st_mtime_ns

        again, recorded = tools.record_nudge(state, PROJECT, "clippy")

        self.assertFalse(recorded)
        self.assertEqual(again["persistent"]["nudged"], ["clippy"])
        after = state_mod.state_path(PROJECT).stat().st_mtime_ns
        self.assertEqual(before, after)

    def test_distinct_tools_each_get_one_nudge(self) -> None:
        state = state_mod.default_state()
        state, _ = tools.record_nudge(state, PROJECT, "clippy")
        state, recorded = tools.record_nudge(state, PROJECT, "shellcheck")
        self.assertTrue(recorded)
        self.assertEqual(state["persistent"]["nudged"], ["clippy", "shellcheck"])

    def test_nudge_does_not_mutate_input_state(self) -> None:
        state = state_mod.default_state()
        tools.record_nudge(state, PROJECT, "clippy")
        self.assertEqual(state["persistent"]["nudged"], [])

    def test_nudge_once_survives_session_restart(self) -> None:
        # Session N nudges; session N+1 loads, resets runtime, nudges again.
        state = state_mod.default_state()
        state, first = tools.record_nudge(state, PROJECT, "clippy")

        restarted = state_mod.reset_runtime(state_mod.load_state(PROJECT))
        _, second = tools.record_nudge(restarted, PROJECT, "clippy")

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(
            state_mod.load_state(PROJECT)["persistent"]["nudged"], ["clippy"]
        )


if __name__ == "__main__":
    unittest.main()
