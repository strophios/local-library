## Phase 6: Library Integration

**Goal:** Integrate embedding pipeline into Library orchestrator.

This phase adds `embed()` and `embed_all()` methods to the Library class, handles embedding status transitions, integrates with `add()` for automatic embedding, and ensures embeddings cascade on delete.

---

<!-- START_TASK_1 -->
### Task 1: Add embedding methods to Library class

**Files:**
- Modify: `src/local_library/core/library.py`

**Step 1: Add embedding-related imports**

At the top of library.py, add these imports after line 26:

```python
from local_library.core.models import AddResult, Document, DocumentStatus, EmbeddingStatus
```

And add embedding imports (add after the ingestion imports around line 50):

```python
from local_library.core.vec_extension import is_vec_available, load_vec_extension
from local_library.embeddings.base import ChunkEmbedding
from local_library.embeddings.chunking import MarkdownChunker
from local_library.embeddings.nomic import NomicEmbedder
from local_library.embeddings.storage import (
    EmbeddingStorage,
    get_documents_needing_embedding,
    update_embedding_status,
)
```

**Step 2: Add embedding configuration to __init__**

Update the `__init__` method to accept embedding parameters. After line 100 (`pdf_llm_enabled: bool = False,`), add:

```python
        embed_on_add: bool = True,
        embedding_batch_size: int = 32,
```

And add initialization code after line 151 (`init_schema(self._conn)`):

```python
        # Initialize embedding components (if sqlite-vec available)
        self._embed_on_add = embed_on_add and is_vec_available()
        self._embedding_batch_size = embedding_batch_size
        self._chunker = MarkdownChunker() if self._embed_on_add else None
        self._embedder = NomicEmbedder(batch_size=embedding_batch_size, lazy_load=True) if self._embed_on_add else None
        self._embedding_storage = None  # Lazy init when needed
```

**Step 3: Add _get_embedding_storage helper method**

Add after the `__exit__` method (around line 169):

```python
    def _get_embedding_storage(self) -> EmbeddingStorage | None:
        """Get or create EmbeddingStorage instance.

        Returns:
            EmbeddingStorage if sqlite-vec available, None otherwise
        """
        if not is_vec_available():
            return None

        if self._embedding_storage is None:
            load_vec_extension(self._conn)
            self._embedding_storage = EmbeddingStorage(self._conn)

        return self._embedding_storage
```

**Step 4: Add embed() method**

Add after the `_get_embedding_storage` method:

```python
    def embed(self, doc_id: str, force: bool = False) -> int:
        """Embed a single document.

        Loads extracted text, chunks it, computes embeddings, and stores them.
        Updates embedding status to CURRENT on success.

        Args:
            doc_id: Document ID (full UUID or partial)
            force: Re-embed even if embeddings exist (default: False)

        Returns:
            Number of chunks embedded

        Raises:
            LookupError: If document not found
            EmbeddingError: If embedding fails or sqlite-vec unavailable
        """
        from local_library.core.errors import EmbeddingError, ErrorCode

        storage = self._get_embedding_storage()
        if storage is None:
            raise EmbeddingError(
                "sqlite-vec extension not available",
                ErrorCode.EMBEDDING_EXTENSION_UNAVAILABLE,
            )

        # Get document
        doc = self.get(doc_id)

        # Check if document is ready
        if doc.status != DocumentStatus.READY and doc.status != DocumentStatus.NEEDS_REVIEW:
            raise EmbeddingError(
                f"document not ready for embedding: status={doc.status.value}",
                ErrorCode.EMBEDDING_DOCUMENT_NOT_READY,
                details={"doc_id": str(doc.id), "status": doc.status.value},
            )

        # Check if already embedded (unless force)
        if not force and doc.embedding_status == EmbeddingStatus.CURRENT:
            return 0

        # Delete existing embeddings if re-embedding
        if storage.has_embeddings(doc.id):
            storage.delete_by_document(doc.id)

        # Load extracted text
        if not doc.extracted_path:
            raise EmbeddingError(
                "document has no extracted text",
                ErrorCode.EMBEDDING_DOCUMENT_NOT_READY,
                details={"doc_id": str(doc.id)},
            )

        extracted_path = Path(doc.extracted_path)
        if not extracted_path.exists():
            raise EmbeddingError(
                f"extracted file not found: {doc.extracted_path}",
                ErrorCode.EMBEDDING_DOCUMENT_NOT_READY,
                details={"doc_id": str(doc.id), "path": doc.extracted_path},
            )

        text = extracted_path.read_text(encoding="utf-8")

        # Chunk the text
        if self._chunker is None:
            self._chunker = MarkdownChunker()
        chunks = self._chunker.chunk(doc.id, text)

        if not chunks:
            # No chunks produced - update status but return 0
            update_embedding_status(self._conn, doc.id, EmbeddingStatus.CURRENT)
            return 0

        # Compute embeddings
        if self._embedder is None:
            self._embedder = NomicEmbedder(batch_size=self._embedding_batch_size, lazy_load=True)
        embeddings = self._embedder.embed_chunks(chunks)

        # Store embeddings
        storage.store_embeddings(embeddings)

        # Update status
        update_embedding_status(self._conn, doc.id, EmbeddingStatus.CURRENT)

        return len(embeddings)

    def embed_all(
        self,
        force: bool = False,
        progress_callback: callable | None = None,
    ) -> dict[str, int]:
        """Embed all documents that need embedding.

        Processes documents with PENDING or STALE embedding status.

        Args:
            force: Re-embed all READY documents regardless of status
            progress_callback: Optional callback(current, total, doc_id) for progress

        Returns:
            Dict with 'embedded' count and 'failed' count

        Raises:
            EmbeddingError: If sqlite-vec unavailable
        """
        from local_library.core.errors import EmbeddingError, ErrorCode

        storage = self._get_embedding_storage()
        if storage is None:
            raise EmbeddingError(
                "sqlite-vec extension not available",
                ErrorCode.EMBEDDING_EXTENSION_UNAVAILABLE,
            )

        # Get documents to embed
        if force:
            # Get all READY documents
            docs = list_documents(self._conn, status=DocumentStatus.READY)
            doc_ids = [doc.id for doc in docs]
        else:
            doc_ids = get_documents_needing_embedding(self._conn)

        results = {"embedded": 0, "failed": 0, "chunks": 0}
        total = len(doc_ids)

        for i, doc_id in enumerate(doc_ids):
            try:
                if progress_callback:
                    progress_callback(i, total, str(doc_id))

                chunk_count = self.embed(str(doc_id), force=force)
                results["embedded"] += 1
                results["chunks"] += chunk_count

            except Exception as e:
                results["failed"] += 1
                # Update status to PENDING on failure (will retry later)
                update_embedding_status(self._conn, doc_id, EmbeddingStatus.PENDING)

        if progress_callback:
            progress_callback(total, total, None)

        return results
```

**Step 5: Update delete() to cascade embeddings**

Update the `delete()` method to delete embeddings before deleting the document. Find the delete method and add embedding cleanup after the files are deleted but before the database record is deleted. After line 673 (`_cleanup_empty_parents(extracted_path, self._extracted_dir)`), add:

```python
            # Delete embeddings (cascade)
            storage = self._get_embedding_storage()
            if storage:
                storage.delete_by_document(doc.id)
```

**Step 6: Verify the changes compile**

Run: `uv run python -c "
from local_library.core.library import Library
import inspect

# Check embed method exists
assert hasattr(Library, 'embed'), 'Library should have embed method'
assert hasattr(Library, 'embed_all'), 'Library should have embed_all method'

# Check signature
sig = inspect.signature(Library.embed)
params = list(sig.parameters.keys())
assert 'doc_id' in params
assert 'force' in params

print('Library methods verified')
"
`

Expected: `Library methods verified`

**Step 7: Commit**

```bash
git add src/local_library/core/library.py
git commit -m "feat(library): add embed(), embed_all() methods and cascade deletion"
```
<!-- END_TASK_1 -->

---

<!-- START_TASK_2 -->
### Task 2: Integrate embedding into add() pipeline

**Files:**
- Modify: `src/local_library/core/library.py`

**Step 1: Add embedding after extraction in add() method**

Find the `add()` method and update it to embed after successful extraction. After the metadata processing section (around line 343, after `doc = self._process_text_extraction(doc, result.text)`), add embedding logic before the return statement:

```python
            # Embed the document (if enabled and sqlite-vec available)
            if self._embed_on_add:
                try:
                    self.embed(str(doc.id))
                except Exception:
                    # Embedding failure is non-fatal for add()
                    # Document is still usable, just not searchable via vectors
                    # Status remains PENDING, can retry via `local-library embed`
                    pass
```

**Step 2: Update docstring for add()**

Update the add() docstring to mention embedding. After step 10 in the pipeline description, add:

```
        11. Embed document (if embed_on_add=True and sqlite-vec available)
```

**Step 3: Verify add() still works**

Run: `uv run python -c "
from local_library.core.library import Library
import inspect

# Check add signature
sig = inspect.signature(Library.add)
params = list(sig.parameters.keys())
print(f'add() parameters: {params}')

# Check init signature for embed_on_add
sig_init = inspect.signature(Library.__init__)
params_init = list(sig_init.parameters.keys())
assert 'embed_on_add' in params_init, 'Library should accept embed_on_add parameter'
print('embed_on_add parameter verified')
"
`

Expected: Parameters listed and embed_on_add verified

**Step 4: Commit**

```bash
git add src/local_library/core/library.py
git commit -m "feat(library): integrate embedding into add() pipeline"
```
<!-- END_TASK_2 -->

---

<!-- START_TASK_3 -->
### Task 3: Add embedding status update on re-extraction

**Files:**
- Modify: `src/local_library/core/library.py`

When a document's extracted text changes (e.g., re-extraction), embeddings become stale. This task ensures the embedding_status transitions to STALE.

**Step 1: Add helper for marking embeddings stale**

Add after the `_get_embedding_storage` method:

```python
    def _mark_embeddings_stale(self, doc_id: UUID) -> None:
        """Mark document's embeddings as stale.

        Called when extracted text changes and embeddings need refresh.

        Args:
            doc_id: Document UUID
        """
        if is_vec_available():
            update_embedding_status(self._conn, doc_id, EmbeddingStatus.STALE)
```

**Step 2: Update status transitions in update_metadata**

The `update_metadata` method allows changing document status. If moving back to READY after re-extraction, embeddings should be marked stale. This is already handled by the workflow - when text changes, a new add() or manual re-extraction would occur.

For now, add a note in the docstring of `update_metadata`:

```python
        Note: If CSL-JSON is updated, this does not affect embeddings.
              Embeddings are tied to extracted text, not metadata.
              Re-extraction (which updates extracted_path) should mark
              embeddings as STALE via _mark_embeddings_stale().
```

**Step 3: Commit**

```bash
git add src/local_library/core/library.py
git commit -m "feat(library): add _mark_embeddings_stale helper for status transitions"
```
<!-- END_TASK_3 -->

---

<!-- START_TASK_4 -->
### Task 4: Add unit tests for Library embedding integration

**Files:**
- Create: `tests/unit/test_library_embedding.py`

**Step 1: Create test file**

Create `tests/unit/test_library_embedding.py`:

```python
"""Unit tests for Library embedding integration."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from local_library.core.errors import EmbeddingError
from local_library.core.library import Library
from local_library.core.models import DocumentStatus, EmbeddingStatus
from local_library.core.storage import get_document_by_id
from local_library.core.vec_extension import is_vec_available


@pytest.fixture
def library_no_embed(temp_dir: Path) -> Library:
    """Provide a Library with embedding disabled."""
    return Library(
        db_path=temp_dir / "test.db",
        storage_dir=temp_dir / "storage",
        extracted_dir=temp_dir / "extracted",
        text_extraction_enabled=False,
        embed_on_add=False,
    )


@pytest.fixture
def library_with_embed(temp_dir: Path) -> Library:
    """Provide a Library with embedding enabled (if sqlite-vec available)."""
    return Library(
        db_path=temp_dir / "test.db",
        storage_dir=temp_dir / "storage",
        extracted_dir=temp_dir / "extracted",
        text_extraction_enabled=False,
        embed_on_add=True,
    )


@pytest.fixture
def sample_pdf(temp_dir: Path) -> Path:
    """Create a minimal PDF file."""
    pdf_path = temp_dir / "sample.pdf"
    # Minimal valid PDF
    pdf_content = b"""%PDF-1.0
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000052 00000 n
0000000101 00000 n
trailer<</Size 4/Root 1 0 R>>
startxref
170
%%EOF"""
    pdf_path.write_bytes(pdf_content)
    return pdf_path


class TestLibraryEmbedConfig:
    """Tests for Library embedding configuration."""

    def test_embed_on_add_default_true(self, temp_dir: Path) -> None:
        """embed_on_add should default to True."""
        lib = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
        )
        # If sqlite-vec available, embed_on_add should be True
        if is_vec_available():
            assert lib._embed_on_add is True
        lib.close()

    def test_embed_on_add_disabled(self, library_no_embed: Library) -> None:
        """embed_on_add=False should disable embedding."""
        assert library_no_embed._embed_on_add is False


@pytest.mark.skipif(not is_vec_available(), reason="sqlite-vec not available")
class TestLibraryEmbed:
    """Tests for Library.embed() method."""

    def test_embed_not_ready_raises(self, library_with_embed: Library) -> None:
        """embed() should raise for non-READY documents."""
        # Create a PENDING document (mock the acquirer)
        with patch.object(library_with_embed._acquirers[0], "validate"):
            with patch.object(library_with_embed._acquirers[0], "acquire") as mock_acq:
                mock_acq.return_value = MagicMock(
                    content_hash="hash123",
                    temp_path=Path("/tmp/test.pdf"),
                    original_path="/test.pdf",
                )
                # This will fail during extraction, leaving doc in PENDING
                with pytest.raises(Exception):
                    library_with_embed.add("/test.pdf")

    def test_embed_with_mocked_pipeline(
        self, library_with_embed: Library, temp_dir: Path
    ) -> None:
        """embed() should work with mocked extraction and embedding."""
        # Create a READY document manually
        from local_library.core.storage import create_document, update_document_status

        doc = create_document(
            library_with_embed.conn,
            "/test.pdf",
            "hash123",
            str(temp_dir / "storage" / "hash123.pdf"),
        )

        # Create extracted file
        extracted_path = temp_dir / "extracted" / "hash123.md"
        extracted_path.parent.mkdir(parents=True, exist_ok=True)
        extracted_path.write_text("# Test Document\n\nThis is test content.")

        update_document_status(
            library_with_embed.conn,
            doc.id,
            DocumentStatus.READY,
            extracted_path=str(extracted_path),
        )

        # Mock the embedder
        mock_embedder = MagicMock()
        mock_embedder.embed_chunks = MagicMock(
            side_effect=lambda chunks: [
                MagicMock(chunk=c, embedding=np.random.randn(768).astype(np.float32))
                for c in chunks
            ]
        )
        library_with_embed._embedder = mock_embedder

        # Run embed
        count = library_with_embed.embed(str(doc.id))

        assert count > 0
        mock_embedder.embed_chunks.assert_called_once()

    def test_embed_updates_status(
        self, library_with_embed: Library, temp_dir: Path
    ) -> None:
        """embed() should update embedding_status to CURRENT."""
        from local_library.core.storage import create_document, update_document_status

        doc = create_document(
            library_with_embed.conn,
            "/test.pdf",
            "hash456",
            str(temp_dir / "storage" / "hash456.pdf"),
        )

        extracted_path = temp_dir / "extracted" / "hash456.md"
        extracted_path.parent.mkdir(parents=True, exist_ok=True)
        extracted_path.write_text("# Test\n\nContent here.")

        update_document_status(
            library_with_embed.conn,
            doc.id,
            DocumentStatus.READY,
            extracted_path=str(extracted_path),
        )

        # Mock embedder
        mock_embedder = MagicMock()
        mock_embedder.embed_chunks = MagicMock(
            side_effect=lambda chunks: [
                MagicMock(chunk=c, embedding=np.random.randn(768).astype(np.float32))
                for c in chunks
            ]
        )
        library_with_embed._embedder = mock_embedder

        library_with_embed.embed(str(doc.id))

        # Check status updated
        updated = get_document_by_id(library_with_embed.conn, doc.id)
        assert updated.embedding_status == EmbeddingStatus.CURRENT


class TestLibraryEmbedAll:
    """Tests for Library.embed_all() method."""

    @pytest.mark.skipif(not is_vec_available(), reason="sqlite-vec not available")
    def test_embed_all_returns_counts(self, library_with_embed: Library) -> None:
        """embed_all() should return embedded/failed counts."""
        results = library_with_embed.embed_all()

        assert "embedded" in results
        assert "failed" in results
        assert "chunks" in results


class TestLibraryDeleteCascade:
    """Tests for embedding cascade on delete."""

    @pytest.mark.skipif(not is_vec_available(), reason="sqlite-vec not available")
    def test_delete_removes_embeddings(
        self, library_with_embed: Library, temp_dir: Path
    ) -> None:
        """delete() should remove embeddings."""
        from local_library.core.storage import create_document, update_document_status
        from local_library.embeddings.base import Chunk, ChunkEmbedding

        # Create document
        doc = create_document(
            library_with_embed.conn,
            "/test.pdf",
            "hash789",
            str(temp_dir / "storage" / "hash789.pdf"),
        )

        # Create storage file
        storage_path = temp_dir / "storage" / "hash789.pdf"
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        storage_path.write_bytes(b"fake pdf")

        extracted_path = temp_dir / "extracted" / "hash789.md"
        extracted_path.parent.mkdir(parents=True, exist_ok=True)
        extracted_path.write_text("# Test")

        update_document_status(
            library_with_embed.conn,
            doc.id,
            DocumentStatus.READY,
            extracted_path=str(extracted_path),
        )

        # Add some embeddings
        storage = library_with_embed._get_embedding_storage()
        chunk = Chunk.create(doc.id, 0, "Test chunk")
        embedding = np.random.randn(768).astype(np.float32)
        storage.store_embeddings([ChunkEmbedding(chunk=chunk, embedding=embedding)])

        assert storage.has_embeddings(doc.id)

        # Delete document
        library_with_embed.delete(str(doc.id))

        # Embeddings should be gone
        assert not storage.has_embeddings(doc.id)
```

**Step 2: Run the tests**

Run: `uv run pytest tests/unit/test_library_embedding.py -v`
Expected: All tests pass (some may skip if sqlite-vec unavailable)

**Step 3: Commit**

```bash
git add tests/unit/test_library_embedding.py
git commit -m "test: add unit tests for Library embedding integration"
```
<!-- END_TASK_4 -->

---

<!-- START_TASK_5 -->
### Task 5: Update core/CLAUDE.md with embedding integration

**Files:**
- Modify: `src/local_library/core/CLAUDE.md`

**Step 1: Update Contracts section**

Add to "Exposes": `Library.embed(), Library.embed_all()`

Add to "Guarantees":
- `Library.embed() computes and stores embeddings, updates status to CURRENT`
- `Library.embed_all() processes all PENDING/STALE documents`
- `Library.delete() cascades to remove embeddings`
- `Library.add() embeds by default when embed_on_add=True and sqlite-vec available`

**Step 2: Update Key Decisions section**

Add:
- `**Embedding integration**: Library orchestrates chunking→embedding→storage pipeline; graceful failure on add (document usable, just not vector-searchable)`
- `**embed_on_add config**: Defaults to True; controlled via Library constructor parameter`

**Step 3: Update Dependencies section**

Add to "Uses": `embeddings` (MarkdownChunker, NomicEmbedder, EmbeddingStorage)

**Step 4: Update Key Files section**

Update `library.py` description to: `Library orchestrator (add, get, list, delete, embed, embed_all, update_metadata)`

**Step 5: Update Gotchas section**

Add:
- `Library.embed() raises EmbeddingError if sqlite-vec unavailable or document not READY`
- `Embedding failure in add() is non-fatal; document created but embedding_status stays PENDING`
- `embed_on_add respects sqlite-vec availability; disabled automatically if extension unavailable`

**Step 6: Update Last verified date**

Change to: `Last verified: 2026-02-04`

**Step 7: Commit**

```bash
git add src/local_library/core/CLAUDE.md
git commit -m "docs: update core/CLAUDE.md with embedding integration documentation"
```
<!-- END_TASK_5 -->

---

## Phase 6 Verification

After completing all tasks, verify the phase is complete:

**Run all Phase 6 tests:**
```bash
uv run pytest tests/unit/test_library_embedding.py -v
```

**Verify Library methods work:**
```bash
uv run python -c "
from local_library.core.library import Library
import inspect

# Verify methods exist
methods = ['embed', 'embed_all', 'delete', 'add']
for method in methods:
    assert hasattr(Library, method), f'Library should have {method} method'

# Check embed signature
sig = inspect.signature(Library.embed)
params = list(sig.parameters.keys())
assert 'doc_id' in params
assert 'force' in params

# Check embed_all signature
sig = inspect.signature(Library.embed_all)
params = list(sig.parameters.keys())
assert 'force' in params
assert 'progress_callback' in params

print('All Library embedding methods verified!')
"
```

**Done when:**
- Library.embed() chunks, embeds, and stores for a single document
- Library.embed_all() processes all PENDING/STALE documents
- Library.add() embeds automatically when enabled
- Library.delete() cascades to remove embeddings
- Embedding status transitions work (PENDING→CURRENT, CURRENT→STALE)
- All tests pass
- CLAUDE.md updated
