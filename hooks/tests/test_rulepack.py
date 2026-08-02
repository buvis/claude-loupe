"""Fixture verification for the ast-grep rule pack.

Inventory tests run everywhere (pure file checks). Behavior tests run
the real ast-grep binary over rules/ast-grep/fixtures in one scan and
assert, per rule: the rule fires in its positive fixture and stays
silent in its negative fixture. When ast-grep is unavailable the whole
behavior class skips visibly (counted in the test summary).
"""

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loupe.astgrep import run_astgrep
from loupe.findings import CATEGORIES, classify
from loupe.tools import resolve_tool

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = REPO_ROOT / "rules" / "ast-grep"
FIXTURES_DIR = RULES_DIR / "fixtures"
SCAN_TIMEOUT_SECONDS = 120

# Rule dir -> fixture extension; ids in each dir must use the matching
# language tag by convention.
RULE_DIRS = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "rust": ".rs",
}

_ID_RE = re.compile(r"(?m)^id:\s*(\S+)")


def _rule_ids() -> dict[str, str]:
    """Map of rule id -> rule dir name, parsed from the pack itself."""
    ids: dict[str, str] = {}
    for dir_name in RULE_DIRS:
        for rule_file in sorted((RULES_DIR / dir_name).glob("*.yml")):
            for rule_id in _ID_RE.findall(rule_file.read_text(encoding="utf-8")):
                ids[rule_id] = dir_name
    return ids


class RulePackInventoryTests(unittest.TestCase):
    """Static pack invariants; no ast-grep binary required."""

    def test_pack_is_not_empty(self) -> None:
        self.assertGreaterEqual(len(_rule_ids()), 26)

    def test_rule_ids_are_unique_across_the_pack(self) -> None:
        seen: list[str] = []
        for dir_name in RULE_DIRS:
            for rule_file in sorted((RULES_DIR / dir_name).glob("*.yml")):
                seen.extend(_ID_RE.findall(rule_file.read_text(encoding="utf-8")))
        self.assertEqual(len(seen), len(set(seen)))

    def test_every_rule_id_carries_a_category_prefix(self) -> None:
        for rule_id in _rule_ids():
            with self.subTest(rule=rule_id):
                self.assertIn(rule_id.split("-", 1)[0], CATEGORIES)

    def test_every_rule_has_positive_and_negative_fixtures(self) -> None:
        for rule_id, dir_name in _rule_ids().items():
            extension = RULE_DIRS[dir_name]
            with self.subTest(rule=rule_id):
                fixture_dir = FIXTURES_DIR / rule_id
                self.assertTrue(
                    (fixture_dir / f"positive{extension}").is_file(),
                    f"missing positive fixture for {rule_id}",
                )
                self.assertTrue(
                    (fixture_dir / f"negative{extension}").is_file(),
                    f"missing negative fixture for {rule_id}",
                )


class RulePackBehaviorTests(unittest.TestCase):
    """One real ast-grep scan over all fixtures, asserted per rule."""

    matches_by_file: dict[Path, set] = {}

    @classmethod
    def setUpClass(cls) -> None:
        binary = resolve_tool("ast-grep")
        if binary is None:
            raise unittest.SkipTest(
                "ast-grep unavailable; rule-pack fixture verification skipped"
            )
        result = subprocess.run(
            [
                binary,
                "scan",
                "--config",
                str(RULES_DIR / "sgconfig.yml"),
                "--json",
                str(FIXTURES_DIR),
            ],
            capture_output=True,
            text=True,
            timeout=SCAN_TIMEOUT_SECONDS,
        )
        try:
            matches = json.loads(result.stdout)
        except ValueError:
            raise AssertionError(
                "ast-grep scan over fixtures produced no JSON "
                f"(exit {result.returncode}): {result.stderr[:500]}"
            ) from None
        cls.matches_by_file = {}
        for match in matches:
            file_path = Path(match["file"]).resolve()
            cls.matches_by_file.setdefault(file_path, set()).add(match["ruleId"])

    def _fixture(self, rule_id: str, dir_name: str, kind: str) -> Path:
        return (FIXTURES_DIR / rule_id / f"{kind}{RULE_DIRS[dir_name]}").resolve()

    def test_every_rule_fires_on_its_positive_fixture(self) -> None:
        for rule_id, dir_name in _rule_ids().items():
            with self.subTest(rule=rule_id):
                fired = self.matches_by_file.get(
                    self._fixture(rule_id, dir_name, "positive"), set()
                )
                self.assertIn(rule_id, fired)

    def test_every_rule_stays_silent_on_its_negative_fixture(self) -> None:
        for rule_id, dir_name in _rule_ids().items():
            with self.subTest(rule=rule_id):
                fired = self.matches_by_file.get(
                    self._fixture(rule_id, dir_name, "negative"), set()
                )
                self.assertNotIn(rule_id, fired)

    def test_empty_except_and_catch_never_block_an_edit(self) -> None:
        """Best-effort cleanup is advisory, not a stub.

        The 2026-08-02 dogfood scan hit 30 deliberate empty handlers in
        shipped first-party code and zero real stubs, so these three
        rules carry the ``style`` category and can never exit 2.
        """
        ids = _rule_ids()
        for rule_id in (
            "style-python-empty-except",
            "style-js-empty-catch",
            "style-ts-empty-catch",
        ):
            with self.subTest(rule=rule_id):
                dir_name = ids[rule_id]
                fixture = self._fixture(rule_id, dir_name, "positive")
                language = "python" if dir_name == "python" else "javascript"
                fired = [
                    finding
                    for finding in run_astgrep(str(fixture), language, RULES_DIR)
                    if finding.message.startswith(f"{rule_id}:")
                ]
                self.assertTrue(fired, f"{rule_id} did not fire on its fixture")
                blocking, advisory = classify(fired)
                self.assertEqual(blocking, [])
                self.assertEqual(len(advisory), len(fired))

    def test_run_astgrep_end_to_end_with_the_packaged_pack(self) -> None:
        fixture = FIXTURES_DIR / "security-python-eval-exec" / "positive.py"
        findings = run_astgrep(str(fixture), "python", RULES_DIR)
        categories = {finding.category for finding in findings}
        self.assertIn("security", categories)
        lines = [f.line for f in findings if f.category == "security"]
        self.assertTrue(all(line >= 1 for line in lines))


if __name__ == "__main__":
    unittest.main()
