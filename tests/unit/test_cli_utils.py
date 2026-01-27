"""Unit tests for CLI utilities."""

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from local_library.cli.utils import levenshtein_distance, resolve_identifier, suggest_citekeys
from local_library.core import ErrorCode, LookupError
from local_library.core.models import Document, DocumentStatus


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


class TestSuggestCitekeys:
    """Tests for citekey suggestion generation."""

    def test_prefix_match_prioritized(self) -> None:
        """Prefix matches should appear first."""
        all_citekeys = ["Smith2023", "Smith2024", "Jones2023", "Smithson2023"]
        suggestions = suggest_citekeys("Smith", all_citekeys, max_suggestions=3)

        # Prefix matches first
        assert suggestions[0] in ["Smith2023", "Smith2024"]
        assert suggestions[1] in ["Smith2023", "Smith2024"]

    def test_levenshtein_fallback(self) -> None:
        """When no prefix match, use Levenshtein distance."""
        all_citekeys = ["Smith2023", "Jones2023", "Brown2023"]
        suggestions = suggest_citekeys("Smyth2023", all_citekeys, max_suggestions=3)

        # Smith2023 should be suggested (distance 1 from Smyth2023)
        assert "Smith2023" in suggestions

    def test_max_distance_respected(self) -> None:
        """Suggestions beyond max_distance should be excluded."""
        all_citekeys = ["AAAA", "BBBB", "CCCC"]
        suggestions = suggest_citekeys("ZZZZ", all_citekeys, max_suggestions=3, max_distance=3)

        # All have distance 4, should return empty
        assert suggestions == []

    def test_empty_citekeys(self) -> None:
        """Empty citekey list returns empty suggestions."""
        suggestions = suggest_citekeys("Smith", [], max_suggestions=3)
        assert suggestions == []

    def test_max_suggestions_limit(self) -> None:
        """Should not return more than max_suggestions."""
        all_citekeys = [f"Smith202{i}" for i in range(10)]
        suggestions = suggest_citekeys("Smith", all_citekeys, max_suggestions=3)

        assert len(suggestions) <= 3


def _make_mock_document(
    doc_id: str = "12345678-1234-1234-1234-123456789abc",
    citekey: str | None = "Smith2023",
) -> MagicMock:
    """Create a mock Document for testing."""
    mock = MagicMock(spec=Document)
    mock.id = UUID(doc_id)
    mock.citekey = citekey
    mock.status = DocumentStatus.READY
    return mock


class TestResolveIdentifier:
    """Tests for identifier resolution."""

    def test_uuid_lookup(self) -> None:
        """UUID without @ prefix uses Library.get()."""
        mock_lib = MagicMock()
        mock_doc = _make_mock_document()
        mock_lib.get.return_value = mock_doc

        result = resolve_identifier("12345678", mock_lib)

        assert result == mock_doc
        mock_lib.get.assert_called_once_with("12345678")

    def test_citekey_lookup_with_at_prefix(self) -> None:
        """@citekey syntax uses citekey lookup."""
        mock_lib = MagicMock()
        mock_doc = _make_mock_document()
        mock_lib.get_by_citekey.return_value = mock_doc

        result = resolve_identifier("@Smith2023", mock_lib)

        assert result == mock_doc
        mock_lib.get_by_citekey.assert_called_once_with("Smith2023")

    def test_citekey_not_found_with_suggestions(self) -> None:
        """Citekey miss should raise LookupError with suggestions."""
        mock_lib = MagicMock()
        mock_lib.get_by_citekey.return_value = None
        mock_lib.get_all_citekeys.return_value = ["Smith2023", "Smith2024", "Jones2023"]

        with pytest.raises(LookupError) as exc_info:
            resolve_identifier("@Smth2023", mock_lib)

        assert exc_info.value.code == ErrorCode.NOT_FOUND
        assert "Smth2023" in exc_info.value.message
        # Should have suggestions in details
        assert "suggestions" in exc_info.value.details

    def test_citekey_not_found_no_suggestions(self) -> None:
        """Citekey miss with no close matches has empty suggestions."""
        mock_lib = MagicMock()
        mock_lib.get_by_citekey.return_value = None
        mock_lib.get_all_citekeys.return_value = ["AAAA", "BBBB"]

        with pytest.raises(LookupError) as exc_info:
            resolve_identifier("@ZZZZCompletely2023Different", mock_lib)

        assert exc_info.value.code == ErrorCode.NOT_FOUND
        # No close matches, suggestions may be empty
        assert exc_info.value.details.get("suggestions", []) == []

    def test_uuid_not_found_passthrough(self) -> None:
        """UUID miss should pass through Library.get() exception."""
        mock_lib = MagicMock()
        mock_lib.get.side_effect = LookupError("document not found", ErrorCode.NOT_FOUND)

        with pytest.raises(LookupError) as exc_info:
            resolve_identifier("nonexistent", mock_lib)

        assert exc_info.value.code == ErrorCode.NOT_FOUND
