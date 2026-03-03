"""Tests for RAG context assembly and prompt construction."""

from uuid import uuid4

from local_library.embeddings.base import Chunk, SearchResult
from local_library.rag.interface import (
    _CONTEXT_SEPARATOR,
    _SYSTEM_PROMPT,
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
