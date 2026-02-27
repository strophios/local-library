"""Integration tests for the retrieval pipeline (end-to-end search)."""

# pattern: Imperative Shell

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import numpy as np
import pytest

from local_library.core import Library
from local_library.core.errors import EmbeddingError
from local_library.core.models import DocumentStatus, EmbeddingStatus
from local_library.core.vec_extension import is_vec_available
from local_library.embeddings.base import Retriever, SearchResult

pytestmark = pytest.mark.skipif(
    not is_vec_available(),
    reason="sqlite-vec extension not available",
)


def _setup_document_with_chunks(
    library: Library,
    title: str = "Test Document",
    citekey: str = "Test2023",
    chunks_text: list[str] | None = None,
) -> UUID:
    """Create a document with embedded chunks for search testing.

    Bypasses the full ingestion pipeline — inserts document record directly,
    creates extracted markdown, and embeds with mocked extraction.
    """
    if chunks_text is None:
        chunks_text = ["Default test chunk content."]

    doc_id = uuid4()
    now = datetime.now(timezone.utc).isoformat()

    # Insert document record
    library.conn.execute(
        """
        INSERT INTO documents (id, original_path, content_hash, storage_path,
                               extracted_path, status, citekey, title,
                               embedding_status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(doc_id),
            "/fake/path.pdf",
            f"hash_{doc_id}",
            "fa/ke/hash.pdf",
            "/fake/extracted.md",
            DocumentStatus.READY.value,
            citekey,
            title,
            EmbeddingStatus.CURRENT.value,
            now,
            now,
        ),
    )
    library.conn.commit()

    # Create and store chunks with embeddings
    from local_library.embeddings.base import Chunk, ChunkEmbedding
    from local_library.embeddings.storage import EmbeddingStorage

    storage = EmbeddingStorage(library.conn)
    embeddings = []
    for i, text in enumerate(chunks_text):
        chunk = Chunk.create(doc_id, i, text)
        embedding = np.random.randn(768).astype(np.float32)
        embeddings.append(ChunkEmbedding(chunk=chunk, embedding=embedding))
    storage.store_embeddings(embeddings)

    return doc_id


class TestGetRetriever:
    """Tests for Library.get_retriever() factory method."""

    def test_returns_hybrid_by_default(self, integration_library: Library) -> None:
        """get_retriever() returns HybridRetriever by default."""
        from local_library.embeddings.retrieval import HybridRetriever

        retriever = integration_library.get_retriever()
        assert isinstance(retriever, HybridRetriever)
        assert isinstance(retriever, Retriever)

    def test_returns_vector_retriever(self, integration_library: Library) -> None:
        """get_retriever(mode='vector') returns VectorRetriever."""
        from local_library.embeddings.retrieval import VectorRetriever

        retriever = integration_library.get_retriever(mode="vector")
        assert isinstance(retriever, VectorRetriever)

    def test_returns_fts_retriever(self, integration_library: Library) -> None:
        """get_retriever(mode='fts') returns FTSRetriever."""
        from local_library.embeddings.retrieval import FTSRetriever

        retriever = integration_library.get_retriever(mode="fts")
        assert isinstance(retriever, FTSRetriever)

    def test_raises_on_invalid_mode(self, integration_library: Library) -> None:
        """get_retriever() raises ValueError for unknown mode."""
        with pytest.raises(ValueError, match="unknown retriever mode"):
            integration_library.get_retriever(mode="invalid")

    def test_raises_without_vec_extension(self, temp_dir: Path) -> None:
        """get_retriever() raises EmbeddingError if sqlite-vec unavailable."""
        with patch("local_library.core.library.is_vec_available", return_value=False):
            lib = Library(
                db_path=temp_dir / "test.db",
                storage_dir=temp_dir / "storage",
                extracted_dir=temp_dir / "extracted",
                text_extraction_enabled=False,
            )
            with pytest.raises(EmbeddingError):
                lib.get_retriever()


class TestSearchEndToEnd:
    """End-to-end search tests: embed chunks -> search -> results."""

    def test_vector_search_returns_results(self, integration_library: Library) -> None:
        """Vector search returns results with metadata."""
        _setup_document_with_chunks(
            integration_library,
            title="ML Paper",
            citekey="Author2023",
            chunks_text=[
                "Machine learning algorithms for image classification",
                "Database query optimization techniques",
            ],
        )

        # Mock the embedder to avoid loading the real model
        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.random.randn(768).astype(np.float32)

        retriever = integration_library.get_retriever(mode="vector")
        # Replace the embedder with our mock
        retriever._embedder = mock_embedder

        results = retriever.retrieve("machine learning", k=5)

        assert len(results) >= 1
        assert all(isinstance(r, SearchResult) for r in results)
        assert results[0].doc_title == "ML Paper"
        assert results[0].doc_citekey == "Author2023"

    def test_fts_search_returns_results(self, integration_library: Library) -> None:
        """FTS search returns results matching keywords."""
        _setup_document_with_chunks(
            integration_library,
            title="Python Guide",
            citekey="Guide2023",
            chunks_text=[
                "Python programming language features and syntax",
                "Java virtual machine architecture",
            ],
        )

        retriever = integration_library.get_retriever(mode="fts")
        results = retriever.retrieve("Python programming")

        assert len(results) >= 1
        assert results[0].doc_title == "Python Guide"
        assert "fts" in results[0].search_methods

    def test_hybrid_search_returns_results(self, integration_library: Library) -> None:
        """Hybrid search returns fused results from both methods."""
        _setup_document_with_chunks(
            integration_library,
            title="Hybrid Doc",
            citekey="Hybrid2023",
            chunks_text=["Neural networks for natural language processing"],
        )

        mock_embedder = MagicMock()
        mock_embedder.embed_query.return_value = np.random.randn(768).astype(np.float32)

        retriever = integration_library.get_retriever(mode="hybrid")
        retriever._vector._embedder = mock_embedder

        results = retriever.retrieve("neural networks")

        assert len(results) >= 1
        assert isinstance(results[0], SearchResult)

    def test_search_across_multiple_documents(self, integration_library: Library) -> None:
        """Search returns results from multiple documents."""
        _setup_document_with_chunks(
            integration_library,
            title="Doc A",
            citekey="DocA2023",
            chunks_text=["Python web frameworks comparison"],
        )
        _setup_document_with_chunks(
            integration_library,
            title="Doc B",
            citekey="DocB2023",
            chunks_text=["Python data science libraries"],
        )

        retriever = integration_library.get_retriever(mode="fts")
        results = retriever.retrieve("Python")

        assert len(results) >= 2
        titles = {r.doc_title for r in results}
        assert "Doc A" in titles
        assert "Doc B" in titles

    def test_search_with_doc_ids_filter(self, integration_library: Library) -> None:
        """Search filters results to specified document IDs."""
        doc_id_1 = _setup_document_with_chunks(
            integration_library,
            title="Filtered In",
            citekey="In2023",
            chunks_text=["Searchable keyword content"],
        )
        _setup_document_with_chunks(
            integration_library,
            title="Filtered Out",
            citekey="Out2023",
            chunks_text=["Searchable keyword content"],
        )

        retriever = integration_library.get_retriever(mode="fts")
        results = retriever.retrieve("keyword", doc_ids=[doc_id_1])

        assert len(results) >= 1
        for r in results:
            assert r.chunk.doc_id == doc_id_1
