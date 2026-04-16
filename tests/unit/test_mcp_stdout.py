"""Tests that MCP server components don't write to stdout.

The stdio transport reserves stdout for JSON-RPC protocol messages.
Any stdout output from Library, formatters, or tool functions would
corrupt the protocol stream.
"""

import io
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from local_library.core.models import Document, DocumentStatus, EmbeddingStatus
from local_library.mcp.formatters import (
    format_document,
    format_document_list,
    format_document_text,
    format_empty_results,
    format_search_results,
    format_tool_error,
    format_user_error,
)


class TestFormatterStdoutDiscipline:
    """Verify formatters never write to stdout."""

    def test_format_search_results_no_stdout(self) -> None:
        """format_search_results produces no stdout output."""
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            format_search_results([], "test query")
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == "", f"Unexpected stdout: {captured.getvalue()!r}"

    def test_format_user_error_no_stdout(self) -> None:
        """format_user_error produces no stdout output."""
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            format_user_error("test error")
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == ""

    def test_format_tool_error_no_stdout(self) -> None:
        """format_tool_error produces no stdout output."""
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            format_tool_error("test error")
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == ""

    def test_format_empty_results_no_stdout(self) -> None:
        """format_empty_results produces no stdout output."""
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            format_empty_results("test query")
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == ""

    def test_format_document_no_stdout(self) -> None:
        """format_document produces no stdout output."""
        doc = Document(
            id=uuid4(),
            original_path="/p.pdf",
            content_hash="abc",
            storage_path="/s/abc.pdf",
            status=DocumentStatus.READY,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            format_document(doc, chunk_count=0)
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == ""

    def test_format_document_list_no_stdout(self) -> None:
        """format_document_list produces no stdout output."""
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            format_document_list([], total=0)
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == ""

    def test_format_document_text_no_stdout(self) -> None:
        """format_document_text produces no stdout output."""
        doc = Document(
            id=uuid4(),
            original_path="/p.pdf",
            content_hash="abc",
            storage_path="/s/abc.pdf",
            status=DocumentStatus.READY,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            format_document_text(doc, text="content", chunks=None, total_chunks=1)
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == ""


class TestToolFunctionStdoutDiscipline:
    """Verify tool functions don't write to stdout when called."""

    @pytest.fixture(autouse=True)
    def setup_mock_library(self):
        """Mock Library so tools can execute without real database."""
        self.mock_library = MagicMock()
        self.mock_retriever = MagicMock()
        self.mock_library.get_retriever.return_value = self.mock_retriever
        self.mock_retriever.retrieve.return_value = []
        self.mock_library.list.return_value = []
        self.mock_library.get_chunk_count.return_value = 0

        with patch("local_library.mcp.server._library", self.mock_library):
            yield

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_search_library_no_stdout(self, _mock_vec) -> None:
        """search_library produces no stdout output."""
        from local_library.mcp.server import search_library

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            search_library("test query")
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == "", f"Unexpected stdout: {captured.getvalue()!r}"

    def test_list_documents_no_stdout(self) -> None:
        """list_documents produces no stdout output."""
        from local_library.mcp.server import list_documents

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            list_documents()
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == "", f"Unexpected stdout: {captured.getvalue()!r}"

    @patch("local_library.mcp.server.resolve_identifier")
    def test_show_document_no_stdout(self, mock_resolve) -> None:
        """show_document produces no stdout output."""
        from local_library.mcp.server import show_document

        mock_doc = MagicMock()
        mock_doc.id = MagicMock()
        mock_doc.citekey = "Test2023"
        mock_doc.title = "Test"
        mock_doc.authors = None
        mock_doc.issued_date = None
        mock_doc.status = MagicMock(value="ready")
        mock_doc.embedding_status = MagicMock(value="current")
        mock_doc.csl_json = None
        mock_doc.original_path = "/test.pdf"
        mock_resolve.return_value = mock_doc

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            show_document("@Test2023")
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == "", f"Unexpected stdout: {captured.getvalue()!r}"

    @patch("local_library.mcp.server.resolve_identifier")
    def test_get_document_text_no_stdout(self, mock_resolve) -> None:
        """get_document_text produces no stdout output."""
        from local_library.mcp.server import get_document_text

        mock_doc = MagicMock()
        mock_doc.extracted_path = None  # Triggers error path (simplest)
        mock_doc.citekey = "Test2023"
        mock_doc.status = MagicMock(value="ready")
        mock_resolve.return_value = mock_doc

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            get_document_text("@Test2023")
        finally:
            sys.stdout = old_stdout
        assert captured.getvalue() == "", f"Unexpected stdout: {captured.getvalue()!r}"
