"""Unit tests for the CLI search command."""

# pattern: Imperative Shell

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from local_library.cli.main import app
from local_library.core.errors import (
    EmbeddingError,
    ErrorCode,
    FTSQueryError,
)

runner = CliRunner()


@pytest.fixture
def mock_search_library():
    """Provide a mock Library for search CLI testing."""
    with patch("local_library.cli.search.Library") as mock_cls:
        mock_lib = MagicMock()
        mock_cls.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_lib


@pytest.fixture
def mock_vec_available():
    """Patch is_vec_available to return True."""
    with patch("local_library.cli.search.is_vec_available", return_value=True):
        yield


def _make_mock_result(
    text: str = "Sample text",
    score: float = 0.5,
    title: str | None = "Test Doc",
    citekey: str | None = "Test2023",
    methods: frozenset[str] | None = None,
) -> MagicMock:
    """Create a mock SearchResult."""
    if methods is None:
        methods = frozenset({"vector", "fts"})
    result = MagicMock()
    result.chunk.chunk_id = str(uuid4())
    result.chunk.doc_id = uuid4()
    result.chunk.chunk_index = 0
    result.chunk.text = text
    result.score = score
    result.doc_title = title
    result.doc_citekey = citekey
    result.search_methods = methods
    return result


class TestSearchCommand:
    """Tests for the search command."""

    def test_basic_search(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search command returns results in table format."""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [
            _make_mock_result(text="Machine learning result", score=0.8)
        ]
        mock_search_library.get_retriever.return_value = mock_retriever

        result = runner.invoke(app, ["search", "machine learning"])

        assert result.exit_code == 0
        assert "machine learning" in result.output.lower() or "Search" in result.output
        mock_search_library.get_retriever.assert_called_once_with(mode="hybrid")

    def test_json_output(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search --json outputs valid JSON with expected schema."""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [
            _make_mock_result(
                text="Test text",
                score=0.75,
                title="My Doc",
                citekey="Key2023",
                methods=frozenset({"vector"}),
            )
        ]
        mock_search_library.get_retriever.return_value = mock_retriever

        result = runner.invoke(app, ["search", "test", "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        item = parsed[0]
        assert "chunk_id" in item
        assert "doc_id" in item
        assert "score" in item
        assert "doc_title" in item
        assert "doc_citekey" in item
        assert "search_methods" in item
        assert "text" in item

    def test_mode_vector(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search --mode vector uses vector retriever."""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []
        mock_search_library.get_retriever.return_value = mock_retriever

        result = runner.invoke(app, ["search", "query", "--mode", "vector"])

        assert result.exit_code == 0
        mock_search_library.get_retriever.assert_called_once_with(mode="vector")

    def test_mode_fts(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search --mode fts uses FTS retriever."""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []
        mock_search_library.get_retriever.return_value = mock_retriever

        result = runner.invoke(app, ["search", "query", "--mode", "fts"])

        assert result.exit_code == 0
        mock_search_library.get_retriever.assert_called_once_with(mode="fts")

    def test_invalid_mode_rejected(self, mock_vec_available) -> None:
        """search --mode invalid exits with error."""
        result = runner.invoke(app, ["search", "query", "--mode", "invalid"])

        assert result.exit_code == 1

    def test_limit_parameter(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search --limit passes k parameter to retriever."""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []
        mock_search_library.get_retriever.return_value = mock_retriever

        result = runner.invoke(app, ["search", "query", "--limit", "5"])

        assert result.exit_code == 0
        mock_retriever.retrieve.assert_called_once()
        call_kwargs = mock_retriever.retrieve.call_args
        assert call_kwargs.kwargs.get("k") == 5 or call_kwargs[1].get("k") == 5

    def test_doc_filter(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search --doc resolves identifier and passes doc_ids."""
        mock_doc = MagicMock()
        mock_doc.id = uuid4()
        mock_search_library.get_by_citekey.return_value = mock_doc

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []
        mock_search_library.get_retriever.return_value = mock_retriever

        result = runner.invoke(app, ["search", "query", "--doc", "@Author2023"])

        assert result.exit_code == 0
        mock_retriever.retrieve.assert_called_once()
        call_kwargs = mock_retriever.retrieve.call_args
        doc_ids = call_kwargs.kwargs.get("doc_ids") or call_kwargs[1].get("doc_ids")
        assert doc_ids is not None
        assert mock_doc.id in doc_ids

    def test_empty_results(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search with no results shows appropriate message."""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []
        mock_search_library.get_retriever.return_value = mock_retriever

        result = runner.invoke(app, ["search", "nonexistent"])

        assert result.exit_code == 0
        assert "no results" in result.output.lower()

    def test_vec_unavailable(self) -> None:
        """search exits with error when sqlite-vec not available."""
        with patch("local_library.cli.search.is_vec_available", return_value=False):
            result = runner.invoke(app, ["search", "query"])

        assert result.exit_code == 1

    def test_fts_query_error(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search handles FTSQueryError gracefully."""
        mock_retriever = MagicMock()
        mock_retriever.retrieve.side_effect = FTSQueryError(
            "invalid FTS5 query syntax",
            ErrorCode.EMBEDDING_FTS_QUERY_SYNTAX,
            details={"query": '"unbalanced'},
        )
        mock_search_library.get_retriever.return_value = mock_retriever

        result = runner.invoke(app, ["search", '"unbalanced'])

        assert result.exit_code == 1

    def test_embedding_error(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search handles EmbeddingError gracefully."""
        mock_search_library.get_retriever.side_effect = EmbeddingError(
            "sqlite-vec extension not available",
            ErrorCode.EMBEDDING_EXTENSION_UNAVAILABLE,
        )

        result = runner.invoke(app, ["search", "query"])

        assert result.exit_code == 1

    def test_lookup_error_for_doc_filter(
        self, mock_search_library: MagicMock, mock_vec_available
    ) -> None:
        """search --doc with unknown identifier shows error."""
        mock_search_library.get_by_citekey.return_value = None
        mock_search_library.get_all_citekeys.return_value = []

        result = runner.invoke(app, ["search", "query", "--doc", "@Unknown"])

        assert result.exit_code == 1
