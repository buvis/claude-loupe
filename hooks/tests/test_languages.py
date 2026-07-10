"""Tests for hooks/loupe/languages.py."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loupe.languages import UNKNOWN, detect_language


class DetectLanguageTests(unittest.TestCase):
    def test_maps_every_supported_extension(self) -> None:
        expectations = {
            "app.py": "python",
            "app.js": "javascript",
            "app.jsx": "javascript",
            "app.ts": "javascript",
            "app.tsx": "javascript",
            "lib.rs": "rust",
            "Card.svelte": "svelte",
            "site.css": "css",
            "site.scss": "css",
            "schema.sql": "sql",
            "task.rb": "ruby",
            "run.sh": "shell",
            "run.bash": "shell",
            "run.zsh": "shell",
            "README.md": "markdown",
            "README.markdown": "markdown",
        }
        for filename, language in expectations.items():
            with self.subTest(filename=filename):
                self.assertEqual(detect_language(filename), language)

    def test_extension_matching_is_case_insensitive(self) -> None:
        self.assertEqual(detect_language("APP.PY"), "python")
        self.assertEqual(detect_language("lib.RS"), "rust")

    def test_unmapped_extension_is_unknown(self) -> None:
        self.assertEqual(detect_language("data.xyz"), UNKNOWN)

    def test_no_extension_is_unknown(self) -> None:
        self.assertEqual(detect_language("Makefile"), UNKNOWN)

    def test_accepts_path_objects_and_full_paths(self) -> None:
        self.assertEqual(detect_language(Path("x.py")), "python")
        self.assertEqual(detect_language("/deep/nested/dir/main.rs"), "rust")

    def test_only_final_suffix_counts(self) -> None:
        # A tarball-style double extension maps by its last suffix.
        self.assertEqual(detect_language("archive.spec.ts"), "javascript")
        self.assertEqual(detect_language("notes.md.bak"), UNKNOWN)


if __name__ == "__main__":
    unittest.main()
