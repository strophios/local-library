# Phase 4: RAGInterface with Streaming

**Goal:** Full RAG orchestration with both blocking and streaming paths, developed test-first.

**Done when:** `query()` returns correct `RAGResponse` with mock LLMClient, `query_stream()` yields tokens and `to_response()` produces correct `RAGResponse`, empty-retrieval path skips LLM and returns appropriate response, all tests pass.

---

<!-- START_SUBCOMPONENT_A (tasks 1-4) -->
<!-- START_TASK_1 -->
### Task 1: Write tests for RAGInterface and RAGStream

**Files:**
- Modify: `tests/unit/test_rag_interface.py` (append new test classes)

Tests are written first (TDD). RAGInterface and RAGStream don't exist yet — tests
should fail with import/attribute errors.

**Step 1: Add imports**

At the top of `tests/unit/test_rag_interface.py`, add to the existing imports:
```python
from local_library.rag.interface import RAGInterface
```

**Step 2: Add RAGInterface test class**

Append to end of `tests/unit/test_rag_interface.py`:
```python


class TestRAGInterface:
    """Tests for RAGInterface orchestration."""

    def _make_interface(self, complete_return: str = "Answer text.", stream_tokens: list[str] | None = None):
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
        import pytest
        from unittest.mock import MagicMock

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
```

**Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_rag_interface.py -v -k "TestRAGInterface or TestRAGStream"`
Expected: FAIL — `RAGInterface` and `RAGStream` do not exist yet
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement RAGStream

**Files:**
- Modify: `src/local_library/rag/interface.py` (append after existing pure functions)

RAGStream is implemented first because RAGInterface.query_stream() depends on it.

**Step 1: Add imports to interface.py**

At the top of the file, after `from __future__ import annotations`, add:
```python

from collections.abc import Iterator
```

After the existing import `from local_library.embeddings.base import SearchResult`, add:
```python
from local_library.core.errors import ErrorCode, RAGError
from local_library.core.models import RAGResponse
```

**Step 2: Update pattern comment**

At the top of the file, change:
```python
# pattern: Functional Core
```
to:
```python
# pattern: Mixed (unavoidable)
# Reason: Pure functions (assemble_context, build_messages) and Imperative Shell
# (RAGInterface) colocated in same file. Separation into two files adds
# complexity without testability benefit — pure functions are tested directly,
# RAGInterface tested with mocks.
```

**Step 3: Add RAGStream class**

After the `build_messages()` function, add:
```python


class RAGStream:
    """Streaming wrapper for RAG query responses.

    Wraps a token iterator from the LLM, accumulating tokens during iteration.
    After iteration completes, call to_response() to build the final RAGResponse.

    The context_chunks are available immediately (before iteration starts),
    enabling the caller to display source information while streaming.

    Attributes:
        context_chunks: SearchResults used as context (available immediately).
    """

    def __init__(
        self,
        token_iter: Iterator[str],
        question: str,
        context_chunks: tuple[SearchResult, ...],
        model: str,
        retrieval_mode: str,
    ) -> None:
        """Initialize the streaming wrapper.

        Args:
            token_iter: Iterator yielding answer tokens from LLM.
            question: The original question.
            context_chunks: SearchResults used as context.
            model: Model identifier.
            retrieval_mode: Retrieval mode label.
        """
        self._token_iter = token_iter
        self._question = question
        self.context_chunks = context_chunks
        self._model = model
        self._retrieval_mode = retrieval_mode
        self._accumulated: list[str] = []
        self._exhausted = False

    def __iter__(self) -> Iterator[str]:
        """Yield answer tokens, accumulating them internally.

        Raises:
            RAGError: If the token stream fails mid-iteration.
        """
        try:
            for token in self._token_iter:
                self._accumulated.append(token)
                yield token
        except Exception as exc:
            raise RAGError(
                "LLM generation failed during streaming",
                ErrorCode.LLM_GENERATION_FAILED,
            ) from exc
        finally:
            self._exhausted = True

    def to_response(self) -> RAGResponse:
        """Build the complete RAGResponse from accumulated tokens.

        Should be called after iteration completes. If called before
        iteration finishes, builds response from tokens received so far.

        Returns:
            Complete RAGResponse with the accumulated answer.
        """
        return RAGResponse(
            question=self._question,
            answer="".join(self._accumulated),
            context_chunks=self.context_chunks,
            model=self._model,
            retrieval_mode=self._retrieval_mode,
        )
```

**Step 4: Run RAGStream tests to verify they pass**

Run: `uv run pytest tests/unit/test_rag_interface.py -v -k "TestRAGStream"`
Expected: All 7 TestRAGStream tests PASS

Run: `uv run pytest tests/unit/test_rag_interface.py -v -k "TestRAGInterface"`
Expected: Still FAIL — RAGInterface not implemented yet
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Implement RAGInterface

**Files:**
- Modify: `src/local_library/rag/interface.py` (add after RAGStream)

**Step 1: Add LLMClient import**

At the top of the file, after the `RAGResponse` import, add:
```python
from local_library.llm.base import LLMClient
```

**Step 2: Add RAGInterface class**

After the `RAGStream` class, add:
```python


class RAGInterface:
    """Orchestrates the RAG query pipeline.

    Coordinates context assembly, prompt construction, and LLM generation.
    Supports both blocking (query) and streaming (query_stream) paths.

    The pre-LLM gate skips the API call when retrieval returns zero results,
    saving latency and cost.
    """

    def __init__(self, llm_client: LLMClient, model: str) -> None:
        """Initialize the RAG interface.

        Args:
            llm_client: Client for LLM generation.
            model: Model identifier for attribution in RAGResponse.
        """
        self._llm_client = llm_client
        self._model = model

    def query(
        self,
        question: str,
        search_results: list[SearchResult],
        retrieval_mode: str = "hybrid",
    ) -> RAGResponse:
        """Execute a blocking RAG query.

        Assembles context from search results, constructs the prompt, calls the
        LLM, and returns a complete RAGResponse.

        If search_results is empty, returns a no-context response without
        calling the LLM (pre-LLM gate).

        Args:
            question: The user's natural language question.
            search_results: Retrieved chunks from the retriever.
            retrieval_mode: Retrieval mode label for the response.

        Returns:
            Complete RAGResponse with answer and source attribution.

        Raises:
            RAGError: If LLM generation fails.
        """
        context_chunks = tuple(search_results)

        # Pre-LLM gate: skip API call if no context
        if not search_results:
            return RAGResponse(
                question=question,
                answer="I don't have any relevant documents to answer this question.",
                context_chunks=context_chunks,
                model=self._model,
                retrieval_mode=retrieval_mode,
            )

        context = assemble_context(search_results)
        messages = build_messages(context, question)

        try:
            answer = self._llm_client.complete(messages, temperature=0.3)
        except Exception as exc:
            raise RAGError(
                "LLM generation failed",
                ErrorCode.LLM_GENERATION_FAILED,
            ) from exc

        return RAGResponse(
            question=question,
            answer=answer,
            context_chunks=context_chunks,
            model=self._model,
            retrieval_mode=retrieval_mode,
        )

    def query_stream(
        self,
        question: str,
        search_results: list[SearchResult],
        retrieval_mode: str = "hybrid",
    ) -> RAGStream:
        """Execute a streaming RAG query.

        Assembles context and constructs the prompt, then returns a RAGStream
        that yields tokens as they arrive from the LLM.

        If search_results is empty, returns a RAGStream that yields the
        no-context message without calling the LLM.

        Args:
            question: The user's natural language question.
            search_results: Retrieved chunks from the retriever.
            retrieval_mode: Retrieval mode label for the response.

        Returns:
            RAGStream that yields answer tokens and builds RAGResponse.
        """
        context_chunks = tuple(search_results)

        # Pre-LLM gate: skip API call if no context
        if not search_results:
            no_context_msg = "I don't have any relevant documents to answer this question."
            return RAGStream(
                token_iter=iter([no_context_msg]),
                question=question,
                context_chunks=context_chunks,
                model=self._model,
                retrieval_mode=retrieval_mode,
            )

        context = assemble_context(search_results)
        messages = build_messages(context, question)

        token_iter = self._llm_client.stream(messages, temperature=0.3)

        return RAGStream(
            token_iter=token_iter,
            question=question,
            context_chunks=context_chunks,
            model=self._model,
            retrieval_mode=retrieval_mode,
        )
```

**Step 3: Update rag/__init__.py to expose new classes**

In `src/local_library/rag/__init__.py`, add to the `__getattr__` function before the `raise AttributeError`:
```python
    elif name == "RAGStream":
        from local_library.rag.interface import RAGStream

        return RAGStream
```

Note: `RAGInterface` should already be in `__getattr__` from Phase 3. If not, add it too.

Update `__all__` to include `"RAGStream"`.

**Step 4: Run all RAGInterface and RAGStream tests**

Run: `uv run pytest tests/unit/test_rag_interface.py -v -k "TestRAGInterface or TestRAGStream"`
Expected: All tests PASS (both TestRAGInterface and TestRAGStream)
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Verify full test suite and commit

**Step 1: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass

**Step 2: Verify linting**

Run: `uv run ruff check src/local_library/rag/`
Expected: No errors

**Step 3: Commit**

```bash
git add src/local_library/rag/interface.py src/local_library/rag/__init__.py tests/unit/test_rag_interface.py
git commit -m "feat(rag): add RAGInterface and RAGStream orchestration

RAGInterface orchestrates the full RAG pipeline: context assembly,
prompt construction, and LLM generation with both blocking (query)
and streaming (query_stream) paths.

RAGStream wraps the token iterator with internal accumulation,
exposing to_response() for building the final RAGResponse.

Pre-LLM gate skips the API call when retrieval returns zero results.
Errors during generation are wrapped in RAGError."
```
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_A -->
