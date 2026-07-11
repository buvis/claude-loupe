"""Tests for hooks/gate.py: the import-light enabled gate.

The parity classes pin the gate's stdlib-only duplicates to the engine
(loupe.config / loupe.project) so the copies cannot drift silently; the
contract class asserts no entry point imports the engine at module
level - the latency requirement the gate exists for.
"""

import ast
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gate
from loupe import config as config_mod
from loupe import project as project_mod

HOOKS_DIR = Path(__file__).resolve().parents[1]
ENTRY_POINTS = (
    "session_start.py",
    "scan_secrets.py",
    "analyze.py",
    "agent_end.py",
)


class HomeIsolatedTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        env = mock.patch.dict(os.environ, {"HOME": tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.project = self.home / "proj"
        (self.project / ".git").mkdir(parents=True)

    def _write_global(self, payload) -> None:
        path = self.home / ".claude" / "loupe" / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _write_project(self, payload) -> None:
        path = self.project / ".claude" / "loupe.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        text = payload if isinstance(payload, str) else json.dumps(payload)
        path.write_text(text, encoding="utf-8")


class ReadHookJsonTests(unittest.TestCase):
    def _read(self, text: str):
        with mock.patch.object(sys, "stdin", io.StringIO(text)):
            return gate.read_hook_json()

    def test_json_object_parses(self) -> None:
        self.assertEqual(self._read('{"tool_name": "Write"}'), {"tool_name": "Write"})

    def test_garbage_yields_none(self) -> None:
        self.assertIsNone(self._read("{{{ not json"))

    def test_empty_stdin_yields_none(self) -> None:
        self.assertIsNone(self._read(""))

    def test_non_object_json_yields_none(self) -> None:
        self.assertIsNone(self._read("[1, 2, 3]"))
        self.assertIsNone(self._read("null"))


class ProjectRootParityTests(HomeIsolatedTestCase):
    """gate.find_project_root must match loupe.project.project_root."""

    def test_parity_from_a_nested_directory(self) -> None:
        nested = self.project / "src" / "deep"
        nested.mkdir(parents=True)
        self.assertEqual(
            gate.find_project_root(nested), project_mod.project_root(nested)
        )
        self.assertEqual(gate.find_project_root(nested), self.project.resolve())

    def test_parity_without_a_git_marker(self) -> None:
        loose = self.home / "loose"
        loose.mkdir()
        self.assertEqual(
            gate.find_project_root(loose), project_mod.project_root(loose)
        )


class EnabledParityTests(HomeIsolatedTestCase):
    """gate.loupe_enabled must match load_config()['enabled'] exactly."""

    def _assert_parity(self, expected: bool) -> None:
        engine = config_mod.load_config(self.project)["enabled"]
        self.assertEqual(engine, expected)
        self.assertEqual(gate.loupe_enabled(self.project), engine)

    def test_no_config_defaults_enabled(self) -> None:
        self._assert_parity(True)

    def test_global_layer_disables(self) -> None:
        self._write_global({"enabled": False})
        self._assert_parity(False)

    def test_project_layer_disables(self) -> None:
        self._write_project({"enabled": False})
        self._assert_parity(False)

    def test_project_layer_overrides_global(self) -> None:
        self._write_global({"enabled": False})
        self._write_project({"enabled": True})
        self._assert_parity(True)

    def test_wrong_typed_project_value_falls_back_to_default(self) -> None:
        # Not to the global layer: this mirrors load_config exactly.
        self._write_global({"enabled": False})
        self._write_project({"enabled": "yes"})
        self._assert_parity(True)

    def test_wrong_typed_global_value_falls_back_to_default(self) -> None:
        self._write_global({"enabled": 1})
        self._assert_parity(True)

    def test_malformed_project_layer_contributes_nothing(self) -> None:
        self._write_global({"enabled": False})
        self._write_project("{{{ not json")
        self._assert_parity(False)

    def test_non_object_layer_contributes_nothing(self) -> None:
        self._write_project(json.dumps(["enabled"]))
        self._assert_parity(True)

    def test_enabled_resolves_from_a_nested_cwd(self) -> None:
        self._write_project({"enabled": False})
        nested = self.project / "src"
        nested.mkdir()
        self.assertFalse(gate.loupe_enabled(nested))


class ImportLightContractTests(unittest.TestCase):
    """No engine import may run before the gate's enabled check."""

    def test_entry_points_never_import_the_engine_at_module_level(self) -> None:
        for name in ENTRY_POINTS:
            tree = ast.parse((HOOKS_DIR / name).read_text(encoding="utf-8"))
            for node in tree.body:
                with self.subTest(script=name):
                    if isinstance(node, ast.Import):
                        modules = {alias.name.split(".")[0] for alias in node.names}
                        self.assertNotIn("loupe", modules)
                    elif isinstance(node, ast.ImportFrom):
                        module = (node.module or "").split(".")[0]
                        self.assertNotEqual(module, "loupe")

    def test_gate_imports_only_the_stdlib(self) -> None:
        allowed = {"json", "sys", "pathlib"}
        tree = ast.parse((HOOKS_DIR / "gate.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = {alias.name.split(".")[0] for alias in node.names}
                self.assertLessEqual(modules, allowed)
            elif isinstance(node, ast.ImportFrom):
                self.assertIn((node.module or "").split(".")[0], allowed)


if __name__ == "__main__":
    unittest.main()
