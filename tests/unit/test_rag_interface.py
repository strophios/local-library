"""Tests for RAG context assembly and prompt construction."""

from uuid import uuid4

from local_library.embeddings.base import Chunk, SearchResult
from local_library.rag.interface import (
    _CONTEXT_SEPARATOR,
    _SYSTEM_PROMPT,
    RAGInterface,
    assemble_context,
    build_messages,
)


def _make_result(
    text: str = "chunk text",
    citekey: str | None = "Smith2023",
    section: str = "",
    score: float = 0.9,
) -> SearchResult:
    """Helper to create SearchResult for testing."""
    chunk = Chunk.create(doc_id=uuid4(), chunk_index=0, text=text, section=section)
    return SearchResult(
        chunk=chunk,
        score=score,
        doc_title="Test Doc",
        doc_citekey=citekey,
        search_methods=frozenset({"vector"}),
    )


class TestAssembleContext:
    """Tests for context assembly from search results."""

    def test_single_chunk_with_citekey(self) -> None:
        """Single chunk with citekey should produce attributed block."""
        result = _make_result(text="The key finding was X.", citekey="Smith2023")
        context = assemble_context([result])

        assert "[@Smith2023]" in context
        assert "The key finding was X." in context

    def test_single_chunk_with_section(self) -> None:
        """Chunk with section should include section in header."""
        result = _make_result(
            text="We used method Y.",
            citekey="Jones2021",
            section="Methods",
        )
        context = assemble_context([result])

        assert "[@Jones2021, §Methods]" in context
        assert "We used method Y." in context

    def test_multiple_chunks_separated(self) -> None:
        """Multiple chunks should be separated by horizontal rules."""
        results = [
            _make_result(text="First chunk.", citekey="A2023"),
            _make_result(text="Second chunk.", citekey="B2023"),
        ]
        context = assemble_context(results)

        assert _CONTEXT_SEPARATOR in context
        assert "First chunk." in context
        assert "Second chunk." in context

    def test_missing_citekey(self) -> None:
        """Chunk without citekey should use 'unknown source'."""
        result = _make_result(text="Some text.", citekey=None)
        context = assemble_context([result])

        assert "[unknown source]" in context
        assert "Some text." in context

    def test_empty_section_omitted(self) -> None:
        """Empty section should not produce §."""
        result = _make_result(text="Text.", citekey="X2023", section="")
        context = assemble_context([result])

        assert "§" not in context
        assert "[@X2023]" in context

    def test_empty_results_returns_empty_string(self) -> None:
        """No results should return empty string."""
        assert assemble_context([]) == ""

    def test_missing_citekey_with_section(self) -> None:
        """Missing citekey with section should still show section."""
        result = _make_result(text="Text.", citekey=None, section="Results")
        context = assemble_context([result])

        assert "[unknown source, §Results]" in context


class TestBuildMessages:
    """Tests for prompt construction."""

    def test_produces_system_and_user_messages(self) -> None:
        """Should produce exactly two messages: system and user."""
        messages = build_messages("some context", "What is X?")

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_system_message_contains_citation_instructions(self) -> None:
        """System message should instruct citekey citation format."""
        messages = build_messages("context", "question")

        assert "[@" in messages[0]["content"]
        assert messages[0]["content"] == _SYSTEM_PROMPT

    def test_user_message_context_first_question_last(self) -> None:
        """User message should have context before question."""
        messages = build_messages("Here is context.", "What is X?")
        user_content = messages[1]["content"]

        context_pos = user_content.index("Here is context.")
        question_pos = user_content.index("What is X?")
        assert context_pos < question_pos

    def test_empty_context_still_includes_question(self) -> None:
        """Empty context should still produce a valid user message with question."""
        messages = build_messages("", "What is X?")
        user_content = messages[1]["content"]

        assert "What is X?" in user_content

    def test_system_prompt_mentions_insufficient_context(self) -> None:
        """System prompt should instruct LLM to acknowledge insufficient context."""
        messages = build_messages("context", "question")
        system_content = messages[0]["content"]

        # Should mention handling insufficient context
        assert (
            "not contain enough information" in system_content.lower()
            or "insufficient" in system_content.lower()
            or "say so" in system_content.lower()
        )


class TestRAGInterface:
    """Tests for RAGInterface orchestration."""

    def _make_interface(
        self, complete_return: str = "Answer text.", stream_tokens: list[str] | None = None
    ):
        """Create RAGInterface with a mock LLMClient."""
        from unittest.mock import MagicMock

        mock_client = MagicMock()
        mock_client.complete.return_value = complete_return
        if stream_tokens is not None:
            mock_client.stream.return_value = iter(stream_tokens)
        else:
            mock_client.stream.return_value = iter(["Answer", " text", "."])

        interface = RAGInterface(llm_client=mock_client, model="test-model")
        return interface, mock_client

    def test_query_returns_rag_response(self) -> None:
        """query() should return a complete RAGResponse."""
        from local_library.core.models import RAGResponse

        interface, _ = self._make_interface(complete_return="Attention is [@Smith2023]...")
        results = [_make_result(text="chunk about attention", citekey="Smith2023")]

        response = interface.query("What is attention?", results)

        assert isinstance(response, RAGResponse)
        assert response.question == "What is attention?"
        assert response.answer == "Attention is [@Smith2023]..."
        assert response.model == "test-model"
        assert response.retrieval_mode == "hybrid"
        assert len(response.context_chunks) == 1

    def test_query_passes_assembled_context_to_llm(self) -> None:
        """query() should pass assembled context through to LLM."""
        interface, mock_client = self._make_interface()
        results = [_make_result(text="Important finding.", citekey="A2023")]

        interface.query("Question?", results)

        call_args = mock_client.complete.call_args
        messages = call_args[0][0]  # First positional arg
        user_content = messages[1]["content"]
        assert "Important finding." in user_content
        assert "[@A2023]" in user_content

    def test_query_empty_results_skips_llm(self) -> None:
        """query() with no results should skip LLM call (pre-LLM gate)."""
        interface, mock_client = self._make_interface()

        response = interface.query("Question?", [])

        mock_client.complete.assert_not_called()
        assert "don't have" in response.answer.lower() or "no relevant" in response.answer.lower()
        assert len(response.context_chunks) == 0

    def test_query_llm_error_raises_rag_error(self) -> None:
        """query() should wrap LLM errors in RAGError."""
        from unittest.mock import MagicMock

        import pytest

        from local_library.core.errors import RAGError

        mock_client = MagicMock()
        mock_client.complete.side_effect = Exception("API failure")
        interface = RAGInterface(llm_client=mock_client, model="test-model")

        with pytest.raises(RAGError):
            interface.query("Q?", [_make_result()])

    def test_query_uses_low_temperature(self) -> None:
        """query() should use low temperature for consistency."""
        interface, mock_client = self._make_interface()
        interface.query("Q?", [_make_result()])

        call_kwargs = mock_client.complete.call_args
        assert call_kwargs.kwargs.get("temperature") == 0.3

    def test_query_stream_returns_rag_stream(self) -> None:
        """query_stream() should return a RAGStream."""
        from local_library.rag.interface import RAGStream

        interface, _ = self._make_interface(stream_tokens=["Hello", " world"])
        results = [_make_result()]

        stream = interface.query_stream("Q?", results)

        assert isinstance(stream, RAGStream)

    def test_query_stream_empty_results_skips_llm(self) -> None:
        """query_stream() with no results should skip LLM (pre-LLM gate)."""
        interface, mock_client = self._make_interface()

        stream = interface.query_stream("Q?", [])

        mock_client.stream.assert_not_called()
        tokens = list(stream)
        assert len(tokens) == 1
        assert "don't have" in tokens[0].lower() or "no relevant" in tokens[0].lower()


class TestRAGStream:
    """Tests for RAGStream streaming accumulator."""

    def _make_stream(self, tokens: list[str] | None = None, **kwargs):
        """Create a RAGStream with given tokens."""
        from local_library.rag.interface import RAGStream

        if tokens is None:
            tokens = ["Hello", " ", "world"]

        defaults = {
            "token_iter": iter(tokens),
            "question": "Test question?",
            "context_chunks": (),
            "model": "test-model",
            "retrieval_mode": "hybrid",
        }
        defaults.update(kwargs)
        return RAGStream(**defaults)

    def test_iteration_yields_all_tokens(self) -> None:
        """Iterating RAGStream should yield all tokens in order."""
        stream = self._make_stream(["A", "B", "C"])

        collected = list(stream)

        assert collected == ["A", "B", "C"]

    def test_to_response_after_iteration(self) -> None:
        """to_response() after iteration should have complete answer."""
        from local_library.core.models import RAGResponse

        stream = self._make_stream(["Hello", " world"])

        list(stream)  # exhaust
        response = stream.to_response()

        assert isinstance(response, RAGResponse)
        assert response.answer == "Hello world"
        assert response.question == "Test question?"
        assert response.model == "test-model"

    def test_to_response_before_iteration(self) -> None:
        """to_response() before iteration should have empty answer."""
        stream = self._make_stream(["A", "B"])

        response = stream.to_response()

        assert response.answer == ""

    def test_to_response_partial_iteration(self) -> None:
        """to_response() after partial iteration should have partial answer."""
        stream = self._make_stream(["A", "B", "C"])

        it = iter(stream)
        next(it)  # consume "A"
        next(it)  # consume "B"
        # Don't consume "C"

        response = stream.to_response()
        assert response.answer == "AB"

    def test_context_chunks_available_immediately(self) -> None:
        """context_chunks should be available before iteration."""
        result = _make_result(citekey="Test2023")
        stream = self._make_stream(context_chunks=(result,))

        # Available before iterating
        assert len(stream.context_chunks) == 1
        assert stream.context_chunks[0].doc_citekey == "Test2023"

    def test_stream_error_raises_rag_error(self) -> None:
        """Errors during streaming should be wrapped in RAGError."""
        import pytest

        from local_library.core.errors import RAGError

        def failing_iter():
            yield "token1"
            raise Exception("Stream failed")

        stream = self._make_stream(token_iter=failing_iter())

        with pytest.raises(RAGError):
            list(stream)

    def test_stream_error_preserves_partial_tokens(self) -> None:
        """After a stream error, to_response() should have partial tokens."""
        from local_library.core.errors import RAGError

        def failing_iter():
            yield "good"
            raise Exception("Stream failed")

        stream = self._make_stream(token_iter=failing_iter())

        try:
            list(stream)
        except RAGError:
            pass

        response = stream.to_response()
        assert response.answer == "good"
