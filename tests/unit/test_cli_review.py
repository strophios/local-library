"""Unit tests for review command."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from typer.testing import CliRunner

from local_library.cli.main import app
from local_library.core.models import DocumentStatus

runner = CliRunner()


@pytest.fixture
def mock_library_review():
    """Provide a mock Library for review command testing."""
    with patch("local_library.cli.review.Library") as mock_lib_cls:
        mock_lib = MagicMock()
        mock_lib_cls.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib_cls.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_lib


class TestReviewCommand:
    """Tests for review command."""

    def test_review_opens_pdf_then_markdown_then_update(
        self, mock_library_review: MagicMock
    ) -> None:
        """review should open PDF (non-blocking), markdown (blocking), then update."""
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

        mock_library_review.get.return_value = mock_doc
        mock_library_review.get_all_citekeys.return_value = ["Smith2023"]

        call_order = []

        def track_popen(*args, **kwargs):
            call_order.append("pdf_open")
            return MagicMock()

        def track_run_markdown(*args, **kwargs):
            call_order.append("markdown_open")

        def track_run_editor(*args, **kwargs):
            call_order.append("editor_open")

        # Mock to return empty file (abort update)
        with (
            patch("local_library.cli.review.find_editor", return_value="/usr/bin/nvim"),
            patch("local_library.cli.review._open_pdf", side_effect=track_popen),
            patch("local_library.cli.review._open_markdown", side_effect=track_run_markdown),
            patch("local_library.cli.review._run_update_workflow", return_value=None),
        ):
            result = runner.invoke(app, ["review", "12345678"])

            assert result.exit_code == 0
            # PDF should open before markdown
            assert call_order == ["pdf_open", "markdown_open"]

    def test_review_no_extracted_path(self, mock_library_review: MagicMock) -> None:
        """review should error if no markdown available."""
        mock_doc = MagicMock()
        mock_doc.id = UUID("12345678-1234-1234-1234-123456789abc")
        mock_doc.extracted_path = None
        mock_doc.storage_path = "/path/to/doc.pdf"
        mock_doc.status = DocumentStatus.PENDING

        mock_library_review.get.return_value = mock_doc

        result = runner.invoke(app, ["review", "12345678"])

        assert result.exit_code == 1
        assert "no extracted markdown" in result.output.lower()

    def test_review_citekey_lookup(self, mock_library_review: MagicMock) -> None:
        """review @citekey should use citekey lookup."""
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

        mock_library_review.get_by_citekey.return_value = mock_doc
        mock_library_review.get_all_citekeys.return_value = ["Smith2023"]

        with (
            patch("local_library.cli.review.find_editor", return_value="/usr/bin/nvim"),
            patch("local_library.cli.review._open_pdf"),
            patch("local_library.cli.review._open_markdown"),
            patch("local_library.cli.review._run_update_workflow", return_value=None),
        ):
            result = runner.invoke(app, ["review", "@Smith2023"])

            assert result.exit_code == 0
            mock_library_review.get_by_citekey.assert_called_once_with("Smith2023")
