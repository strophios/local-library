"""Unit tests for update command."""

import json
from datetime import datetime, timezone
from uuid import UUID

import pytest

from local_library.core.models import Document, DocumentStatus


class TestParseEditedJson:
    """Tests for JSON parsing with comment handling."""

    def test_parse_clean_json(self) -> None:
        """Should parse clean JSON."""
        from local_library.cli.update import parse_edited_json

        content = '{"status": "ready", "citekey": "Smith2023"}'

        result = parse_edited_json(content)

        assert result == {"status": "ready", "citekey": "Smith2023"}

    def test_parse_json_with_comments(self) -> None:
        """Should strip comments and parse JSON."""
        from local_library.cli.update import parse_edited_json

        content = """// ERRORS:
//   - some error
//
{"status": "ready", "citekey": "Smith2023"}"""

        result = parse_edited_json(content)

        assert result == {"status": "ready", "citekey": "Smith2023"}

    def test_parse_empty_file_returns_none(self) -> None:
        """Should return None for empty/whitespace-only file (abort signal)."""
        from local_library.cli.update import parse_edited_json

        assert parse_edited_json("") is None
        assert parse_edited_json("   \n\n  ") is None
        assert parse_edited_json("// just comments\n// more comments") is None

    def test_parse_invalid_json_raises(self) -> None:
        """Should raise ValueError for invalid JSON."""
        from local_library.cli.update import parse_edited_json

        content = '{"status": "ready", missing_quotes: bad}'

        with pytest.raises(ValueError) as exc_info:
            parse_edited_json(content)

        assert "JSON" in str(exc_info.value) or "parse" in str(exc_info.value).lower()


class TestInsertErrorsAsComments:
    """Tests for error insertion in JSON."""

    def test_insert_errors_at_top(self) -> None:
        """Should insert errors as comments at top of JSON."""
        from local_library.cli.update import insert_errors_as_comments

        original = '{\n  "status": "invalid"\n}'
        errors = ["invalid status 'invalid'", "citekey already exists"]

        result = insert_errors_as_comments(original, errors)

        # Errors should appear as comments before JSON
        lines = result.split("\n")
        assert "// ERRORS" in lines[0]
        assert any("invalid status" in line for line in lines[:5])
        assert any("citekey" in line for line in lines[:5])

    def test_insert_errors_preserves_json(self) -> None:
        """Should preserve original JSON content."""
        from local_library.cli.update import insert_errors_as_comments

        original = '{\n  "status": "ready",\n  "citekey": "Smith2023"\n}'
        errors = ["some error"]

        result = insert_errors_as_comments(original, errors)

        # JSON should still be present after comments
        assert '"status": "ready"' in result
        assert '"citekey": "Smith2023"' in result


class TestValidateEditedJson:
    """Tests for edited JSON validation."""

    def test_validate_valid_json(self) -> None:
        """Should return no errors for valid JSON."""
        from local_library.cli.update import validate_edited_json

        edited = {
            "status": "ready",
            "citekey": "Smith2023",
            "csl_json": {"type": "article", "title": "Test"},
        }

        errors = validate_edited_json(edited, current_citekey="Smith2023", all_citekeys=["Smith2023"])

        assert errors == []

    def test_validate_invalid_status(self) -> None:
        """Should error on invalid status value."""
        from local_library.cli.update import validate_edited_json

        edited = {
            "status": "invalid_status",
            "citekey": "Smith2023",
            "csl_json": {"type": "article", "title": "Test"},
        }

        errors = validate_edited_json(edited, current_citekey="Smith2023", all_citekeys=["Smith2023"])

        assert any("status" in e.lower() for e in errors)

    def test_validate_duplicate_citekey(self) -> None:
        """Should error on duplicate citekey."""
        from local_library.cli.update import validate_edited_json

        edited = {
            "status": "ready",
            "citekey": "Jones2024",  # Different from current, exists in library
            "csl_json": {"type": "article", "title": "Test"},
        }

        errors = validate_edited_json(
            edited,
            current_citekey="Smith2023",
            all_citekeys=["Smith2023", "Jones2024"],  # Jones2024 already exists
        )

        assert any("citekey" in e.lower() and "exists" in e.lower() for e in errors)

    def test_validate_citekey_same_as_current(self) -> None:
        """Should allow keeping current citekey."""
        from local_library.cli.update import validate_edited_json

        edited = {
            "status": "ready",
            "citekey": "Smith2023",  # Same as current
            "csl_json": {"type": "article", "title": "Test"},
        }

        errors = validate_edited_json(
            edited,
            current_citekey="Smith2023",
            all_citekeys=["Smith2023", "Jones2024"],
        )

        assert errors == []

    def test_validate_invalid_csl_json(self) -> None:
        """Should error on invalid CSL-JSON."""
        from local_library.cli.update import validate_edited_json

        edited = {
            "status": "ready",
            "citekey": "Smith2023",
            "csl_json": {"title": "Missing type field"},  # No 'type' field
        }

        errors = validate_edited_json(edited, current_citekey="Smith2023", all_citekeys=["Smith2023"])

        assert any("type" in e.lower() for e in errors)

    def test_validate_missing_status(self) -> None:
        """Should error on missing status."""
        from local_library.cli.update import validate_edited_json

        edited = {
            "citekey": "Smith2023",
            "csl_json": {"type": "article", "title": "Test"},
        }

        errors = validate_edited_json(edited, current_citekey="Smith2023", all_citekeys=["Smith2023"])

        assert any("status" in e.lower() for e in errors)


class TestBuildEditableJson:
    """Tests for JSON structure builder."""

    def test_build_editable_json_structure(self) -> None:
        """Should build correct JSON structure for editing."""
        from local_library.cli.update import build_editable_json

        doc = Document(
            id=UUID("12345678-1234-1234-1234-123456789abc"),
            original_path="/path/to/doc.pdf",
            content_hash="abc123",
            storage_path="/storage/ab/c1/abc123.pdf",
            status=DocumentStatus.NEEDS_REVIEW,
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
            extracted_path="/extracted/abc123.md",
            citekey="Smith2023",
            csl_json={"type": "article", "title": "Test"},
            title="Test Title",
            authors="John Smith",
            issued_date="2023",
        )

        result = build_editable_json(doc)
        parsed = json.loads(result)

        # Check readonly block
        assert "_readonly" in parsed
        assert parsed["_readonly"]["id"] == "12345678-1234-1234-1234-123456789abc"
        assert parsed["_readonly"]["original_path"] == "/path/to/doc.pdf"

        # Check editable fields
        assert parsed["status"] == "needs_review"
        assert parsed["citekey"] == "Smith2023"
        assert parsed["csl_json"] == {"type": "article", "title": "Test"}

    def test_build_editable_json_null_fields(self) -> None:
        """Should handle null fields gracefully."""
        from local_library.cli.update import build_editable_json

        doc = Document(
            id=UUID("12345678-1234-1234-1234-123456789abc"),
            original_path="/path/to/doc.pdf",
            content_hash="abc123",
            storage_path="/storage/ab/c1/abc123.pdf",
            status=DocumentStatus.PENDING,
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
            citekey=None,
            csl_json=None,
        )

        result = build_editable_json(doc)
        parsed = json.loads(result)

        assert parsed["citekey"] is None
        assert parsed["csl_json"] is None
