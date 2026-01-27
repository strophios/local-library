"""Unit tests for CLI utilities."""

import pytest

from local_library.cli.utils import levenshtein_distance


class TestLevenshteinDistance:
    """Tests for Levenshtein distance calculation."""

    def test_identical_strings(self) -> None:
        """Identical strings have distance 0."""
        assert levenshtein_distance("test", "test") == 0

    def test_empty_strings(self) -> None:
        """Empty string comparisons."""
        assert levenshtein_distance("", "") == 0
        assert levenshtein_distance("abc", "") == 3
        assert levenshtein_distance("", "abc") == 3

    def test_single_insertion(self) -> None:
        """Single character insertion."""
        assert levenshtein_distance("test", "tests") == 1

    def test_single_deletion(self) -> None:
        """Single character deletion."""
        assert levenshtein_distance("tests", "test") == 1

    def test_single_substitution(self) -> None:
        """Single character substitution."""
        assert levenshtein_distance("test", "tent") == 1

    def test_multiple_edits(self) -> None:
        """Multiple edits needed."""
        assert levenshtein_distance("kitten", "sitting") == 3

    def test_case_sensitive(self) -> None:
        """Distance is case-sensitive."""
        assert levenshtein_distance("Test", "test") == 1
