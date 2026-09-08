from __future__ import annotations

import unittest

from alchemy.domain.versioning import VersionRange


class VersionRangeTests(unittest.TestCase):
    def test_matches_bounded_plasma_range(self) -> None:
        value = VersionRange.parse(">=6.6,<6.9")

        self.assertTrue(value.matches("6.6.0"))
        self.assertTrue(value.matches("6.8.9"))
        self.assertFalse(value.matches("6.9.0"))

    def test_rejects_impossible_or_ambiguous_ranges(self) -> None:
        for value in (
            ">=6.9,<6.6",
            ">6.7,<6.7.1",
            ">6.7,<=6.7",
            "<0.0",
            "6.7",
            ">= 6.7",
            ">=6.x",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                VersionRange.parse(value)


if __name__ == "__main__":
    unittest.main()
