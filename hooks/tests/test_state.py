"""Tests for hooks/loupe/state.py."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loupe import state as state_mod

PROJECT = "abc123def456"


class HomeIsolatedTestCase(unittest.TestCase):
    """Isolate HOME so state I/O never touches the real ~/.claude."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        env = mock.patch.dict(os.environ, {"HOME": tmp.name})
        env.start()
        self.addCleanup(env.stop)


class StateRoundTripTests(HomeIsolatedTestCase):
    def test_save_then_load_round_trips(self) -> None:
        state = state_mod.default_state()
        state["runtime"]["format_queue"] = ["src/a.py", "src/b.rs"]
        state["runtime"]["findings"] = [{"category": "style", "line": 3}]
        state["persistent"]["nudged"] = ["ruff"]
        state_mod.save_state(PROJECT, state)
        self.assertEqual(state_mod.load_state(PROJECT), state)

    def test_state_file_lands_under_isolated_home(self) -> None:
        state_mod.save_state(PROJECT, state_mod.default_state())
        expected = self.home / ".claude" / "loupe" / "state" / f"{PROJECT}.json"
        self.assertTrue(expected.is_file())

    def test_save_leaves_no_tmp_file_behind(self) -> None:
        state_mod.save_state(PROJECT, state_mod.default_state())
        leftovers = list(state_mod.state_dir().glob("*.tmp"))
        self.assertEqual(leftovers, [])

    def test_missing_file_yields_defaults(self) -> None:
        self.assertEqual(state_mod.load_state(PROJECT), state_mod.default_state())


class RuntimeResetTests(HomeIsolatedTestCase):
    def test_reset_clears_runtime_and_keeps_persistent(self) -> None:
        state = state_mod.default_state()
        state["runtime"]["format_queue"] = ["src/a.py"]
        state["persistent"]["nudged"] = ["clippy"]

        fresh = state_mod.reset_runtime(state)

        self.assertEqual(fresh["runtime"], state_mod.default_runtime())
        self.assertEqual(fresh["persistent"]["nudged"], ["clippy"])

    def test_reset_returns_new_state_without_mutating_input(self) -> None:
        state = state_mod.default_state()
        state["runtime"]["format_queue"] = ["src/a.py"]
        state_mod.reset_runtime(state)
        self.assertEqual(state["runtime"]["format_queue"], ["src/a.py"])

    def test_nudge_log_survives_a_session_cycle(self) -> None:
        # Session N records a nudge; session N+1 resets runtime on start.
        state = state_mod.default_state()
        state["runtime"]["findings"] = [{"category": "stub"}]
        state["persistent"]["nudged"] = ["shellcheck"]
        state_mod.save_state(PROJECT, state)

        loaded = state_mod.load_state(PROJECT)
        restarted = state_mod.reset_runtime(loaded)
        state_mod.save_state(PROJECT, restarted)

        final = state_mod.load_state(PROJECT)
        self.assertEqual(final["runtime"], state_mod.default_runtime())
        self.assertEqual(final["persistent"]["nudged"], ["shellcheck"])


class MalformedStateTests(HomeIsolatedTestCase):
    def _plant(self, content: str) -> None:
        path = state_mod.state_path(PROJECT)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_garbage_text_rebuilds_defaults(self) -> None:
        self._plant("{{{ not json at all")
        self.assertEqual(state_mod.load_state(PROJECT), state_mod.default_state())

    def test_non_dict_json_rebuilds_defaults(self) -> None:
        self._plant("[1, 2, 3]")
        self.assertEqual(state_mod.load_state(PROJECT), state_mod.default_state())

    def test_wrong_typed_blocks_rebuild_defaults(self) -> None:
        self._plant(json.dumps({"runtime": "nope", "persistent": 7}))
        self.assertEqual(state_mod.load_state(PROJECT), state_mod.default_state())

    def test_wrong_typed_field_falls_back_field_by_field(self) -> None:
        self._plant(
            json.dumps(
                {
                    "runtime": {"format_queue": "not-a-list", "findings": []},
                    "persistent": {"nudged": ["ruff"]},
                }
            )
        )
        loaded = state_mod.load_state(PROJECT)
        self.assertEqual(loaded["runtime"]["format_queue"], [])
        self.assertEqual(loaded["persistent"]["nudged"], ["ruff"])

    def test_partial_state_fills_missing_blocks(self) -> None:
        self._plant(json.dumps({"persistent": {"nudged": ["biome"]}}))
        loaded = state_mod.load_state(PROJECT)
        self.assertEqual(loaded["runtime"], state_mod.default_runtime())
        self.assertEqual(loaded["persistent"]["nudged"], ["biome"])
        self.assertEqual(loaded["version"], state_mod.STATE_VERSION)


if __name__ == "__main__":
    unittest.main()
