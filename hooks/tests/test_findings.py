"""Tests for hooks/loupe/findings.py."""

import dataclasses
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loupe.findings import BLOCKING_CATEGORIES, CATEGORIES, Finding, classify


def _finding(category: str, message: str = "m") -> Finding:
    return Finding(category, "error", message, "src/a.py", 1)


class FindingModelTests(unittest.TestCase):
    def test_accepts_every_known_category(self) -> None:
        for category in CATEGORIES:
            with self.subTest(category=category):
                self.assertEqual(_finding(category).category, category)

    def test_rejects_unknown_category(self) -> None:
        with self.assertRaises(ValueError):
            _finding("vibes")

    def test_finding_is_immutable(self) -> None:
        finding = _finding("style")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            finding.category = "stub"

    def test_findings_are_hashable_for_dedup(self) -> None:
        a = _finding("style")
        b = _finding("style")
        self.assertEqual({a, b}, {a})


class ClassifyTests(unittest.TestCase):
    def test_stub_and_security_block_rest_advise(self) -> None:
        stub = _finding("stub", "empty body")
        security = _finding("security", "eval on input")
        correctness = _finding("correctness", "shadowed var")
        style = _finding("style", "long line")

        blocking, advisory = classify([style, stub, correctness, security])

        self.assertEqual(blocking, [stub, security])
        self.assertEqual(advisory, [style, correctness])

    def test_blocking_set_is_exactly_stub_plus_security(self) -> None:
        self.assertEqual(BLOCKING_CATEGORIES, {"stub", "security"})
        self.assertTrue(BLOCKING_CATEGORIES < CATEGORIES)

    def test_all_advisory_input_blocks_nothing(self) -> None:
        findings = [_finding("style"), _finding("correctness")]
        blocking, advisory = classify(findings)
        self.assertEqual(blocking, [])
        self.assertEqual(advisory, findings)

    def test_all_blocking_input_advises_nothing(self) -> None:
        findings = [_finding("stub"), _finding("security")]
        blocking, advisory = classify(findings)
        self.assertEqual(blocking, findings)
        self.assertEqual(advisory, [])

    def test_empty_input_yields_empty_split(self) -> None:
        self.assertEqual(classify([]), ([], []))


if __name__ == "__main__":
    unittest.main()
