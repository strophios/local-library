"""Integration tests for the complete embedding pipeline."""

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from local_library.core.library import Library
from local_library.core.models import DocumentStatus, EmbeddingStatus
from local_library.core.storage import get_document_by_id
from local_library.core.vec_extension import is_vec_available

# Skip all tests if sqlite-vec is not available
pytestmark = [
    pytest.mark.embedding,
    pytest.mark.skipif(
        not is_vec_available(),
        reason="sqlite-vec extension not available",
    ),
]


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
