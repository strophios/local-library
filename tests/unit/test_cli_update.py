"""Unit tests for update command."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, mock_open, patch
from uuid import UUID

import pytest
from typer.testing import CliRunner

from local_library.cli.main import app
from local_library.cli.update import (
    build_editable_json,
    insert_errors_as_comments,
    parse_edited_json,
    validate_edited_json,
)
from local_library.core.models import Document, DocumentStatus

runner = CliRunner()


class TestParseEditedJson:
    """Tests for JSON parsing with comment handling."""

    def test_parse_clean_json(self) -> None:
        """Should parse clean JSON."""
        content = '{"status": "ready", "citekey": "Smith2023"}'

        result = parse_edited_json(content)

        assert result == {"status": "ready", "citekey": "Smith2023"}

    def test_parse_json_with_comments(self) -> None:
        """Should strip comments and parse JSON."""
        content = """// ERRORS:
//   - some error
//
{"status": "ready", "citekey": "Smith2023"}"""

        result = parse_edited_json(content)

        assert result == {"status": "ready", "citekey": "Smith2023"}

    def test_parse_empty_file_returns_none(self) -> None:
        """Should return None for empty/whitespace-only file (abort signal)."""
        assert parse_edited_json("") is None
        assert parse_edited_json("   \n\n  ") is None
        assert parse_edited_json("// just comments\n// more comments") is None

    def test_parse_invalid_json_raises(self) -> None:
        """Should raise ValueError for invalid JSON."""
        content = '{"status": "ready", missing_quotes: bad}'

        with pytest.raises(ValueError) as exc_info:
            parse_edited_json(content)

        assert "JSON" in str(exc_info.value) or "parse" in str(exc_info.value).lower()


class TestInsertErrorsAsComments:
    """Tests for error insertion in JSON."""

    def test_insert_errors_at_top(self) -> None:
        """Should insert errors as comments at top of JSON."""
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
        edited = {
            "status": "ready",
            "citekey": "Smith2023",
            "csl_json": {"type": "article", "title": "Test"},
        }

        errors = validate_edited_json(
            edited,
            current_citekey="Smith2023",
            all_citekeys=["Smith2023"],
        )

        assert errors == []

    def test_validate_invalid_status(self) -> None:
        """Should error on invalid status value."""
        edited = {
            "status": "invalid_status",
            "citekey": "Smith2023",
            "csl_json": {"type": "article", "title": "Test"},
        }

        errors = validate_edited_json(
            edited,
            current_citekey="Smith2023",
            all_citekeys=["Smith2023"],
        )

        assert any("status" in e.lower() for e in errors)

    def test_validate_duplicate_citekey(self) -> None:
        """Should error on duplicate citekey."""
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
        edited = {
            "status": "ready",
            "citekey": "Smith2023",
            "csl_json": {"title": "Missing type field"},  # No 'type' field
        }

        errors = validate_edited_json(
            edited,
            current_citekey="Smith2023",
            all_citekeys=["Smith2023"],
        )

        assert any("type" in e.lower() for e in errors)

    def test_validate_missing_status(self) -> None:
        """Should error on missing status."""
        edited = {
            "citekey": "Smith2023",
            "csl_json": {"type": "article", "title": "Test"},
        }

        errors = validate_edited_json(
            edited,
            current_citekey="Smith2023",
            all_citekeys=["Smith2023"],
        )

        assert any("status" in e.lower() for e in errors)


class TestBuildEditableJson:
    """Tests for JSON structure builder."""

    def test_build_editable_json_structure(self) -> None:
        """Should build correct JSON structure for editing."""
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


@pytest.fixture
def mock_library_update():
    """Provide a mock Library for update command testing."""
    with patch("local_library.cli.update.Library") as mock_lib_cls:
        mock_lib = MagicMock()
        mock_lib_cls.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib_cls.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_lib


class TestUpdateCommand:
    """Tests for update command."""

    def test_update_success(self, mock_library_update: MagicMock) -> None:
        """update command should apply valid changes."""
        mock_doc = MagicMock()
        mock_doc.id = UUID("12345678-1234-1234-1234-123456789abc")
        mock_doc.status = DocumentStatus.NEEDS_REVIEW
        mock_doc.citekey = "Smith2023"
        mock_doc.csl_json = {"type": "article", "title": "Test"}
        mock_doc.original_path = "/path/to/doc.pdf"
        mock_doc.storage_path = "/storage/doc.pdf"
        mock_doc.extracted_path = "/extracted/doc.md"
        mock_doc.content_hash = "abc123"
        mock_doc.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mock_doc.updated_at = datetime(2025, 1, 2, tzinfo=timezone.utc)
        mock_doc.title = "Test"
        mock_doc.authors = "Smith"
        mock_doc.issued_date = "2023"

        mock_library_update.get.return_value = mock_doc
        mock_library_update.get_all_citekeys.return_value = ["Smith2023"]

        # Mock the editor to return modified JSON
        edited_json = json.dumps({
            "status": "ready",
            "citekey": "Smith2023",
            "csl_json": {"type": "article", "title": "Updated Title"},
        })

        with (
            patch("local_library.cli.update.find_editor", return_value="/usr/bin/nvim"),
            patch("tempfile.NamedTemporaryFile") as mock_tempfile,
            patch("local_library.cli.update.subprocess.run"),
            patch("builtins.open", mock_open(read_data=edited_json)),
            patch("local_library.cli.update.Confirm.ask", return_value=False),
        ):
            mock_tempfile.return_value.__enter__.return_value.name = "/tmp/edit.json"

            result = runner.invoke(app, ["update", "12345678"])

            assert result.exit_code == 0
            mock_library_update.update_metadata.assert_called_once()

    def test_update_abort_on_empty(self, mock_library_update: MagicMock) -> None:
        """update command should abort if file is empty."""
        mock_doc = MagicMock()
        mock_doc.id = UUID("12345678-1234-1234-1234-123456789abc")
        mock_doc.status = DocumentStatus.NEEDS_REVIEW
        mock_doc.citekey = "Smith2023"
        mock_doc.csl_json = {"type": "article", "title": "Test"}
        mock_doc.original_path = "/path/to/doc.pdf"
        mock_doc.storage_path = "/storage/doc.pdf"
        mock_doc.extracted_path = "/extracted/doc.md"
        mock_doc.content_hash = "abc123"
        mock_doc.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mock_doc.updated_at = datetime(2025, 1, 2, tzinfo=timezone.utc)
        mock_doc.title = None
        mock_doc.authors = None
        mock_doc.issued_date = None

        mock_library_update.get.return_value = mock_doc

        with (
            patch("local_library.cli.update.find_editor", return_value="/usr/bin/nvim"),
            patch("tempfile.NamedTemporaryFile") as mock_tempfile,
            patch("local_library.cli.update.subprocess.run"),
            patch("builtins.open", mock_open(read_data="")),  # Empty file = abort
        ):
            mock_tempfile.return_value.__enter__.return_value.name = "/tmp/edit.json"

            result = runner.invoke(app, ["update", "12345678"])

            assert result.exit_code == 0
            assert "aborted" in result.output.lower()
            mock_library_update.update_metadata.assert_not_called()

    def test_update_citekey_lookup(self, mock_library_update: MagicMock) -> None:
        """update @citekey should use citekey lookup."""
        mock_doc = MagicMock()
        mock_doc.id = UUID("12345678-1234-1234-1234-123456789abc")
        mock_doc.status = DocumentStatus.READY
        mock_doc.citekey = "Smith2023"
        mock_doc.csl_json = {"type": "article", "title": "Test"}
        mock_doc.original_path = "/path/to/doc.pdf"
        mock_doc.storage_path = "/storage/doc.pdf"
        mock_doc.extracted_path = "/extracted/doc.md"
        mock_doc.content_hash = "abc123"
        mock_doc.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mock_doc.updated_at = datetime(2025, 1, 2, tzinfo=timezone.utc)
        mock_doc.title = "Test"
        mock_doc.authors = "Smith"
        mock_doc.issued_date = "2023"

        mock_library_update.get_by_citekey.return_value = mock_doc
        mock_library_update.get_all_citekeys.return_value = ["Smith2023"]

        edited_json = json.dumps({
            "status": "ready",
            "citekey": "Smith2023",
            "csl_json": {"type": "article", "title": "Test"},
        })

        with (
            patch("local_library.cli.update.find_editor", return_value="/usr/bin/nvim"),
            patch("tempfile.NamedTemporaryFile") as mock_tempfile,
            patch("local_library.cli.update.subprocess.run"),
            patch("builtins.open", mock_open(read_data=edited_json)),
        ):
            mock_tempfile.return_value.__enter__.return_value.name = "/tmp/edit.json"

            result = runner.invoke(app, ["update", "@Smith2023"])

            assert result.exit_code == 0
            mock_library_update.get_by_citekey.assert_called_once_with("Smith2023")
