"""Unit tests for CLI commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from local_library.cli.main import app
from local_library.core import ErrorCode, LookupError
from local_library.core.models import AddResult, DocumentStatus

runner = CliRunner()


@pytest.fixture
def mock_library():
    """Provide a mock Library for CLI testing."""
    with (
        patch("local_library.cli.add.Library") as mock_add,
        patch("local_library.cli.list.Library") as mock_list,
        patch("local_library.cli.show.Library") as mock_show,
        patch("local_library.cli.delete.Library") as mock_delete,
    ):
        mock_lib = MagicMock()
        mock_add.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_add.return_value.__exit__ = MagicMock(return_value=False)
        mock_list.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_list.return_value.__exit__ = MagicMock(return_value=False)
        mock_show.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_show.return_value.__exit__ = MagicMock(return_value=False)
        mock_delete.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_delete.return_value.__exit__ = MagicMock(return_value=False)

        yield mock_lib


class TestAddCommand:
    """Tests for the add command."""

    def test_add_success(self, mock_library: MagicMock, temp_dir: Path) -> None:
        """add command should succeed for valid files."""
        pdf_path = temp_dir / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")

        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.storage_path = "/storage/12/34/1234.pdf"
        mock_doc.original_path = str(pdf_path)
        mock_doc.content_hash = "abcd1234"

        mock_library.add.return_value = AddResult(document=mock_doc)

        result = runner.invoke(app, ["add", str(pdf_path)])

        assert result.exit_code == 0
        assert "added" in result.output

    def test_add_duplicate_shows_warning(self, mock_library: MagicMock, temp_dir: Path) -> None:
        """add command should indicate duplicates."""
        pdf_path = temp_dir / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")

        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.storage_path = "/storage/test.pdf"
        mock_doc.original_path = str(pdf_path)
        mock_doc.content_hash = "abcd1234"

        mock_library.add.return_value = AddResult(
            document=mock_doc,
            is_duplicate=True,
            duplicate_reason="path",
        )

        result = runner.invoke(app, ["add", str(pdf_path)])

        assert result.exit_code == 0
        assert "duplicate" in result.output

    def test_add_json_output(self, mock_library: MagicMock, temp_dir: Path) -> None:
        """add command with --json should output JSON."""
        pdf_path = temp_dir / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4")

        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.storage_path = "/storage/test.pdf"
        mock_doc.original_path = str(pdf_path)
        mock_doc.content_hash = "abcd1234"

        mock_library.add.return_value = AddResult(document=mock_doc)

        result = runner.invoke(app, ["add", "--json", str(pdf_path)])

        assert result.exit_code == 0
        assert '"id"' in result.output


class TestListCommand:
    """Tests for the list command."""

    def test_list_empty(self, mock_library: MagicMock) -> None:
        """list command should handle empty library."""
        mock_library.list.return_value = []

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "No documents" in result.output

    def test_list_with_documents(self, mock_library: MagicMock) -> None:
        """list command should display documents."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.original_path = "/path/to/doc.pdf"
        mock_doc.content_hash = "abcd1234"
        mock_doc.created_at = None

        mock_library.list.return_value = [mock_doc]

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "12345678" in result.output

    def test_list_filter_by_status(self, mock_library: MagicMock) -> None:
        """list command should accept --status filter."""
        mock_library.list.return_value = []

        result = runner.invoke(app, ["list", "--status", "ready"])

        assert result.exit_code == 0
        mock_library.list.assert_called_once_with(status=DocumentStatus.READY)

    def test_list_invalid_status(self, mock_library: MagicMock) -> None:
        """list command should reject invalid status."""
        result = runner.invoke(app, ["list", "--status", "invalid"])

        assert result.exit_code == 1
        assert "invalid status" in result.output


class TestShowCommand:
    """Tests for the show command."""

    def test_show_document(self, mock_library: MagicMock) -> None:
        """show command should display document details."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.original_path = "/path/to/doc.pdf"
        mock_doc.storage_path = "/storage/doc.pdf"
        mock_doc.extracted_path = "/extracted/doc.md"
        mock_doc.content_hash = "abcd1234"
        mock_doc.citekey = None
        mock_doc.error_message = None
        mock_doc.error_code = None
        mock_doc.created_at = None
        mock_doc.updated_at = None

        mock_library.get.return_value = mock_doc

        result = runner.invoke(app, ["show", "12345678"])

        assert result.exit_code == 0
        assert "12345678" in result.output

    def test_show_not_found(self, mock_library: MagicMock) -> None:
        """show command should handle not found."""
        mock_library.get.side_effect = LookupError("document not found", ErrorCode.NOT_FOUND)

        result = runner.invoke(app, ["show", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output


class TestDeleteCommand:
    """Tests for the delete command."""

    def test_delete_with_force(self, mock_library: MagicMock) -> None:
        """delete command with --force should skip confirmation."""
        mock_doc = MagicMock()
        mock_doc.id = "12345678-1234-1234-1234-123456789abc"
        mock_doc.status = DocumentStatus.READY
        mock_doc.original_path = "/path/to/doc.pdf"

        mock_library.get.return_value = mock_doc
        mock_library.delete.return_value = True

        result = runner.invoke(app, ["delete", "--force", "12345678"])

        assert result.exit_code == 0
        assert "deleted" in result.output

    def test_delete_not_found(self, mock_library: MagicMock) -> None:
        """delete command should handle not found."""
        mock_library.get.side_effect = LookupError("document not found", ErrorCode.NOT_FOUND)

        result = runner.invoke(app, ["delete", "--force", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output
