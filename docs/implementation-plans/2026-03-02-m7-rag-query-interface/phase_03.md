# Phase 3: RAG Data Models and Context Assembly

**Goal:** Pure-function context assembly and prompt construction, with RAGResponse data model.

**Done when:** Context assembly correctly formats chunks with citekeys/sections, handles edge cases (missing citekeys, empty sections), prompt construction produces well-formed message list, all tests pass.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Add RAGResponse dataclass to models.py

**Files:**
- Modify: `src/local_library/core/models.py` (after line 247)

**Step 1: Add TYPE_CHECKING import for SearchResult**

At line 9, change:
```python
from typing import Any
```
to:
```python
from typing import TYPE_CHECKING, Any
```

After line 10 (`from uuid import UUID, uuid4`), add:
```python

if TYPE_CHECKING:
    from local_library.embeddings.base import SearchResult
```

**Step 2: Add the RAGResponse dataclass**

After the `TextExtractionResult` class (line 247), add:
```python


@dataclass(frozen=True)
class RAGResponse:
    """Complete result of a RAG query.

    Captures the question, LLM-generated answer, contributing chunks,
    model used, and retrieval mode for display and serialization.

    Attributes:
        question: The original natural language question
        answer: LLM-generated answer text with citekey citations
        context_chunks: SearchResults used as context for generation
        model: LLM model identifier (e.g., "gemini/gemini-2.0-flash")
        retrieval_mode: Retrieval mode used ("hybrid", "vector", "fts")
    """

    question: str
    answer: str
    context_chunks: tuple["SearchResult", ...]
    model: str
    retrieval_mode: str
```

Note: Uses `tuple["SearchResult", ...]` (not `list`) because frozen dataclasses require immutable fields. The forward reference string `"SearchResult"` avoids a circular import since `SearchResult` is in `embeddings.base`.

**Step 3: Verify linting**

Run: `uv run ruff check src/local_library/core/models.py`
Expected: No errors
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Test RAGResponse dataclass

**Files:**
- Modify: `tests/unit/test_models.py` (add test class at end)

**Step 1: Add RAGResponse tests**

Append to end of `tests/unit/test_models.py`:
```python


class TestRAGResponse:
    """Tests for RAGResponse frozen dataclass."""

    def test_rag_response_creation(self) -> None:
        """RAGResponse should store all fields correctly."""
        from uuid import uuid4

        from local_library.core.models import RAGResponse
        from local_library.embeddings.base import Chunk, SearchResult

        chunk = Chunk.create(doc_id=uuid4(), chunk_index=0, text="Some text")
        result = SearchResult(
            chunk=chunk,
            score=0.9,
            doc_title="Test Doc",
            doc_citekey="Smith2023",
            search_methods=frozenset({"vector"}),
        )

        response = RAGResponse(
            question="What is attention?",
            answer="Attention is a mechanism...",
            context_chunks=(result,),
            model="gemini/gemini-2.0-flash",
            retrieval_mode="hybrid",
        )

        assert response.question == "What is attention?"
        assert response.answer == "Attention is a mechanism..."
        assert len(response.context_chunks) == 1
        assert response.context_chunks[0].doc_citekey == "Smith2023"
        assert response.model == "gemini/gemini-2.0-flash"
        assert response.retrieval_mode == "hybrid"

    def test_rag_response_is_frozen(self) -> None:
        """RAGResponse should be immutable."""
        from local_library.core.models import RAGResponse

        response = RAGResponse(
            question="Q",
            answer="A",
            context_chunks=(),
            model="test-model",
            retrieval_mode="hybrid",
        )

        import pytest

        with pytest.raises(AttributeError):
            response.answer = "modified"  # type: ignore[misc]

    def test_rag_response_empty_context(self) -> None:
        """RAGResponse should handle empty context (no-context path)."""
        from local_library.core.models import RAGResponse

        response = RAGResponse(
            question="Q",
            answer="I don't have relevant context.",
            context_chunks=(),
            model="test-model",
            retrieval_mode="hybrid",
        )

        assert len(response.context_chunks) == 0
```

**Step 2: Run tests**

Run: `uv run pytest tests/unit/test_models.py -v -k "TestRAGResponse"`
Expected: 3 tests pass
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-5) -->
<!-- START_TASK_3 -->
### Task 3: Create rag/ package with context assembly and prompt construction

**Files:**
- Create: `src/local_library/rag/__init__.py`
- Create: `src/local_library/rag/interface.py`

**Step 1: Create `src/local_library/rag/__init__.py`**

```python
"""RAG query interface - context assembly, prompt construction, and generation."""

# Lazy imports to prevent circular import on package initialization
# (follows same pattern as embeddings and ingestion modules)


def __getattr__(name: str) -> object:
    """Lazy-load rag submodules to avoid circular imports."""
    if name == "RAGInterface":
        from local_library.rag.interface import RAGInterface

        return RAGInterface
    elif name == "assemble_context":
        from local_library.rag.interface import assemble_context

        return assemble_context
    elif name == "build_messages":
        from local_library.rag.interface import build_messages

        return build_messages
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "RAGInterface",
    "assemble_context",
    "build_messages",
]
```

**Step 2: Create `src/local_library/rag/interface.py`**

```python
"""RAG query interface - context assembly, prompt construction, and orchestration.

Context assembly and prompt construction are pure functions (Functional Core).
RAGInterface orchestrates the full pipeline (Imperative Shell, added in Phase 4).
"""

# pattern: Functional Core

from __future__ import annotations

from local_library.embeddings.base import SearchResult

_SYSTEM_PROMPT = """\
You are a research assistant answering questions based on a personal document library. \
You have been given relevant excerpts from the library below.

Instructions:
- Answer the question using ONLY the provided context.
- Cite sources using citekey references in the format [@citekey] (e.g., [@Smith2023]).
- If the provided context does not contain enough information to answer the question, \
say so clearly rather than speculating.
- Be concise and direct.\
"""

_CONTEXT_SEPARATOR = "\n\n---\n\n"


def assemble_context(search_results: list[SearchResult]) -> str:
    """Format retrieved search results into an attributed context string.

    Each chunk is prefixed with its citekey and section header (when available).
    Chunks are separated by horizontal rules.

    Args:
        search_results: Retrieved chunks with metadata, in relevance order.

    Returns:
        Formatted context string ready for inclusion in a prompt.
        Empty string if no results provided.
    """
    if not search_results:
        return ""

    blocks: list[str] = []
    for result in search_results:
        header = _format_chunk_header(result)
        blocks.append(f"{header} {result.chunk.text}")

    return _CONTEXT_SEPARATOR.join(blocks)


def _format_chunk_header(result: SearchResult) -> str:
    """Build the attribution header for a single chunk.

    Format: [@citekey, §Section] or [@citekey] or [unknown source, §Section] or
    [unknown source].

    Args:
        result: A single search result.

    Returns:
        Formatted attribution header string.
    """
    citekey_part = f"@{result.doc_citekey}" if result.doc_citekey else "unknown source"
    section_part = f", §{result.chunk.section}" if result.chunk.section else ""
    return f"[{citekey_part}{section_part}]"


def build_messages(context: str, question: str) -> list[dict[str, str]]:
    """Construct the message list for the LLM call.

    Uses context-first, question-last ordering: the question sits in the
    high-attention position at the end of the prompt.

    Args:
        context: Formatted context string from assemble_context().
        question: The user's natural language question.

    Returns:
        List of message dicts with 'role' and 'content' keys.
    """
    user_content = f"Context:\n{context}\n\nQuestion: {question}" if context else f"Question: {question}"

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
```

**Step 3: Verify linting**

Run: `uv run ruff check src/local_library/rag/`
Expected: No errors
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Tests for context assembly and prompt construction

**Files:**
- Create: `tests/unit/test_rag_interface.py`

**Step 1: Create test file**

```python
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
        assert "not contain enough information" in system_content.lower() or \
               "insufficient" in system_content.lower() or \
               "say so" in system_content.lower()
```

**Step 2: Run tests**

Run: `uv run pytest tests/unit/test_rag_interface.py -v`
Expected: All tests pass
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Verify full test suite and commit

**Step 1: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass

**Step 2: Verify linting**

Run: `uv run ruff check src/local_library/rag/ src/local_library/core/models.py`
Expected: No errors

**Step 3: Commit**

```bash
git add src/local_library/core/models.py src/local_library/rag/__init__.py src/local_library/rag/interface.py tests/unit/test_models.py tests/unit/test_rag_interface.py
git commit -m "feat(rag): add RAGResponse model and context assembly functions

Add RAGResponse frozen dataclass to core models.
Create rag/ package with pure-function context assembly (formats
SearchResults with citekey/section attribution) and prompt construction
(system + user messages with context-first ordering).

Includes tests for all edge cases: missing citekeys, empty sections,
empty results, and message structure."
```
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->
