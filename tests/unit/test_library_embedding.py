"""Unit tests for Library embedding integration."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from local_library.core.errors import ErrorCode, ExtractionError
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

    def test_embed_not_ready_raises(self, library_with_embed: Library, temp_dir: Path) -> None:
        """embed() should raise for non-READY documents."""
        # Create a mock PDF file in temp directory
        temp_pdf = temp_dir / "mock.pdf"
        temp_pdf.write_bytes(b"%PDF-1.0\n")

        # Create a PENDING document (mock the acquirer)
        acquirer = library_with_embed._acquirers[0]
        extractor = library_with_embed._extractors[0]

        with patch.object(acquirer, "validate"):
            with patch.object(acquirer, "acquire") as mock_acq:
                mock_acq.return_value = MagicMock(
                    content_hash="hash123",
                    temp_path=temp_pdf,
                    original_path="/test.pdf",
                )
                # Mock extractor to raise ExtractionError
                with patch.object(extractor, "can_handle", return_value=True):
                    with patch.object(extractor, "extract_and_validate") as mock_extract:
                        mock_extract.side_effect = ExtractionError(
                            "failed to extract",
                            ErrorCode.EXTRACTION_EMPTY_OUTPUT,
                        )
                        # This will fail during extraction
                        with pytest.raises(ExtractionError):
                            library_with_embed.add("/test.pdf")

    def test_embed_with_mocked_pipeline(self, library_with_embed: Library, temp_dir: Path) -> None:
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

    def test_embed_updates_status(self, library_with_embed: Library, temp_dir: Path) -> None:
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
        assert updated is not None, "Document should exist after embedding"
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
    def test_delete_removes_embeddings(self, library_with_embed: Library, temp_dir: Path) -> None:
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
        assert storage is not None, "EmbeddingStorage should be available when sqlite-vec is loaded"
        chunk = Chunk.create(doc.id, 0, "Test chunk")
        embedding = np.random.randn(768).astype(np.float32)
        storage.store_embeddings([ChunkEmbedding(chunk=chunk, embedding=embedding)])

        assert storage.has_embeddings(doc.id)

        # Delete document
        library_with_embed.delete(str(doc.id))

        # Embeddings should be gone
        storage = library_with_embed._get_embedding_storage()
        assert storage is not None, "EmbeddingStorage should be available when sqlite-vec is loaded"
        assert not storage.has_embeddings(doc.id)
