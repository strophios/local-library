## Phase 8: Integration Testing and Polish

**Goal:** End-to-end testing, edge cases, documentation updates.

This phase ensures the embedding pipeline works end-to-end, handles edge cases gracefully, and updates project documentation.

---

<!-- START_TASK_1 -->
### Task 1: Create integration tests for embedding pipeline

**Files:**
- Create: `tests/integration/test_embedding_pipeline.py`

**Step 1: Create integration test file**

Create `tests/integration/test_embedding_pipeline.py`:

```python
"""Integration tests for the complete embedding pipeline."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from local_library.core.library import Library
from local_library.core.models import DocumentStatus, EmbeddingStatus
from local_library.core.storage import get_document_by_id
from local_library.core.vec_extension import is_vec_available


# Skip all tests if sqlite-vec is not available
pytestmark = pytest.mark.skipif(
    not is_vec_available(),
    reason="sqlite-vec extension not available",
)


@pytest.fixture
def integration_library(temp_dir: Path) -> Library:
    """Provide a Library instance for integration testing."""
    return Library(
        db_path=temp_dir / "test.db",
        storage_dir=temp_dir / "storage",
        extracted_dir=temp_dir / "extracted",
        text_extraction_enabled=False,
        embed_on_add=False,  # We'll test embedding separately
    )


@pytest.fixture
def sample_markdown_content() -> str:
    """Sample markdown content for testing."""
    return """# Introduction

This is an introduction to machine learning, a field of artificial intelligence
that enables computers to learn from data without being explicitly programmed.

## Supervised Learning

In supervised learning, the model learns from labeled training data. Common
algorithms include linear regression, decision trees, and neural networks.

### Linear Regression

Linear regression predicts a continuous output variable based on input features.
It assumes a linear relationship between inputs and outputs.

### Decision Trees

Decision trees split data based on feature values, creating a tree-like model
of decisions and their consequences.

## Unsupervised Learning

Unsupervised learning finds patterns in unlabeled data. Clustering and
dimensionality reduction are common techniques.

### K-Means Clustering

K-means partitions data into K clusters, minimizing within-cluster variance.
Each point belongs to the cluster with the nearest centroid.

## Conclusion

Machine learning has revolutionized many fields and continues to advance
with new techniques and applications.
"""


class TestEmbeddingPipelineIntegration:
    """Integration tests for the full embedding pipeline."""

    def test_embed_creates_chunks_and_vectors(
        self, integration_library: Library, temp_dir: Path, sample_markdown_content: str
    ) -> None:
        """Full pipeline should create chunks and store vectors."""
        lib = integration_library

        # Create a document manually
        from local_library.core.storage import create_document, update_document_status

        doc = create_document(
            lib.conn, "/test.pdf", "hash_integration", str(temp_dir / "storage/test.pdf")
        )

        # Create extracted markdown
        extracted_path = temp_dir / "extracted/test.md"
        extracted_path.parent.mkdir(parents=True, exist_ok=True)
        extracted_path.write_text(sample_markdown_content)

        update_document_status(
            lib.conn, doc.id, DocumentStatus.READY, extracted_path=str(extracted_path)
        )

        # Mock the embedder to avoid slow model loading
        mock_embedder = MagicMock()
        mock_embedder.embed_chunks = MagicMock(
            side_effect=lambda chunks: [
                MagicMock(
                    chunk=c,
                    embedding=np.random.randn(768).astype(np.float32),
                    chunk_id=c.chunk_id,
                    doc_id=c.doc_id,
                )
                for c in chunks
            ]
        )
        lib._embedder = mock_embedder

        # Run embedding
        chunk_count = lib.embed(str(doc.id))

        # Verify
        assert chunk_count > 0
        mock_embedder.embed_chunks.assert_called_once()

        # Check embedding status updated
        updated_doc = get_document_by_id(lib.conn, doc.id)
        assert updated_doc.embedding_status == EmbeddingStatus.CURRENT

        # Check chunks were stored
        storage = lib._get_embedding_storage()
        assert storage.get_chunk_count(doc.id) == chunk_count

    def test_embed_all_processes_pending_documents(
        self, integration_library: Library, temp_dir: Path
    ) -> None:
        """embed_all should process all pending documents."""
        lib = integration_library
        from local_library.core.storage import create_document, update_document_status

        # Create multiple documents
        doc_ids = []
        for i in range(3):
            doc = create_document(
                lib.conn,
                f"/test{i}.pdf",
                f"hash_batch_{i}",
                str(temp_dir / f"storage/test{i}.pdf"),
            )
            extracted_path = temp_dir / f"extracted/test{i}.md"
            extracted_path.parent.mkdir(parents=True, exist_ok=True)
            extracted_path.write_text(f"# Document {i}\n\nContent for document {i}.")
            update_document_status(
                lib.conn, doc.id, DocumentStatus.READY, extracted_path=str(extracted_path)
            )
            doc_ids.append(doc.id)

        # Mock embedder
        mock_embedder = MagicMock()
        mock_embedder.embed_chunks = MagicMock(
            side_effect=lambda chunks: [
                MagicMock(
                    chunk=c,
                    embedding=np.random.randn(768).astype(np.float32),
                    chunk_id=c.chunk_id,
                    doc_id=c.doc_id,
                )
                for c in chunks
            ]
        )
        lib._embedder = mock_embedder

        # Run embed_all
        results = lib.embed_all()

        assert results["embedded"] == 3
        assert results["failed"] == 0
        assert results["chunks"] > 0

        # All documents should be CURRENT
        for doc_id in doc_ids:
            doc = get_document_by_id(lib.conn, doc_id)
            assert doc.embedding_status == EmbeddingStatus.CURRENT

    def test_delete_cascades_embeddings(
        self, integration_library: Library, temp_dir: Path
    ) -> None:
        """Deleting a document should remove its embeddings."""
        lib = integration_library
        from local_library.core.storage import create_document, update_document_status
        from local_library.embeddings.base import Chunk, ChunkEmbedding

        # Create document
        storage_file = temp_dir / "storage/cascade.pdf"
        storage_file.parent.mkdir(parents=True, exist_ok=True)
        storage_file.write_bytes(b"fake pdf")

        doc = create_document(
            lib.conn, "/cascade.pdf", "hash_cascade", str(storage_file)
        )

        extracted_path = temp_dir / "extracted/cascade.md"
        extracted_path.parent.mkdir(parents=True, exist_ok=True)
        extracted_path.write_text("# Test")

        update_document_status(
            lib.conn, doc.id, DocumentStatus.READY, extracted_path=str(extracted_path)
        )

        # Add embeddings directly
        storage = lib._get_embedding_storage()
        chunk = Chunk.create(doc.id, 0, "Test content")
        embedding = np.random.randn(768).astype(np.float32)
        storage.store_embeddings([ChunkEmbedding(chunk=chunk, embedding=embedding)])

        assert storage.has_embeddings(doc.id)

        # Delete document
        lib.delete(str(doc.id))

        # Embeddings should be gone
        assert not storage.has_embeddings(doc.id)

    def test_reembed_with_force_replaces_embeddings(
        self, integration_library: Library, temp_dir: Path
    ) -> None:
        """Re-embedding with force should replace existing embeddings."""
        lib = integration_library
        from local_library.core.storage import create_document, update_document_status
        from local_library.embeddings.storage import update_embedding_status

        # Create document
        doc = create_document(
            lib.conn, "/reembed.pdf", "hash_reembed", str(temp_dir / "storage/reembed.pdf")
        )

        extracted_path = temp_dir / "extracted/reembed.md"
        extracted_path.parent.mkdir(parents=True, exist_ok=True)
        extracted_path.write_text("# Original Content\n\nThis is original.")

        update_document_status(
            lib.conn, doc.id, DocumentStatus.READY, extracted_path=str(extracted_path)
        )

        # Mock embedder
        mock_embedder = MagicMock()
        call_count = [0]

        def mock_embed(chunks):
            call_count[0] += 1
            return [
                MagicMock(
                    chunk=c,
                    embedding=np.random.randn(768).astype(np.float32),
                    chunk_id=c.chunk_id,
                    doc_id=c.doc_id,
                )
                for c in chunks
            ]

        mock_embedder.embed_chunks = MagicMock(side_effect=mock_embed)
        lib._embedder = mock_embedder

        # First embed
        lib.embed(str(doc.id))
        first_call_count = call_count[0]

        # Second embed without force should do nothing
        lib.embed(str(doc.id), force=False)
        assert call_count[0] == first_call_count  # No new embedding

        # Re-embed with force
        lib.embed(str(doc.id), force=True)
        assert call_count[0] == first_call_count + 1  # New embedding call


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_embed_empty_document(
        self, integration_library: Library, temp_dir: Path
    ) -> None:
        """Embedding an empty document should succeed with 0 chunks."""
        lib = integration_library
        from local_library.core.storage import create_document, update_document_status

        doc = create_document(
            lib.conn, "/empty.pdf", "hash_empty", str(temp_dir / "storage/empty.pdf")
        )

        # Empty extracted file
        extracted_path = temp_dir / "extracted/empty.md"
        extracted_path.parent.mkdir(parents=True, exist_ok=True)
        extracted_path.write_text("")

        update_document_status(
            lib.conn, doc.id, DocumentStatus.READY, extracted_path=str(extracted_path)
        )

        # Should not raise, should return 0
        chunk_count = lib.embed(str(doc.id))
        assert chunk_count == 0

        # Status should still be updated
        doc = get_document_by_id(lib.conn, doc.id)
        assert doc.embedding_status == EmbeddingStatus.CURRENT

    def test_embed_whitespace_only_document(
        self, integration_library: Library, temp_dir: Path
    ) -> None:
        """Embedding whitespace-only document should succeed with 0 chunks."""
        lib = integration_library
        from local_library.core.storage import create_document, update_document_status

        doc = create_document(
            lib.conn, "/whitespace.pdf", "hash_ws", str(temp_dir / "storage/ws.pdf")
        )

        extracted_path = temp_dir / "extracted/ws.md"
        extracted_path.parent.mkdir(parents=True, exist_ok=True)
        extracted_path.write_text("   \n\n   \t  \n  ")

        update_document_status(
            lib.conn, doc.id, DocumentStatus.READY, extracted_path=str(extracted_path)
        )

        chunk_count = lib.embed(str(doc.id))
        assert chunk_count == 0

    def test_embed_pending_document_fails(
        self, integration_library: Library, temp_dir: Path
    ) -> None:
        """Embedding a PENDING (not ready) document should fail."""
        lib = integration_library
        from local_library.core.errors import EmbeddingError
        from local_library.core.storage import create_document

        doc = create_document(
            lib.conn, "/pending.pdf", "hash_pending", str(temp_dir / "storage/pending.pdf")
        )
        # Status is PENDING, not READY

        with pytest.raises(EmbeddingError) as exc_info:
            lib.embed(str(doc.id))

        assert exc_info.value.code.value == "EMBEDDING_DOCUMENT_NOT_READY"

    def test_embed_missing_extracted_file_fails(
        self, integration_library: Library, temp_dir: Path
    ) -> None:
        """Embedding with missing extracted file should fail."""
        lib = integration_library
        from local_library.core.errors import EmbeddingError
        from local_library.core.storage import create_document, update_document_status

        doc = create_document(
            lib.conn, "/missing.pdf", "hash_missing", str(temp_dir / "storage/missing.pdf")
        )

        # Set to READY but don't create extracted file
        update_document_status(
            lib.conn, doc.id, DocumentStatus.READY, extracted_path="/nonexistent/path.md"
        )

        with pytest.raises(EmbeddingError) as exc_info:
            lib.embed(str(doc.id))

        assert exc_info.value.code.value == "EMBEDDING_DOCUMENT_NOT_READY"
```

**Step 2: Run the integration tests**

Run: `uv run pytest tests/integration/test_embedding_pipeline.py -v`
Expected: All tests pass (or skip if sqlite-vec unavailable)

**Step 3: Commit**

```bash
git add tests/integration/test_embedding_pipeline.py
git commit -m "test: add integration tests for embedding pipeline"
```
<!-- END_TASK_1 -->

---

<!-- START_TASK_2 -->
### Task 2: Add pytest marker for embedding tests

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add embedding marker**

Find the markers list in pyproject.toml and add:

```toml
    "embedding: Embedding pipeline tests requiring sqlite-vec",
```

**Step 2: Commit**

```bash
git add pyproject.toml
git commit -m "config: add embedding pytest marker"
```
<!-- END_TASK_2 -->

---

<!-- START_TASK_3 -->
### Task 3: Update project CLAUDE.md with M5 completion

**Files:**
- Modify: `CLAUDE.md` (project root)

**Step 1: Update Current Status section**

Update the "Current Status" section to include M5:

```markdown
### Current Status: M1-M5 Complete (Record Storage + Extraction + Metadata + Zotero Reader + Text Extraction + Embedding Pipeline)

Milestones M1 (record storage), M2 (PDF extraction), M3a (metadata validation), M3b (text-based metadata extraction), M4 (Zotero read-only access), and M5 (embedding pipeline) are implemented. The system can:
- Ingest local PDF files via CLI (`local-library add <path>`)
- Accept explicit CSL-JSON metadata (`--metadata <file>`)
- Extract text to markdown via Marker
- Validate metadata against CSL-JSON schema and generate citekeys
- **Extract metadata from PDF text** when no explicit metadata provided
- Set documents to NEEDS_REVIEW status when extraction confidence is low
- Optionally use LLM fallback (via LiteLLM) for low-confidence extractions
- Store documents in content-addressable storage with SQLite metadata
- Query, list, and delete documents via CLI
- Read items, attachments, and metadata from Zotero library
- **Compute and store embeddings for semantic search** (`local-library embed`)
- **Chunk documents using section-aware markdown splitting**
- **Store 768-dimensional vectors in sqlite-vec for similarity search**
```

**Step 2: Update Implemented section**

Add to "Implemented" list:
- **Embedding pipeline**: Section-aware chunking via LangChain, 768-dim vectors via nomic-embed-text-v1.5, sqlite-vec storage
- **CLI embed command**: `local-library embed` with --pending, --all, --force options
- **Automatic embedding on add**: Documents embedded by default (--skip-embed to disable)
- **Embedding status tracking**: PENDING, CURRENT, STALE lifecycle
- **Cascade deletion**: Embeddings deleted when parent document deleted

**Step 3: Update Next milestones**

Change to: `**Next milestones:** M6 (search interface). See `build_plan.md` for full details.`

**Step 4: Update Commands section**

Add:
- `uv run local-library embed <id>` - Embed a single document
- `uv run local-library embed --pending` - Embed all documents needing embedding
- `uv run local-library embed --all --force` - Re-embed all documents
- `uv run local-library add <path> --skip-embed` - Add without automatic embedding

**Step 5: Update Package Structure**

Add to the structure:
```
├── embeddings/          # Domain: chunking, embedding, vector storage
│   ├── base.py          # Protocols: Chunker, Embedder; Models: Chunk, ChunkEmbedding
│   ├── chunking.py      # MarkdownChunker (LangChain splitters)
│   ├── nomic.py         # NomicEmbedder (sentence-transformers)
│   └── storage.py       # EmbeddingStorage (sqlite-vec operations)
```

**Step 6: Update Key Libraries section**

Add:
- **Chunking**: langchain-text-splitters (MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter)
- **Embeddings**: sentence-transformers with nomic-embed-text-v1.5 (768 dims, 8192 context)
- **Vector storage**: sqlite-vec v0.1.6+ (vec0 virtual tables for k-NN search)

**Step 7: Update Last verified date**

Change to: `Last verified: 2026-02-04`

**Step 8: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with M5 embedding pipeline completion"
```
<!-- END_TASK_3 -->

---

<!-- START_TASK_4 -->
### Task 4: Update embeddings/CLAUDE.md with final documentation

**Files:**
- Modify: `src/local_library/embeddings/CLAUDE.md`

**Step 1: Update Exposes section**

Ensure all components are listed:
- `Chunker protocol, Embedder protocol`
- `Chunk dataclass, ChunkEmbedding dataclass`
- `MarkdownChunker, NomicEmbedder, EmbeddingStorage`
- `update_embedding_status, get_documents_needing_embedding, estimate_token_count`

**Step 2: Update Key Files section**

Ensure all files documented:
- `base.py` - Chunk, ChunkEmbedding dataclasses; Chunker, Embedder protocols
- `chunking.py` - MarkdownChunker (section-aware markdown splitting)
- `nomic.py` - NomicEmbedder (nomic-embed-text-v1.5 via sentence-transformers)
- `storage.py` - EmbeddingStorage (sqlite-vec CRUD), status functions

**Step 3: Update Gotchas section**

Ensure important gotchas documented:
- nomic-embed-text requires `trust_remote_code=True`
- Task prefixes must be prepended manually
- sqlite-vec requires `serialize_float32()` for insertion
- ChunkEmbedding validates 768 dimensions on creation
- Model download (~262 MB) happens on first embed
- EmbeddingStorage requires sqlite-vec loaded; use `require_vec_extension()` first
- `search_similar()` returns (Chunk, distance) tuples sorted by distance ascending

**Step 4: Update Last verified date**

Change to: `Last verified: 2026-02-04`

**Step 5: Commit**

```bash
git add src/local_library/embeddings/CLAUDE.md
git commit -m "docs: finalize embeddings/CLAUDE.md documentation"
```
<!-- END_TASK_4 -->

---

<!-- START_TASK_5 -->
### Task 5: Run full test suite and verify

**Files:** None (verification only)

**Step 1: Run all unit tests**

Run: `uv run pytest tests/unit/ -v --tb=short`
Expected: All tests pass

**Step 2: Run all integration tests**

Run: `uv run pytest tests/integration/ -v --tb=short`
Expected: All tests pass (some may skip if sqlite-vec unavailable)

**Step 3: Run linting**

Run: `uv run ruff check src/local_library/`
Expected: No errors

**Step 4: Run formatting check**

Run: `uv run ruff format --check src/local_library/`
Expected: No formatting issues (or run `uv run ruff format src/local_library/` to fix)

**Step 5: Verify CLI works**

Run:
```bash
uv run local-library --help
uv run local-library embed --help
```
Expected: Help output shows all commands including embed

**Step 6: Create final commit if tests pass**

If all tests pass and linting is clean:

```bash
git add -A
git commit -m "chore: M5 embedding pipeline complete - all tests passing"
```
<!-- END_TASK_5 -->

---

## Phase 8 Verification

After completing all tasks, verify the phase is complete:

**Run complete test suite:**
```bash
uv run pytest tests/ -v --tb=short -m "not slow and not extraction"
```

**Verify documentation is updated:**
```bash
# Check CLAUDE.md mentions embedding
grep -l "embedding" CLAUDE.md src/local_library/*/CLAUDE.md
```

**Verify all embedding tests pass:**
```bash
uv run pytest -k "embedding" -v
```

**Done when:**
- All unit tests pass
- All integration tests pass (or skip gracefully)
- Linting passes
- Project CLAUDE.md updated with M5 status
- Domain CLAUDE.md files updated
- CLI works with all embed options

---

## M5 Completion Checklist

When all phases are complete, verify the Definition of Done:

- [ ] **Documents have searchable embeddings** — Chunks and vectors stored in sqlite-vec after add/import
- [ ] **Chunk boundaries respect markdown structure** — Section-aware chunking using headers and paragraphs
- [ ] **Embeddings cascade on delete** — When a document is deleted, its chunks and embeddings are removed
- [ ] **Embedding status tracking** — Document tracks embedding state (PENDING/CURRENT/STALE)
- [ ] **CLI `embed` command** — Manual embedding/re-embedding for specific documents or all pending
- [ ] **Two-phase batch operations** — Zotero import supports --skip-embed for extract-all → embed-all workflow
- [ ] **Extensible architecture** — Protocols support future chunking/embedding implementations
- [ ] **Tests pass** — Coverage for chunking logic, embedding computation, sqlite-vec storage, status transitions, cascade deletion
