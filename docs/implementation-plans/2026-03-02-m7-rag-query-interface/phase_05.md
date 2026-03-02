# Phase 5: Library Integration

**Goal:** Wire RAGInterface into Library with lazy initialization.

**Done when:** `Library.query()` produces correct RAGResponse with mock LLMClient, lazy initialization works (LLMClient not created until first query), error handling pipeline surfaces LLMError/RAGError correctly, tests pass.

---

<!-- START_SUBCOMPONENT_A (tasks 1-4) -->
<!-- START_TASK_1 -->
### Task 1: Write tests for Library.query() and Library.query_stream()

**Files:**
- Modify: `tests/unit/test_library.py` (append new test class)

Tests first — these define the expected contract before implementation.

**Step 1: Add test class**

Append to end of `tests/unit/test_library.py`:
```python


class TestLibraryQuery:
    """Tests for Library RAG query methods."""

    @pytest.fixture
    def library(self, temp_dir: Path) -> Library:
        """Provide an initialized Library for testing."""
        return Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            text_extraction_enabled=False,
            embed_on_add=False,
        )

    def test_query_returns_rag_response(self, library: Library) -> None:
        """query() should return a RAGResponse."""
        from unittest.mock import MagicMock

        from local_library.core.models import RAGResponse
        from local_library.embeddings.base import Chunk, SearchResult

        # Set up mock retriever
        chunk = Chunk.create(doc_id=__import__("uuid").uuid4(), chunk_index=0, text="Test text")
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [
            SearchResult(
                chunk=chunk,
                score=0.9,
                doc_title="Test",
                doc_citekey="Test2023",
                search_methods=frozenset({"vector"}),
            )
        ]

        # Set up mock LLM client
        mock_llm = MagicMock()
        mock_llm.complete.return_value = "The answer is [@Test2023]..."

        # Inject mocks
        library._llm_client = mock_llm
        library._rag_model = "test-model"

        response = library.query(
            "What is the answer?",
            retriever=mock_retriever,
        )

        assert isinstance(response, RAGResponse)
        assert response.question == "What is the answer?"
        assert "[@Test2023]" in response.answer
        assert response.model == "test-model"

    def test_query_empty_retrieval_skips_llm(self, library: Library) -> None:
        """query() with no retrieval results should skip LLM."""
        from unittest.mock import MagicMock

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []

        mock_llm = MagicMock()
        library._llm_client = mock_llm
        library._rag_model = "test-model"

        response = library.query("Question?", retriever=mock_retriever)

        mock_llm.complete.assert_not_called()
        assert len(response.context_chunks) == 0

    def test_query_stream_returns_rag_stream(self, library: Library) -> None:
        """query_stream() should return a RAGStream."""
        from unittest.mock import MagicMock

        from local_library.embeddings.base import Chunk, SearchResult
        from local_library.rag.interface import RAGStream

        chunk = Chunk.create(doc_id=__import__("uuid").uuid4(), chunk_index=0, text="Text")
        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = [
            SearchResult(
                chunk=chunk,
                score=0.9,
                doc_title="Test",
                doc_citekey="Test2023",
                search_methods=frozenset({"vector"}),
            )
        ]

        mock_llm = MagicMock()
        mock_llm.stream.return_value = iter(["token1", "token2"])
        library._llm_client = mock_llm
        library._rag_model = "test-model"

        stream = library.query_stream("Question?", retriever=mock_retriever)

        assert isinstance(stream, RAGStream)
        tokens = list(stream)
        assert tokens == ["token1", "token2"]

    def test_query_lazy_inits_llm_client(self, library: Library) -> None:
        """query() should lazily create LLMClient on first call."""
        from unittest.mock import MagicMock, patch

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []

        # No _llm_client set — should be created lazily
        assert library._llm_client is None

        with patch(
            "local_library.core.library.LiteLLMClient"
        ) as mock_litellm_cls:
            mock_instance = MagicMock()
            mock_litellm_cls.return_value = mock_instance

            library.query("Q?", retriever=mock_retriever)

            mock_litellm_cls.assert_called_once()
            assert library._llm_client is mock_instance

    def test_query_reuses_llm_client(self, library: Library) -> None:
        """query() should reuse existing LLMClient across calls."""
        from unittest.mock import MagicMock

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []

        mock_llm = MagicMock()
        library._llm_client = mock_llm
        library._rag_model = "test-model"

        library.query("Q1?", retriever=mock_retriever)
        library.query("Q2?", retriever=mock_retriever)

        # LLMClient should be same instance
        assert library._llm_client is mock_llm

    def test_query_passes_retrieval_params(self, library: Library) -> None:
        """query() should pass limit and doc_ids to retriever."""
        from unittest.mock import MagicMock
        from uuid import uuid4

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []

        mock_llm = MagicMock()
        library._llm_client = mock_llm
        library._rag_model = "test-model"

        doc_id = uuid4()
        library.query(
            "Q?",
            retriever=mock_retriever,
            limit=5,
            doc_ids=[doc_id],
        )

        mock_retriever.retrieve.assert_called_once_with(
            "Q?", k=5, doc_ids=[doc_id],
        )

    def test_query_default_model(self, temp_dir: Path) -> None:
        """Library should use configured model for RAG queries."""
        from unittest.mock import MagicMock

        lib = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            text_extraction_enabled=False,
            embed_on_add=False,
            rag_model="anthropic/claude-3-haiku",
        )

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []

        mock_llm = MagicMock()
        lib._llm_client = mock_llm

        response = lib.query("Q?", retriever=mock_retriever)

        assert response.model == "anthropic/claude-3-haiku"

    def test_query_propagates_rag_error(self, library: Library) -> None:
        """query() should propagate RAGError from RAGInterface."""
        from unittest.mock import MagicMock

        from local_library.core.errors import RAGError

        mock_retriever = MagicMock()
        mock_retriever.retrieve.return_value = []

        mock_llm = MagicMock()
        library._llm_client = mock_llm
        library._rag_model = "test-model"

        # Mock _get_rag_interface to return a RAGInterface that raises
        mock_rag = MagicMock()
        mock_rag.query.side_effect = RAGError("generation failed")
        library._rag_interface = mock_rag

        with pytest.raises(RAGError, match="generation failed"):
            library.query("Q?", retriever=mock_retriever)

    def test_query_propagates_embedding_error(self, library: Library) -> None:
        """query() should propagate EmbeddingError from retriever."""
        from unittest.mock import MagicMock

        from local_library.core.errors import EmbeddingError

        mock_retriever = MagicMock()
        mock_retriever.retrieve.side_effect = EmbeddingError("vec unavailable")

        mock_llm = MagicMock()
        library._llm_client = mock_llm
        library._rag_model = "test-model"

        with pytest.raises(EmbeddingError, match="vec unavailable"):
            library.query("Q?", retriever=mock_retriever)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_library.py -v -k "TestLibraryQuery"`
Expected: FAIL — `query()` and `query_stream()` methods don't exist, `rag_model` constructor param doesn't exist
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add constructor parameters and lazy init attributes

**Files:**
- Modify: `src/local_library/core/library.py`

**Step 1: Add `rag_model` parameter to constructor**

At line 107 (after `embedding_batch_size: int = 32,`), add:
```python
        rag_model: str = "gemini/gemini-2.0-flash",
```

In the docstring (around line 124), add before the closing `"""`:
```python
            rag_model: LLM model identifier for RAG queries (default: "gemini/gemini-2.0-flash").
```

**Step 2: Add lazy init attributes**

After line 170 (`self._embedding_storage = None  # Lazy init when needed`), add:
```python

        # RAG query components (lazy init on first query() call)
        self._rag_model = rag_model
        self._llm_client = None  # Lazy: created on first query
        self._rag_interface = None  # Lazy: created on first query
```

**Step 3: Verify linting**

Run: `uv run ruff check src/local_library/core/library.py`
Expected: No errors
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Implement Library.query() and Library.query_stream()

**Files:**
- Modify: `src/local_library/core/library.py` (add methods after `delete()`)

**Step 1: Add TYPE_CHECKING imports**

In the existing `if TYPE_CHECKING:` block (after `from local_library.embeddings.base import Retriever`), add:
```python
    from local_library.core.models import RAGResponse
    from local_library.rag.interface import RAGStream
```

**Step 2: Add query() and query_stream() methods**

After the `delete()` method (line 948), add:
```python

    # --- RAG Query Operations ---

    def _get_rag_interface(self):
        """Get or create RAGInterface instance.

        Lazily initializes LLMClient and RAGInterface on first call.

        Returns:
            Configured RAGInterface instance.
        """
        if self._rag_interface is None:
            if self._llm_client is None:
                from local_library.llm.litellm_client import LiteLLMClient

                self._llm_client = LiteLLMClient(model=self._rag_model)

            from local_library.rag.interface import RAGInterface

            self._rag_interface = RAGInterface(
                llm_client=self._llm_client,
                model=self._rag_model,
            )

        return self._rag_interface

    def query(
        self,
        question: str,
        retriever: "Retriever | None" = None,
        mode: str = "hybrid",
        limit: int = 10,
        doc_ids: list[UUID] | None = None,
    ) -> "RAGResponse":
        """Ask a question and get a RAG-generated answer.

        Retrieves relevant document chunks, assembles context, and generates
        an LLM answer with source citations.

        Args:
            question: Natural language question.
            retriever: Pre-configured retriever (if None, creates one via get_retriever).
            mode: Retrieval mode if creating retriever ("hybrid", "vector", "fts").
            limit: Maximum number of context chunks to retrieve.
            doc_ids: Optional document ID filter.

        Returns:
            RAGResponse with answer, source chunks, and model info.

        Raises:
            RAGError: If LLM generation fails.
            EmbeddingError: If retriever creation fails (sqlite-vec unavailable).
        """
        from local_library.core.models import RAGResponse

        if retriever is None:
            retriever = self.get_retriever(mode=mode)

        search_results = retriever.retrieve(question, k=limit, doc_ids=doc_ids)

        rag = self._get_rag_interface()
        return rag.query(question, search_results, retrieval_mode=mode)

    def query_stream(
        self,
        question: str,
        retriever: "Retriever | None" = None,
        mode: str = "hybrid",
        limit: int = 10,
        doc_ids: list[UUID] | None = None,
    ) -> "RAGStream":
        """Ask a question and get a streaming RAG-generated answer.

        Like query(), but returns a RAGStream that yields tokens as they
        arrive from the LLM.

        Args:
            question: Natural language question.
            retriever: Pre-configured retriever (if None, creates one via get_retriever).
            mode: Retrieval mode if creating retriever ("hybrid", "vector", "fts").
            limit: Maximum number of context chunks to retrieve.
            doc_ids: Optional document ID filter.

        Returns:
            RAGStream yielding answer tokens.

        Raises:
            RAGError: If LLM generation fails during streaming.
            EmbeddingError: If retriever creation fails (sqlite-vec unavailable).
        """
        if retriever is None:
            retriever = self.get_retriever(mode=mode)

        search_results = retriever.retrieve(question, k=limit, doc_ids=doc_ids)

        rag = self._get_rag_interface()
        return rag.query_stream(question, search_results, retrieval_mode=mode)
```

**Step 3: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_library.py -v -k "TestLibraryQuery"`
Expected: All 9 tests PASS
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Verify full test suite and commit

**Step 1: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass

**Step 2: Verify linting**

Run: `uv run ruff check src/local_library/core/library.py`
Expected: No errors

**Step 3: Commit**

```bash
git add src/local_library/core/library.py tests/unit/test_library.py
git commit -m "feat(core): add Library.query() and query_stream() for RAG

Wire RAGInterface into Library with lazy initialization of LLMClient
and RAGInterface on first query. Constructor accepts rag_model parameter.

query() and query_stream() accept optional pre-configured retriever
or create one via get_retriever(). Both delegate to RAGInterface
after retrieval.

Tests verify lazy init, retriever parameter passing, empty-result
handling, and model configuration."
```
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_A -->
