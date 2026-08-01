"""Tests for loupe.tdi: unweighted debt counts and their trend.

Pure functions with an injectable clock, so no test here depends on the
wall clock. The load-bearing rows are the ones that keep the index
honest: a clean turn must not append a zero entry, the history must stay
bounded, and a corrupt entry must not poison a direction.
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loupe.tdi import HISTORY_LIMIT, score, trend, update_tdi

FIXED_NOW = datetime(2026, 8, 2, 9, 15, 0, tzinfo=timezone.utc)


def _entry(total: int, ts: str = "2026-08-02T09:15:00Z") -> dict:
    return {"ts": ts, "counts": {"stub": total}, "total": total}


class ScoreTests(unittest.TestCase):
    def test_counts_dicts_by_category(self) -> None:
        findings = [{"category": "stub"}, {"category": "style"}, {"category": "style"}]
        self.assertEqual(
            score(findings), {"counts": {"stub": 1, "style": 2}, "total": 3}
        )

    def test_counts_objects_with_a_category_attribute(self) -> None:
        class Fake:
            category = "security"

        self.assertEqual(
            score([Fake(), Fake()]), {"counts": {"security": 2}, "total": 2}
        )

    def test_entries_without_a_category_are_ignored(self) -> None:
        """A corrupt state row must not inflate the debt number."""
        findings = [{"category": "stub"}, {"nope": 1}, "junk", {"category": ""}]
        self.assertEqual(score(findings), {"counts": {"stub": 1}, "total": 1})

    def test_no_findings_scores_zero(self) -> None:
        self.assertEqual(score([]), {"counts": {}, "total": 0})


class UpdateTdiTests(unittest.TestCase):
    def test_appends_an_entry_for_a_turn_with_findings(self) -> None:
        history = update_tdi([], [{"category": "stub"}], now=FIXED_NOW)
        self.assertEqual(
            history,
            [{"ts": "2026-08-02T09:15:00Z", "counts": {"stub": 1}, "total": 1}],
        )

    def test_clean_turn_appends_nothing(self) -> None:
        """The history logs debt events, not a mostly-zero time series."""
        self.assertEqual(update_tdi([], [], now=FIXED_NOW), [])

    def test_clean_turn_preserves_existing_history(self) -> None:
        history = [_entry(3)]
        self.assertEqual(update_tdi(history, [], now=FIXED_NOW), history)

    def test_timestamp_is_normalized_to_utc(self) -> None:
        local = datetime(2026, 8, 2, 11, 15, 0, tzinfo=timezone(timedelta(hours=2)))
        history = update_tdi([], [{"category": "stub"}], now=local)
        self.assertEqual(history[0]["ts"], "2026-08-02T09:15:00Z")

    def test_history_is_capped_oldest_first(self) -> None:
        history = [_entry(1) for _ in range(HISTORY_LIMIT)]
        updated = update_tdi(history, [{"category": "security"}], now=FIXED_NOW)
        self.assertEqual(len(updated), HISTORY_LIMIT)
        self.assertEqual(updated[-1]["counts"], {"security": 1})

    def test_corrupt_prior_entries_are_dropped(self) -> None:
        updated = update_tdi(
            [{"bogus": True}, _entry(2)], [{"category": "stub"}], now=FIXED_NOW
        )
        self.assertEqual([entry["total"] for entry in updated], [2, 1])


class TrendTests(unittest.TestCase):
    def test_empty_history_is_flat_and_zero(self) -> None:
        self.assertEqual(
            trend([]), {"entries": 0, "latest": 0, "lifetime": 0, "direction": "flat"}
        )

    def test_single_entry_is_flat(self) -> None:
        """One point is not a direction; guessing one would be a lie."""
        self.assertEqual(trend([_entry(5)])["direction"], "flat")

    def test_rising_total_is_up(self) -> None:
        self.assertEqual(trend([_entry(2), _entry(5)])["direction"], "up")

    def test_falling_total_is_down(self) -> None:
        self.assertEqual(trend([_entry(5), _entry(2)])["direction"], "down")

    def test_equal_totals_are_flat(self) -> None:
        self.assertEqual(trend([_entry(3), _entry(3)])["direction"], "flat")

    def test_lifetime_sums_every_entry(self) -> None:
        summary = trend([_entry(2), _entry(3), _entry(4)])
        self.assertEqual(summary["lifetime"], 9)
        self.assertEqual(summary["latest"], 4)
        self.assertEqual(summary["entries"], 3)

    def test_corrupt_entries_do_not_crash_reporting(self) -> None:
        summary = trend([{"ts": 1, "total": "x"}, _entry(4)])
        self.assertEqual(summary["entries"], 1)
        self.assertEqual(summary["latest"], 4)


if __name__ == "__main__":
    unittest.main()
