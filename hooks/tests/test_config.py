"""Tests for hooks/loupe/config.py."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loupe import config as config_mod


class ConfigTestCase(unittest.TestCase):
    """Isolated HOME plus a scratch project root for the override layer."""

    def setUp(self) -> None:
        home_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(home_tmp.cleanup)
        env = mock.patch.dict(os.environ, {"HOME": home_tmp.name})
        env.start()
        self.addCleanup(env.stop)

        project_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(project_tmp.cleanup)
        self.project = Path(project_tmp.name)

    def _write_global(self, content: str) -> None:
        path = config_mod.global_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _write_project(self, content: str) -> None:
        path = config_mod.project_config_path(self.project)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


class DefaultsTests(ConfigTestCase):
    def test_no_config_files_yields_defaults(self) -> None:
        loaded = config_mod.load_config(self.project)
        self.assertEqual(loaded, {"enabled": True, "immediate_fix": False})

    def test_defaults_constant_is_not_mutated_by_loads(self) -> None:
        self._write_project(json.dumps({"enabled": False}))
        config_mod.load_config(self.project)
        self.assertEqual(config_mod.DEFAULTS, {"enabled": True, "immediate_fix": False})


class MergePrecedenceTests(ConfigTestCase):
    def test_global_layer_applies_over_defaults(self) -> None:
        self._write_global(json.dumps({"immediate_fix": True}))
        loaded = config_mod.load_config(self.project)
        self.assertTrue(loaded["immediate_fix"])
        self.assertTrue(loaded["enabled"])

    def test_project_layer_overrides_global(self) -> None:
        self._write_global(json.dumps({"enabled": False}))
        self._write_project(json.dumps({"enabled": True}))
        self.assertTrue(config_mod.load_config(self.project)["enabled"])

    def test_disabling_per_project_survives_merge(self) -> None:
        self._write_project(json.dumps({"enabled": False}))
        self.assertFalse(config_mod.load_config(self.project)["enabled"])

    def test_nested_dicts_deep_merge_instead_of_replacing(self) -> None:
        # Unknown keys ride through untouched; nested objects merge key-wise.
        self._write_global(json.dumps({"linters": {"python": "ruff", "shared": "global"}}))
        self._write_project(json.dumps({"linters": {"rust": "clippy", "shared": "project"}}))
        loaded = config_mod.load_config(self.project)
        self.assertEqual(
            loaded["linters"],
            {"python": "ruff", "rust": "clippy", "shared": "project"},
        )


class MalformedConfigTests(ConfigTestCase):
    def test_malformed_global_is_ignored_but_project_applies(self) -> None:
        self._write_global("not json {{{")
        self._write_project(json.dumps({"immediate_fix": True}))
        loaded = config_mod.load_config(self.project)
        self.assertTrue(loaded["immediate_fix"])
        self.assertTrue(loaded["enabled"])

    def test_malformed_project_is_ignored_but_global_applies(self) -> None:
        self._write_global(json.dumps({"enabled": False}))
        self._write_project("[]")
        self.assertFalse(config_mod.load_config(self.project)["enabled"])

    def test_wrong_typed_known_key_falls_back_to_default(self) -> None:
        self._write_global(json.dumps({"enabled": "yes", "immediate_fix": 1}))
        loaded = config_mod.load_config(self.project)
        self.assertIs(loaded["enabled"], True)
        self.assertIs(loaded["immediate_fix"], False)

    def test_missing_project_root_dir_yields_defaults(self) -> None:
        ghost = self.project / "does-not-exist"
        self.assertEqual(
            config_mod.load_config(ghost),
            {"enabled": True, "immediate_fix": False},
        )


if __name__ == "__main__":
    unittest.main()
