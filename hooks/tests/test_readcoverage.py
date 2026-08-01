"""Tests for loupe.readcoverage: the range math behind the read guard.

Pure functions, so these are plain in-process assertions. The rows that
matter most are the ones that decide whether a legitimate edit gets
blocked: adjacent reads must coalesce, and a malformed payload must
widen coverage rather than narrow it.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loupe.readcoverage import FULL_FILE, is_covered, merge_range, read_range


class MergeRangeTests(unittest.TestCase):
    def test_first_range_is_stored(self) -> None:
        self.assertEqual(merge_range([], 1, 100), [[1, 100]])

    def test_adjacent_ranges_coalesce(self) -> None:
        """1-100 then 101-200 is contiguous coverage, not two islands."""
        self.assertEqual(merge_range([[1, 100]], 101, 200), [[1, 200]])

    def test_overlapping_ranges_coalesce(self) -> None:
        self.assertEqual(merge_range([[1, 100]], 50, 150), [[1, 150]])

    def test_disjoint_ranges_stay_separate(self) -> None:
        self.assertEqual(merge_range([[1, 100]], 200, 300), [[1, 100], [200, 300]])

    def test_contained_range_changes_nothing(self) -> None:
        self.assertEqual(merge_range([[1, 100]], 20, 30), [[1, 100]])

    def test_out_of_order_input_is_sorted(self) -> None:
        self.assertEqual(merge_range([[200, 300]], 1, 100), [[1, 100], [200, 300]])

    def test_reversed_range_is_ignored(self) -> None:
        self.assertEqual(merge_range([[1, 100]], 50, 10), [[1, 100]])

    def test_corrupt_entries_are_dropped(self) -> None:
        junk = [["a", "b"], [1], None, [5, 5]]
        self.assertEqual(merge_range(junk, 10, 20), [[5, 5], [10, 20]])

    def test_booleans_are_not_line_numbers(self) -> None:
        """bool is an int subclass; [True, True] must not become a range."""
        self.assertEqual(merge_range([[True, True]], 5, 6), [[5, 6]])


class IsCoveredTests(unittest.TestCase):
    def test_exact_match_is_covered(self) -> None:
        self.assertTrue(is_covered([[1, 100]], 1, 100))

    def test_subset_is_covered(self) -> None:
        self.assertTrue(is_covered([[1, 100]], 20, 30))

    def test_overhang_is_not_covered(self) -> None:
        self.assertFalse(is_covered([[1, 100]], 50, 150))

    def test_empty_coverage_covers_nothing(self) -> None:
        self.assertFalse(is_covered([], 1, 1))

    def test_hole_between_ranges_is_not_covered(self) -> None:
        """A target spanning two disjoint ranges really has a gap."""
        self.assertFalse(is_covered([[1, 10], [20, 30]], 5, 25))

    def test_coalesced_ranges_cover_the_span(self) -> None:
        ranges = merge_range(merge_range([], 1, 100), 101, 200)
        self.assertTrue(is_covered(ranges, 1, 200))

    def test_reversed_target_is_treated_as_covered(self) -> None:
        """An unresolvable target never becomes a block."""
        self.assertTrue(is_covered([], 50, 10))


class ReadRangeTests(unittest.TestCase):
    def test_no_offset_no_limit_is_whole_file(self) -> None:
        self.assertEqual(read_range(None, None), (1, FULL_FILE))

    def test_offset_and_limit_map_to_inclusive_span(self) -> None:
        self.assertEqual(read_range(10, 5), (10, 14))

    def test_offset_without_limit_runs_to_end(self) -> None:
        self.assertEqual(read_range(10, None), (10, FULL_FILE))

    def test_limit_without_offset_starts_at_one(self) -> None:
        self.assertEqual(read_range(None, 100), (1, 100))

    def test_malformed_values_widen_rather_than_narrow(self) -> None:
        """A junk payload must not fabricate a narrow range and cause
        false blocks."""
        self.assertEqual(read_range("x", "y"), (1, FULL_FILE))
        self.assertEqual(read_range(0, -5), (1, FULL_FILE))


if __name__ == "__main__":
    unittest.main()
