"""Tests for CLI ask command."""

# pattern: Imperative Shell

from unittest.mock import MagicMock, patch
from uuid import uuid4

from typer.testing import CliRunner

from local_library.cli.main import app
from local_library.core.models import RAGResponse
from local_library.embeddings.base import Chunk, SearchResult

runner = CliRunner()


def _make_response(
    question: str = "What is attention?",
    answer: str = "Attention is a mechanism [@Smith2023].",
    citekey: str = "Smith2023",
    title: str = "Attention Paper",
    model: str = "test-model",
) -> RAGResponse:
    """Helper to create a RAGResponse for testing."""
    chunk = Chunk.create(doc_id=uuid4(), chunk_index=0, text="Test text")
    result = SearchResult(
        chunk=chunk,
        score=0.9,
        doc_title=title,
        doc_citekey=citekey,
        search_methods=frozenset({"vector"}),
    )
    return RAGResponse(
        question=question,
        answer=answer,
        context_chunks=(result,),
        model=model,
        retrieval_mode="hybrid",
    )


class TestAskCommand:
    """Tests for the ask CLI command."""

    @patch("local_library.cli.ask.is_vec_available", return_value=False)
    def test_ask_fails_without_vec(self, _mock_vec: MagicMock) -> None:
        """ask should fail gracefully when sqlite-vec is unavailable."""
        result = runner.invoke(app, ["ask", "What is X?"])

        assert result.exit_code == 1
        assert "sqlite-vec" in result.output.lower() or "sqlite-vec" in (result.stderr or "")

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_no_stream_returns_answer(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask --no-stream should print the answer text and sources."""
        response = _make_response()
        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.return_value = response
        mock_lib_cls.return_value = mock_lib

        result = runner.invoke(app, ["ask", "What is attention?", "--no-stream"])

        assert result.exit_code == 0
        assert "Attention is a mechanism" in result.output
        assert "Sources:" in result.output
        assert "Attention Paper" in result.output

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_json_output(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask --json should produce valid JSON with expected fields."""
        import json

        response = _make_response()
        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.return_value = response
        mock_lib_cls.return_value = mock_lib

        result = runner.invoke(app, ["ask", "What is attention?", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["question"] == "What is attention?"
        assert "Attention is a mechanism" in data["answer"]
        assert data["model"] == "test-model"
        assert data["retrieval_mode"] == "hybrid"
        assert len(data["sources"]) == 1
        assert data["sources"][0]["citekey"] == "Smith2023"

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_passes_model_flag(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask --model should pass model to Library constructor."""
        response = _make_response()
        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.return_value = response
        mock_lib_cls.return_value = mock_lib

        runner.invoke(
            app, ["ask", "Q?", "--model", "anthropic/claude-3-haiku", "--no-stream"]
        )

        mock_lib_cls.assert_called_once()
        call_kwargs = mock_lib_cls.call_args[1]
        assert call_kwargs["rag_model"] == "anthropic/claude-3-haiku"

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_passes_mode_flag(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask --mode should pass retrieval mode to query."""
        response = _make_response()
        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.return_value = response
        mock_lib_cls.return_value = mock_lib

        runner.invoke(app, ["ask", "Q?", "--mode", "fts", "--no-stream"])

        mock_lib.query.assert_called_once()
        call_kwargs = mock_lib.query.call_args[1]
        assert call_kwargs["mode"] == "fts"

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_passes_limit_flag(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask --limit should pass limit to query."""
        response = _make_response()
        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.return_value = response
        mock_lib_cls.return_value = mock_lib

        runner.invoke(app, ["ask", "Q?", "--limit", "5", "--no-stream"])

        mock_lib.query.assert_called_once()
        call_kwargs = mock_lib.query.call_args[1]
        assert call_kwargs["limit"] == 5

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    @patch("local_library.cli.ask.resolve_identifier")
    def test_ask_doc_flag_scopes_to_document(
        self,
        mock_resolve: MagicMock,
        mock_lib_cls: MagicMock,
        _mock_vec: MagicMock,
    ) -> None:
        """ask --doc should resolve identifier and pass doc_ids to query."""
        doc_id = uuid4()
        mock_doc = MagicMock()
        mock_doc.id = doc_id
        mock_resolve.return_value = mock_doc

        response = _make_response()
        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.return_value = response
        mock_lib_cls.return_value = mock_lib

        runner.invoke(app, ["ask", "Q?", "--doc", "@Smith2023", "--no-stream"])

        mock_resolve.assert_called_once_with("@Smith2023", mock_lib)
        call_kwargs = mock_lib.query.call_args[1]
        assert call_kwargs["doc_ids"] == [doc_id]

    def test_ask_invalid_mode(self) -> None:
        """ask with invalid mode should fail."""
        with patch("local_library.cli.ask.is_vec_available", return_value=True):
            result = runner.invoke(app, ["ask", "Q?", "--mode", "invalid"])

        assert result.exit_code == 1

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_empty_context_shows_message(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask with no relevant docs should show appropriate message."""
        response = RAGResponse(
            question="Q?",
            answer="I don't have relevant context to answer this question.",
            context_chunks=(),
            model="test-model",
            retrieval_mode="hybrid",
        )
        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.return_value = response
        mock_lib_cls.return_value = mock_lib

        result = runner.invoke(app, ["ask", "Q?", "--no-stream"])

        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert (
            "don't have relevant context" in output_lower
            or "no relevant" in output_lower
        )

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_json_with_empty_sources(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask --json with empty context should produce valid JSON with empty sources."""
        import json

        response = RAGResponse(
            question="Q?",
            answer="No context available.",
            context_chunks=(),
            model="test-model",
            retrieval_mode="hybrid",
        )
        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.return_value = response
        mock_lib_cls.return_value = mock_lib

        result = runner.invoke(app, ["ask", "Q?", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["sources"] == []

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_streaming_calls_query_stream(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """Default ask (streaming) should call query_stream and iterate tokens."""
        from local_library.rag.interface import RAGStream

        response = _make_response()
        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)

        # Create a mock stream that yields tokens and returns response
        mock_stream = MagicMock(spec=RAGStream)
        mock_stream.__iter__ = MagicMock(return_value=iter(["Hello", " world"]))
        mock_stream.to_response.return_value = response
        mock_lib.query_stream.return_value = mock_stream
        mock_lib_cls.return_value = mock_lib

        runner.invoke(app, ["ask", "What is X?"])

        # Should have called query_stream (not query)
        mock_lib.query_stream.assert_called_once()
        mock_lib.query.assert_not_called()
        mock_stream.to_response.assert_called_once()

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_rag_error_displays_cleanly(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask should display RAGError cleanly and exit 1."""
        from local_library.core.errors import ErrorCode, RAGError

        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.side_effect = RAGError("generation failed", ErrorCode.LLM_GENERATION_FAILED)
        mock_lib_cls.return_value = mock_lib

        result = runner.invoke(app, ["ask", "Q?", "--no-stream"])

        assert result.exit_code == 1

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_llm_error_displays_cleanly(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask should display LLMError cleanly and exit 1."""
        from local_library.core.errors import ErrorCode, LLMError

        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.side_effect = LLMError("model not found", ErrorCode.LLM_MODEL_NOT_FOUND)
        mock_lib_cls.return_value = mock_lib

        result = runner.invoke(app, ["ask", "Q?", "--no-stream"])

        assert result.exit_code == 1

    @patch("local_library.cli.ask.is_vec_available", return_value=True)
    @patch("local_library.cli.ask.Library")
    def test_ask_json_error_exits_cleanly(
        self, mock_lib_cls: MagicMock, _mock_vec: MagicMock
    ) -> None:
        """ask --json errors should produce JSON error output and exit cleanly."""
        from local_library.core.errors import ErrorCode, RAGError

        mock_lib = MagicMock()
        mock_lib.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib.__exit__ = MagicMock(return_value=False)
        mock_lib.query.side_effect = RAGError("generation failed", ErrorCode.LLM_GENERATION_FAILED)
        mock_lib_cls.return_value = mock_lib

        result = runner.invoke(app, ["ask", "Q?", "--json"])

        assert result.exit_code == 1
