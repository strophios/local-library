"""Tests for MCP server tool functions."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from local_library.core.errors import EmbeddingError, ErrorCode, FTSQueryError, LookupError
from local_library.embeddings.base import Chunk, SearchResult
from local_library.mcp.server import search_library


def _make_chunk(doc_id=None, chunk_index=0, text="Sample text.", section="Intro"):
    """Create a Chunk for testing."""
    return Chunk(
        chunk_id=str(uuid4()),
        doc_id=doc_id or uuid4(),
        chunk_index=chunk_index,
        text=text,
        section=section,
        char_start=0,
        char_end=len(text),
        created_at=datetime.now(timezone.utc),
    )


def _make_result(score=0.95, doc_citekey="Author2023", doc_title="Test Doc", **kwargs):
    """Create a SearchResult for testing."""
    chunk_kwargs = {
        k: v for k, v in kwargs.items() if k in ("doc_id", "chunk_index", "text", "section")
    }
    return SearchResult(
        chunk=_make_chunk(**chunk_kwargs),
        score=score,
        doc_title=doc_title,
        doc_citekey=doc_citekey,
        search_methods=frozenset(["hybrid"]),
    )


class TestSearchLibrary:
    """Tests for the search_library tool function."""

    @pytest.fixture(autouse=True)
    def setup_mock_library(self):
        """Provide mock Library and retriever for all tests."""
        self.mock_library = MagicMock()
        self.mock_retriever = MagicMock()
        self.mock_library.get_retriever.return_value = self.mock_retriever

        with patch("local_library.mcp.server._library", self.mock_library):
            yield

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_basic_search_returns_formatted_markdown(self, _mock_vec) -> None:
        """Basic search returns markdown with citekey and score."""
        self.mock_retriever.retrieve.return_value = [_make_result()]
        result = search_library("machine learning")
        assert "@Author2023" in result
        assert "Results" in result

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_limit_clamped_to_100(self, _mock_vec) -> None:
        """Limit above 100 is clamped."""
        self.mock_retriever.retrieve.return_value = []
        search_library("query", limit=200)
        _, kwargs = self.mock_retriever.retrieve.call_args
        assert kwargs["k"] == 100

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_limit_minimum_is_1(self, _mock_vec) -> None:
        """Limit below 1 is clamped to 1."""
        self.mock_retriever.retrieve.return_value = []
        search_library("query", limit=-5)
        _, kwargs = self.mock_retriever.retrieve.call_args
        assert kwargs["k"] == 1

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_invalid_mode_returns_tool_error(self, _mock_vec) -> None:
        """Invalid mode returns Error: prefix."""
        result = search_library("query", mode="invalid")
        assert result.startswith("Error: ")
        assert "invalid" in result

    @patch("local_library.mcp.server.is_vec_available", return_value=False)
    def test_vec_unavailable_returns_user_error_for_hybrid(self, _mock_vec) -> None:
        """Missing sqlite-vec returns USER-FACING ERROR for hybrid mode."""
        result = search_library("query")
        assert "USER-FACING ERROR" in result

    @patch("local_library.mcp.server.is_vec_available", return_value=False)
    def test_fts_mode_works_without_vec(self, _mock_vec) -> None:
        """FTS mode works even without sqlite-vec."""
        self.mock_retriever.retrieve.return_value = []
        result = search_library("query", mode="fts")
        assert "USER-FACING ERROR" not in result

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_mode_forwarded_to_retriever(self, _mock_vec) -> None:
        """Mode parameter forwarded to get_retriever."""
        self.mock_retriever.retrieve.return_value = []
        search_library("query", mode="fts")
        self.mock_library.get_retriever.assert_called_with(mode="fts", rerank=True)

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_no_rerank_disables_reranking(self, _mock_vec) -> None:
        """no_rerank=True passes rerank=False to get_retriever."""
        self.mock_retriever.retrieve.return_value = []
        search_library("query", no_rerank=True)
        self.mock_library.get_retriever.assert_called_with(mode="hybrid", rerank=False)

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    @patch("local_library.mcp.server.resolve_identifier")
    def test_doc_id_resolved_and_passed(self, mock_resolve, _mock_vec) -> None:
        """doc_id is resolved via resolve_identifier and passed as doc_ids."""
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_resolve.return_value = mock_doc
        self.mock_retriever.retrieve.return_value = []

        search_library("query", doc_id="@Author2023")
        mock_resolve.assert_called_once_with("@Author2023", self.mock_library)
        _, kwargs = self.mock_retriever.retrieve.call_args
        assert kwargs["doc_ids"] == [mock_doc.id]

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    @patch("local_library.mcp.server.resolve_identifier")
    def test_lookup_error_includes_suggestions(self, mock_resolve, _mock_vec) -> None:
        """LookupError with suggestions formats them with @ prefix."""
        mock_resolve.side_effect = LookupError(
            "citekey not found: Auth2023",
            ErrorCode.NOT_FOUND,
            details={"citekey": "Auth2023", "suggestions": ["Author2023", "AuthorB2023"]},
        )
        result = search_library("query", doc_id="@Auth2023")
        assert result.startswith("Error: ")
        assert "@Author2023" in result
        assert "@AuthorB2023" in result

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_embedding_error_returns_user_error(self, _mock_vec) -> None:
        """EmbeddingError returns USER-FACING ERROR."""
        self.mock_library.get_retriever.side_effect = EmbeddingError(
            "model load failed", ErrorCode.EMBEDDING_MODEL_LOAD_FAILED
        )
        result = search_library("query")
        assert "USER-FACING ERROR" in result

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_fts_query_error_suggests_vector_mode(self, _mock_vec) -> None:
        """FTSQueryError returns tool error suggesting vector mode."""
        self.mock_retriever.retrieve.side_effect = FTSQueryError(
            "query syntax error", ErrorCode.EMBEDDING_FTS_QUERY_SYNTAX
        )
        result = search_library("query")
        assert result.startswith("Error: ")
        assert "vector" in result.lower()

    @patch("local_library.mcp.server.is_vec_available", return_value=True)
    def test_empty_results_returns_helpful_message(self, _mock_vec) -> None:
        """Empty results returns helpful suggestion, not error."""
        self.mock_retriever.retrieve.return_value = []
        result = search_library("obscure query")
        assert "no results" in result.lower()
        assert "obscure query" in result
