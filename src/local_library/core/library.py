"""Library orchestration - coordinates acquisition, extraction, and storage."""

# pattern: Imperative Shell

from __future__ import annotations

import logging
import shutil
import sqlite3
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from local_library.core.models import RAGResponse
    from local_library.embeddings.base import Chunk, Retriever
    from local_library.embeddings.reranking import CrossEncoderReranker
    from local_library.ingestion.pdf import ProgressCallback
    from local_library.rag.interface import RAGInterface, RAGStream

from local_library.config import (
    ensure_directories,
    get_database_path,
    get_extracted_dir,
    get_storage_dir,
)
from local_library.core.errors import (
    AcquisitionError,
    ErrorCode,
    ExtractionError,
    LookupError,
    MetadataError,
    QualityError,
)
from local_library.core.models import (
    AddResult,
    Document,
    DocumentStatus,
    EmbeddingStatus,
    MetadataSource,
)
from local_library.core.storage import (
    create_document,
    delete_document,
    get_all_citekeys,
    get_connection,
    get_document_by_citekey,
    get_document_by_hash,
    get_document_by_id,
    get_document_by_path,
    get_documents_by_partial_id,
    get_unique_citekey,
    init_schema,
    list_documents,
    update_document_metadata,
    update_document_status,
)
from local_library.core.vec_extension import is_vec_available, load_vec_extension
from local_library.ingestion.artifact_cleanup import clean_artifacts
from local_library.ingestion.base import ContentAcquirer, ContentExtractor, compute_storage_path
from local_library.ingestion.file import FileAcquirer
from local_library.ingestion.markdown_cleanup import cleanup_markdown
from local_library.ingestion.metadata import MetadataHandler, extract_year_from_csl
from local_library.ingestion.pdf import PdfExtractor
from local_library.ingestion.text_extraction import (
    TextMetadataExtractor,
    build_csl_json,
)

logger = logging.getLogger(__name__)


def _cleanup_empty_parents(path: Path, stop_at: Path) -> None:
    """Remove empty parent directories up to (but not including) stop_at.

    Walks up the directory tree from path's parent, removing each empty
    directory until reaching stop_at or encountering a non-empty directory.

    Also removes .DS_Store files (macOS Finder metadata) since they don't
    represent meaningful content and would otherwise prevent cleanup.

    Args:
        path: The file that was deleted (starts cleanup from its parent)
        stop_at: Root directory to stop at (will not be removed)
    """
    for parent in path.parents:
        if parent == stop_at or not parent.is_relative_to(stop_at):
            break
        # Remove .DS_Store if it's the only thing preventing cleanup
        ds_store = parent / ".DS_Store"
        if ds_store.exists():
            try:
                ds_store.unlink()
            except OSError:
                pass  # Best effort
        try:
            parent.rmdir()  # Only succeeds if directory is empty
        except OSError:
            break  # Directory not empty or other issue, stop climbing


class Library:
    """Orchestrates document acquisition, extraction, and storage.

    The Library is the main entry point for all document operations.
    It coordinates the acquirer, extractor, and storage layers.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        storage_dir: Path | None = None,
        extracted_dir: Path | None = None,
        acquirers: list[ContentAcquirer] | None = None,
        extractors: list[ContentExtractor] | None = None,
        text_extraction_enabled: bool = True,
        text_extraction_llm_enabled: bool = False,
        text_extraction_llm_model: str = "gemini/gemini-2.0-flash",
        text_extraction_confidence_threshold: float = 0.7,
        pdf_llm_enabled: bool = False,
        embed_on_add: bool = True,
        embedding_batch_size: int = 32,
        rag_model: str = "gemini/gemini-2.0-flash",
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        """Initialize the library.

        Args:
            db_path: Path to SQLite database (default: platformdirs user data)
            storage_dir: Directory for content-addressable storage (default: platformdirs)
            extracted_dir: Directory for extracted markdown (default: platformdirs)
            acquirers: List of content acquirers (default: [FileAcquirer()])
            extractors: List of content extractors (default: [PdfExtractor(lazy_load=True)])
            text_extraction_enabled: Whether to extract metadata from text (default: True)
            text_extraction_llm_enabled: Whether to use LLM fallback (default: False)
            text_extraction_llm_model: LLM model for fallback (default: "gemini-2.0-flash")
            text_extraction_confidence_threshold: Confidence threshold (default: 0.7)
            pdf_llm_enabled: Whether to use Marker's LLM-enhanced PDF extraction (default: False).
                            Enables better table, math, and image handling. Requires GEMINI_API_KEY.
            embed_on_add: Whether to embed documents during add() (default: True).
            embedding_batch_size: Batch size for embedding computation (default: 32).
            rag_model: LLM model identifier for RAG queries (default: "gemini/gemini-2.0-flash").
            progress_callback: Optional callback for extraction progress events.
        """
        # Use defaults from config if not specified
        self._db_path = db_path or get_database_path()
        self._storage_dir = storage_dir or get_storage_dir()
        self._extracted_dir = extracted_dir or get_extracted_dir()

        # Initialize handler lists with defaults
        self._acquirers: list[ContentAcquirer] = (
            acquirers if acquirers is not None else [FileAcquirer()]
        )
        self._extractors: list[ContentExtractor] = (
            extractors
            if extractors is not None
            else [
                PdfExtractor(
                    lazy_load=True,
                    llm_enabled=pdf_llm_enabled,
                    progress_callback=progress_callback,
                )
            ]
        )

        # Initialize metadata handler
        self._metadata_handler = MetadataHandler()

        # Initialize text metadata extractor
        # Create LLMClient at Library level for explicit dependency ownership
        text_llm_client = None
        if text_extraction_llm_enabled:
            from local_library.llm.litellm_client import LiteLLMClient

            text_llm_client = LiteLLMClient(model=text_extraction_llm_model)

        self._text_extractor = (
            TextMetadataExtractor(
                confidence_threshold=text_extraction_confidence_threshold,
                llm_client=text_llm_client,
            )
            if text_extraction_enabled
            else None
        )

        # Ensure directories exist
        ensure_directories()

        # Initialize database
        self._conn = get_connection(self._db_path)
        init_schema(self._conn)

        # Initialize embedding components (if sqlite-vec available)
        # Chunker and embedder are created lazily on first use (in embed/embed_all)
        # to avoid importing heavy ML libraries (torch, transformers, langchain)
        # at Library construction time.
        self._embed_on_add = embed_on_add and is_vec_available()
        self._embedding_batch_size = embedding_batch_size
        self._chunker = None
        self._embedder = None
        self._embedding_storage = None  # Lazy init when needed

        # RAG query components (lazy init on first query() call)
        self._rag_model = rag_model
        self._llm_client = None  # Lazy: created on first query
        self._rag_interface = None  # Lazy: created on first query

        # Reranking (lazy init on first get_retriever(rerank=True) call)
        self._reranker = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Get the database connection."""
        return self._conn

    def close(self) -> None:
        """Close the database connection and release extractor resources."""
        # Stop extraction worker subprocesses
        for extractor in self._extractors:
            if hasattr(extractor, "close"):
                try:
                    extractor.close()
                except Exception:
                    pass
        self._conn.close()

    def __enter__(self) -> Library:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    def _get_embedding_storage(self):
        """Get or create EmbeddingStorage instance.

        Returns:
            EmbeddingStorage if sqlite-vec available, None otherwise
        """
        if not is_vec_available():
            return None

        if self._embedding_storage is None:
            from local_library.embeddings.storage import EmbeddingStorage

            load_vec_extension(self._conn)
            self._embedding_storage = EmbeddingStorage(self._conn)

        return self._embedding_storage

    def get_retriever(self, mode: str = "hybrid", rerank: bool = True) -> Retriever:
        """Get a retriever instance for searching documents.

        Factory method that wires up retriever dependencies (storage, embedder)
        and returns the requested implementation. When rerank=True, wraps the
        base retriever with cross-encoder reranking.

        Args:
            mode: Retriever type - "hybrid" (default), "vector", or "fts"
            rerank: Whether to wrap with cross-encoder reranking (default: True)

        Returns:
            A Retriever protocol-compliant instance

        Raises:
            EmbeddingError: If sqlite-vec extension is not available
            ValueError: If mode is not recognized
        """
        from local_library.core.errors import EmbeddingError, ErrorCode
        from local_library.embeddings.nomic import NomicEmbedder
        from local_library.embeddings.retrieval import (
            FTSRetriever,
            HybridRetriever,
            VectorRetriever,
        )

        storage = self._get_embedding_storage()
        if storage is None:
            raise EmbeddingError(
                "sqlite-vec extension not available for retrieval",
                ErrorCode.EMBEDDING_EXTENSION_UNAVAILABLE,
            )

        # Build base retriever
        if mode == "fts":
            base = FTSRetriever(storage)
        elif mode == "vector":
            if self._embedder is None:
                self._embedder = NomicEmbedder()
            base = VectorRetriever(storage, self._embedder)
        elif mode == "hybrid":
            if self._embedder is None:
                self._embedder = NomicEmbedder()
            vector_ret = VectorRetriever(storage, self._embedder)
            fts_ret = FTSRetriever(storage)
            base = HybridRetriever(vector_ret, fts_ret)
        else:
            raise ValueError(
                f"unknown retriever mode: {mode!r} (expected 'hybrid', 'vector', or 'fts')"
            )

        # Optionally wrap with cross-encoder reranking
        if rerank:
            from local_library.embeddings.reranking import RerankedRetriever

            return RerankedRetriever(inner=base, reranker=self._get_reranker())

        return base

    def _mark_embeddings_stale(self, doc_id: UUID) -> None:
        """Mark document's embeddings as stale.

        Called when extracted text changes and embeddings need refresh.

        Args:
            doc_id: Document UUID
        """
        if is_vec_available():
            from local_library.embeddings.storage import update_embedding_status

            update_embedding_status(self._conn, doc_id, EmbeddingStatus.STALE)

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
        from local_library.embeddings.chunking import MarkdownChunker
        from local_library.embeddings.nomic import NomicEmbedder
        from local_library.embeddings.storage import update_embedding_status

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
        progress_callback: Callable | None = None,
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
        from local_library.embeddings.storage import (
            get_documents_needing_embedding,
            update_embedding_status,
        )

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

            except Exception:
                results["failed"] += 1
                # Update status to PENDING on failure (will retry later)
                update_embedding_status(self._conn, doc_id, EmbeddingStatus.PENDING)

        if progress_callback:
            progress_callback(total, total, None)

        return results

    def _find_acquirer(self, source: str) -> ContentAcquirer:
        """Find an acquirer that can handle the given source.

        Iterates through registered acquirers and returns the first
        one whose can_handle() returns True.

        Args:
            source: Source identifier (path, URL, etc.)

        Returns:
            The acquirer that can handle this source

        Raises:
            AcquisitionError: If no acquirer can handle the source
        """
        for acquirer in self._acquirers:
            if acquirer.can_handle(source):
                return acquirer

        raise AcquisitionError(
            f"no acquirer can handle source: {source}",
            ErrorCode.ACQUISITION_UNSUPPORTED_SOURCE,
            details={"source": source},
        )

    def _find_extractor(self, file_path: Path) -> ContentExtractor:
        """Find an extractor that can handle the given file.

        Iterates through registered extractors and returns the first
        one whose can_handle() returns True.

        Args:
            file_path: Path to the file to extract

        Returns:
            The extractor that can handle this file

        Raises:
            ExtractionError: If no extractor can handle the file
        """
        for extractor in self._extractors:
            if extractor.can_handle(file_path):
                return extractor

        raise ExtractionError(
            f"no extractor can handle file: {file_path}",
            ErrorCode.EXTRACTION_UNSUPPORTED_FORMAT,
            details={"file_path": str(file_path)},
        )

    # --- Add Pipeline ---

    def _persist_preliminary_metadata(
        self,
        doc: Document,
        source_path: str,
        metadata: dict[str, Any] | None = None,
        citekey: str | None = None,
        metadata_source: MetadataSource | None = None,
    ) -> Document:
        """Persist best-effort metadata before extraction.

        Ensures every document has a citekey and basic metadata regardless
        of extraction outcome. Metadata source determines whether text
        extraction should later attempt an upgrade.

        Args:
            doc: The PENDING document to update.
            source_path: Original source path (used for filename parsing fallback).
            metadata: Explicit CSL-JSON metadata if provided.
            citekey: Explicit citekey if provided (e.g., from Zotero).
            metadata_source: MetadataSource value for provenance tracking.

        Returns:
            Updated Document with metadata fields populated.
        """
        if metadata:
            # Tag with provenance
            source_value = (metadata_source or MetadataSource.EXPLICIT).value
            tagged = {**metadata, "_metadata_source": source_value}
            return self._process_metadata(doc, tagged, citekey=citekey)
        else:
            # Parse filename for best-effort metadata
            from local_library.ingestion.metadata import parse_filename_metadata

            filename_csl = parse_filename_metadata(Path(source_path))
            try:
                # Tag with FILENAME source
                filename_csl["_metadata_source"] = MetadataSource.FILENAME.value
                return self._process_metadata(doc, filename_csl)
            except MetadataError:
                # Filename parsing produced invalid metadata -- continue without it
                logger.debug(
                    "filename metadata parsing failed for %s, continuing without",
                    source_path,
                )
                return doc

    def _attempt_metadata_upgrade(self, doc: Document, text: str) -> Document:
        """Attempt to upgrade filename-derived metadata with text extraction.

        Only called when _metadata_source is FILENAME. If text extraction
        produces useful metadata, upgrades the document. If the upgrade would
        change the existing citekey, flags NEEDS_REVIEW instead of auto-applying.

        Args:
            doc: Document with FILENAME-sourced metadata.
            text: Extracted text content for metadata extraction.

        Returns:
            Updated Document (possibly with upgraded metadata or NEEDS_REVIEW status).
        """
        extraction = self._text_extractor.extract(text)
        csl_json = build_csl_json(extraction)

        if "title" not in csl_json and "author" not in csl_json:
            # Nothing useful extracted -- keep filename metadata
            return doc

        # Tag as text-extracted
        csl_json["_metadata_source"] = MetadataSource.TEXT_EXTRACTED.value

        # Check citekey stability
        try:
            result = self._metadata_handler.process(csl_json)
        except MetadataError:
            # Invalid metadata -- keep filename version
            return doc

        candidate_citekey = result.citekey

        if doc.citekey and candidate_citekey != doc.citekey:
            # Upgrade would change citekey -- flag for review, don't auto-apply
            return update_document_status(
                self._conn,
                doc.id,
                DocumentStatus.NEEDS_REVIEW,
                error_message=(
                    f"Text extraction suggests different metadata (citekey would change "
                    f"from @{doc.citekey} to @{candidate_citekey}). "
                    "Use `local-library review` to accept or reject the upgrade."
                ),
            )

        # Same citekey (or no existing citekey) -- apply upgrade
        unique_citekey = get_unique_citekey(self._conn, candidate_citekey)

        doc = update_document_metadata(
            self._conn,
            doc.id,
            citekey=unique_citekey,
            csl_json=result.csl_json,
            title=result.title,
            authors=result.authors,
            issued_date=result.issued_date,
            issued_year=result.issued_year,
        )

        # Set NEEDS_REVIEW if extraction confidence is low
        if extraction.needs_review:
            doc = update_document_status(
                self._conn,
                doc.id,
                DocumentStatus.NEEDS_REVIEW,
                error_message="; ".join(extraction.review_reasons),
            )

        return doc

    def add(
        self,
        source: str,
        force: bool = False,
        metadata: dict[str, Any] | None = None,
        citekey: str | None = None,
        metadata_source: MetadataSource | None = None,
    ) -> AddResult:
        """Add a document to the library.

        The add pipeline:
        1. Check if acquirer can handle the source
        2. Validate the source (unless force=True for inaccessible files)
        3. Check for duplicate by original path
        4. Acquire content and compute hash
        5. Check for duplicate by content hash
        6. Move to content-addressable storage
        7. Create database record
        8. Persist preliminary metadata (before extraction)
        9. Extract text content
        10. Conditional metadata upgrade (if FILENAME source and text extraction enabled)
        11. Update record status
        12. Embed document (if embed_on_add=True and sqlite-vec available)

        Args:
            source: Path to the source file
            force: If True, create failed record for inaccessible files
            metadata: Optional CSL-JSON metadata dict
            citekey: Optional citekey to use (bypasses generation from metadata).
                    Useful when importing from external systems like Zotero.
            metadata_source: Provenance of metadata (ZOTERO, EXPLICIT, FILENAME,
                           TEXT_EXTRACTED). If None, defaults to FILENAME for bare
                           paths or EXPLICIT for explicit metadata.

        Returns:
            AddResult containing the document and duplicate status

        Raises:
            AcquisitionError: If source is invalid and force=False
            ExtractionError: If extraction fails (record created with failed status)
            MetadataError: If metadata validation fails
        """
        # Find and use appropriate acquirer
        acquirer = self._find_acquirer(source)

        # Validate source (unless force mode)
        try:
            acquirer.validate(source)
        except AcquisitionError as e:
            if force:
                # Create failed record for inaccessible file
                return self._create_failed_record(source, e)
            raise

        # Resolve source path for consistent duplicate checking
        resolved_source = str(Path(source).resolve())

        # Check for duplicate by original path
        existing = get_document_by_path(self._conn, resolved_source)
        if existing:
            return AddResult(
                document=existing,
                is_duplicate=True,
                duplicate_reason="path",
            )

        # Acquire content to temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            acquisition = acquirer.acquire(source, temp_path)

            # Check for duplicate by content hash
            existing = get_document_by_hash(self._conn, acquisition.content_hash)
            if existing:
                return AddResult(
                    document=existing,
                    is_duplicate=True,
                    duplicate_reason="hash",
                )

            # Compute storage path and move file
            source_path = Path(source)
            storage_path = compute_storage_path(
                acquisition.content_hash,
                source_path.suffix.lower(),
                self._storage_dir,
            )
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(acquisition.temp_path), str(storage_path))

            # Create database record
            doc = create_document(
                self._conn,
                original_path=acquisition.original_path,
                content_hash=acquisition.content_hash,
                storage_path=str(storage_path),
            )

            # Persist preliminary metadata before extraction
            doc = self._persist_preliminary_metadata(
                doc, resolved_source, metadata, citekey, metadata_source
            )

        # Extract text content
        try:
            extractor = self._find_extractor(storage_path)
            result = extractor.extract_and_validate(storage_path)

            # Clean up extraction artifacts then format markdown
            cleaned_text = clean_artifacts(result.text)
            cleaned_text = cleanup_markdown(cleaned_text)

            # Write extracted markdown
            extracted_path = compute_storage_path(
                doc.content_hash,
                ".md",
                self._extracted_dir,
            )
            extracted_path.parent.mkdir(parents=True, exist_ok=True)
            extracted_path.write_text(cleaned_text, encoding="utf-8")

            # Update record to ready (temporarily - may change to NEEDS_REVIEW)
            doc = update_document_status(
                self._conn,
                doc.id,
                DocumentStatus.READY,
                extracted_path=str(extracted_path),
            )

            # Check for pdftext fallback -- degraded extraction needs review
            if result.metadata.get("extraction_method") == "pdftext_fallback":
                marker_reason = result.metadata.get("marker_failure_reason", "unknown")
                doc = update_document_status(
                    self._conn,
                    doc.id,
                    DocumentStatus.NEEDS_REVIEW,
                    error_message=(
                        f"pdftext fallback used (Marker failed: {marker_reason}). "
                        "Text quality is degraded. Run reextract to try Marker again."
                    ),
                    error_code=ErrorCode.EXTRACTION_FALLBACK.value,
                )

            # Conditional metadata upgrade
            current_source = (doc.csl_json or {}).get("_metadata_source")
            if current_source == MetadataSource.FILENAME.value and self._text_extractor:
                doc = self._attempt_metadata_upgrade(doc, cleaned_text)
            # ZOTERO/EXPLICIT: authoritative, no upgrade

        except (ExtractionError, QualityError) as e:
            # Update record to failed
            doc = update_document_status(
                self._conn,
                doc.id,
                DocumentStatus.FAILED,
                error_message=e.message,
                error_code=e.code.value,
            )
            # Re-raise so caller knows extraction failed
            raise

        # Embed the document (if enabled and sqlite-vec available)
        if self._embed_on_add:
            try:
                self.embed(str(doc.id))
            except Exception:
                # Embedding failure is non-fatal for add()
                # Document is still usable, just not searchable via vectors
                # Status remains PENDING, can retry via `local-library embed`
                pass

        return AddResult(document=doc)

    def _create_failed_record(self, source: str, error: AcquisitionError) -> AddResult:
        """Create a failed record for an inaccessible file.

        Used when --force is specified for files that can't be accessed.

        Args:
            source: Original source path
            error: The acquisition error that occurred

        Returns:
            AddResult with failed document
        """
        # Generate a placeholder hash from the path
        import hashlib

        placeholder_hash = hashlib.sha256(source.encode()).hexdigest()

        # Check if we already have a failed record for this path
        existing = get_document_by_path(self._conn, source)
        if existing:
            return AddResult(
                document=existing,
                is_duplicate=True,
                duplicate_reason="path",
            )

        # Create placeholder storage path (file won't exist)
        storage_path = compute_storage_path(
            placeholder_hash,
            Path(source).suffix.lower() or ".pdf",
            self._storage_dir,
        )

        # Create record with failed status
        doc = create_document(
            self._conn,
            original_path=source,
            content_hash=placeholder_hash,
            storage_path=str(storage_path),
        )

        doc = update_document_status(
            self._conn,
            doc.id,
            DocumentStatus.FAILED,
            error_message=error.message,
            error_code=error.code.value,
        )

        return AddResult(document=doc)

    def _process_metadata(
        self, doc: Document, metadata: dict[str, Any], citekey: str | None = None
    ) -> Document:
        """Process and store metadata for a document.

        Args:
            doc: The document to update
            metadata: CSL-JSON metadata dict
            citekey: Optional citekey to use instead of generating from metadata.
                    When provided, bypasses MetadataHandler's citekey generation.

        Returns:
            Updated document with metadata

        Raises:
            MetadataError: If metadata validation fails
        """
        # Process metadata through handler
        result = self._metadata_handler.process(metadata)

        # Use provided citekey if given, otherwise use generated one
        effective_citekey = citekey if citekey is not None else result.citekey

        # Get unique citekey (handle collisions)
        unique_citekey = get_unique_citekey(self._conn, effective_citekey)

        # Update document with metadata
        return update_document_metadata(
            self._conn,
            doc.id,
            citekey=unique_citekey,
            csl_json=result.csl_json,
            title=result.title,
            authors=result.authors,
            issued_date=result.issued_date,
            issued_year=result.issued_year,
        )

    # --- Query Operations ---

    def get(self, doc_id: str) -> Document:
        """Get a document by ID (supports partial UUID matching).

        Args:
            doc_id: Full or partial UUID

        Returns:
            The matching document

        Raises:
            LookupError: If no document found or multiple matches for partial ID
        """
        # Try as full UUID first
        try:
            full_uuid = UUID(doc_id)
            doc = get_document_by_id(self._conn, full_uuid)
            if doc:
                return doc
        except ValueError:
            pass  # Not a valid UUID, try partial match

        # Try partial match
        matches = get_documents_by_partial_id(self._conn, doc_id)

        if len(matches) == 0:
            raise LookupError(
                f"document not found: {doc_id}",
                ErrorCode.NOT_FOUND,
                details={"id": doc_id},
            )

        if len(matches) > 1:
            raise LookupError(
                f"ambiguous ID prefix: {doc_id} matches {len(matches)} documents",
                ErrorCode.AMBIGUOUS_MATCH,
                details={"id": doc_id, "match_count": len(matches)},
            )

        return matches[0]

    def get_by_citekey(self, citekey: str) -> Document | None:
        """Get a document by citekey.

        Args:
            citekey: Citation key to look up

        Returns:
            Document if found, None otherwise
        """
        return get_document_by_citekey(self._conn, citekey)

    def get_all_citekeys(self) -> list[str]:
        """Get all citekeys in the library.

        Returns:
            List of all non-null citekeys
        """
        return get_all_citekeys(self._conn)

    def get_chunk_count(self, doc_id: UUID) -> int:
        """Get number of chunks for a document.

        Returns 0 if sqlite-vec is unavailable or document has no chunks.

        Args:
            doc_id: Document UUID

        Returns:
            Number of chunks
        """
        storage = self._get_embedding_storage()
        if storage is None:
            return 0
        return storage.get_chunk_count(doc_id)

    def get_chunks(
        self,
        doc_id: UUID,
        start: int | None = None,
        end: int | None = None,
    ) -> list[Chunk]:
        """Get chunks for a document, optionally by index range.

        Returns empty list if sqlite-vec is unavailable or document has no chunks.

        Args:
            doc_id: Document UUID
            start: Optional start chunk index (0-based, inclusive)
            end: Optional end chunk index (inclusive)

        Returns:
            List of Chunk objects ordered by chunk_index
        """
        storage = self._get_embedding_storage()
        if storage is None:
            return []
        chunks = storage.get_chunks_by_document(doc_id)
        if start is not None or end is not None:
            s = start if start is not None else 0
            e = (end + 1) if end is not None else len(chunks)
            chunks = [c for c in chunks if s <= c.chunk_index < e]
        return chunks

    def reextract(self, doc_id: str) -> Document:
        """Re-extract text from a document's stored PDF.

        Re-runs the extraction pipeline on the stored PDF, applies artifact
        cleanup and markdown formatting, overwrites the extracted markdown
        file, and marks embeddings as STALE. Does not modify metadata.

        Args:
            doc_id: Document UUID (full or partial) or @citekey

        Returns:
            Updated Document with new extracted_path and STALE embeddings

        Raises:
            LookupError: If document not found
            ExtractionError: If extraction fails
        """
        doc = self.get(doc_id)
        storage_path = Path(doc.storage_path)

        extractor = self._find_extractor(storage_path)
        result = extractor.extract_and_validate(storage_path)

        cleaned_text = clean_artifacts(result.text)
        cleaned_text = cleanup_markdown(cleaned_text)

        # Write to existing extracted_path, or compute new one
        if doc.extracted_path:
            extracted_path = Path(doc.extracted_path)
        else:
            extracted_path = compute_storage_path(doc.content_hash, ".md", self._extracted_dir)
        extracted_path.parent.mkdir(parents=True, exist_ok=True)
        extracted_path.write_text(cleaned_text, encoding="utf-8")

        # Determine status based on extraction method
        if result.metadata.get("extraction_method") == "pdftext_fallback":
            marker_reason = result.metadata.get("marker_failure_reason", "unknown")
            update_document_status(
                self._conn,
                doc.id,
                DocumentStatus.NEEDS_REVIEW,
                extracted_path=str(extracted_path),
                error_message=(
                    f"pdftext fallback used (Marker failed: {marker_reason}). "
                    "Text quality is degraded. Run reextract to try Marker again."
                ),
                error_code=ErrorCode.EXTRACTION_FALLBACK.value,
            )
        else:
            update_document_status(
                self._conn,
                doc.id,
                DocumentStatus.READY,
                extracted_path=str(extracted_path),
            )

        # Mark embeddings stale so they get re-embedded
        self._mark_embeddings_stale(doc.id)

        # Re-fetch to include stale embedding status
        return self.get(str(doc.id))

    def update_metadata(
        self,
        doc_id: UUID,
        status: DocumentStatus | None = None,
        citekey: str | None = None,
        csl_json: dict[str, Any] | None = None,
    ) -> Document:
        """Update a document's metadata.

        Args:
            doc_id: Document UUID
            status: New status (if changing)
            citekey: New citekey (if changing)
            csl_json: New CSL-JSON (if changing)

        Returns:
            Updated Document

        Note:
            If CSL-JSON is updated, this does not affect embeddings.
            Embeddings are tied to extracted text, not metadata.
            Re-extraction (which updates extracted_path) should mark
            embeddings as STALE via _mark_embeddings_stale().
        """
        # Extract indexed fields from CSL-JSON if provided
        title = None
        authors = None
        issued_date = None
        issued_year = None

        if csl_json:
            title = csl_json.get("title")
            if "author" in csl_json:
                author_names = []
                for author in csl_json["author"]:
                    if "family" in author:
                        name = author.get("family", "")
                        if "given" in author:
                            name = f"{author['given']} {name}"
                        author_names.append(name)
                    elif "literal" in author:
                        author_names.append(author["literal"])
                authors = "; ".join(author_names) if author_names else None

            if "issued" in csl_json:
                issued = csl_json["issued"]
                if "date-parts" in issued and issued["date-parts"]:
                    date_parts = issued["date-parts"][0]
                    if date_parts:
                        issued_date = str(date_parts[0])  # Year

            issued_year = extract_year_from_csl(csl_json)

        # Update status if provided
        if status is not None:
            update_document_status(self._conn, doc_id, status)

        # Update metadata fields
        return update_document_metadata(
            self._conn,
            doc_id,
            citekey=citekey,
            csl_json=csl_json,
            title=title,
            authors=authors,
            issued_date=issued_date,
            issued_year=issued_year,
        )

    def list(
        self,
        status: DocumentStatus | None = None,
        year: int | None = None,
        year_missing: bool = False,
        author_contains: str | None = None,
        title_contains: str | None = None,
        citekey_prefix: str | None = None,
    ) -> list[Document]:
        """List documents with optional filtering.

        All filters are optional and combine with AND semantics.

        Args:
            status: Exact status match (DocumentStatus enum).
            year: Exact match against issued_year. Mutually exclusive with year_missing.
            year_missing: If True, return only documents with no extractable year.
            author_contains: Case-insensitive substring match on authors.
            title_contains: Case-insensitive substring match on title.
            citekey_prefix: Case-insensitive prefix match on citekey.

        Returns:
            List of Document objects ordered by created_at DESC.

        Raises:
            ValueError: If year and year_missing are both provided.
        """
        return list_documents(
            self._conn,
            status=status,
            year=year,
            year_missing=year_missing,
            author_contains=author_contains,
            title_contains=title_contains,
            citekey_prefix=citekey_prefix,
        )

    def delete(self, doc_id: str, delete_files: bool = True) -> bool:
        """Delete a document and optionally its files.

        Args:
            doc_id: Full or partial UUID
            delete_files: If True, also delete storage and extracted files

        Returns:
            True if document was deleted

        Raises:
            LookupError: If document not found
        """
        doc = self.get(doc_id)

        if delete_files:
            # Delete storage file and clean up empty parent directories
            storage_path = Path(doc.storage_path)
            if storage_path.exists():
                storage_path.unlink()
                _cleanup_empty_parents(storage_path, self._storage_dir)

            # Delete extracted file and clean up empty parent directories
            if doc.extracted_path:
                extracted_path = Path(doc.extracted_path)
                if extracted_path.exists():
                    extracted_path.unlink()
                    _cleanup_empty_parents(extracted_path, self._extracted_dir)

        # Delete embeddings (cascade)
        storage = self._get_embedding_storage()
        if storage:
            storage.delete_by_document(doc.id)

        return delete_document(self._conn, doc.id)

    # --- RAG Query Operations ---

    def _get_rag_interface(self) -> RAGInterface:
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

    def _get_reranker(self) -> CrossEncoderReranker:
        """Get or create CrossEncoderReranker instance.

        Lazily initializes the cross-encoder model on first call.

        Returns:
            Configured CrossEncoderReranker instance.
        """
        if self._reranker is None:
            from local_library.embeddings.reranking import CrossEncoderReranker

            self._reranker = CrossEncoderReranker(lazy_load=True)

        return self._reranker

    def query(
        self,
        question: str,
        retriever: Retriever | None = None,
        mode: str = "hybrid",
        limit: int = 10,
        doc_ids: list[UUID] | None = None,
        rerank: bool = True,
    ) -> RAGResponse:
        """Ask a question and get a RAG-generated answer.

        Retrieves relevant document chunks, assembles context, and generates
        an LLM answer with source citations.

        Args:
            question: Natural language question.
            retriever: Pre-configured retriever (if None, creates one via get_retriever).
            mode: Retrieval mode if creating retriever ("hybrid", "vector", "fts").
            limit: Maximum number of context chunks to retrieve.
            doc_ids: Optional document ID filter.
            rerank: Whether to use cross-encoder reranking (default: True).

        Returns:
            RAGResponse with answer, source chunks, and model info.

        Raises:
            RAGError: If LLM generation fails.
            EmbeddingError: If retriever creation fails (sqlite-vec unavailable).
        """
        if retriever is None:
            retriever = self.get_retriever(mode=mode, rerank=rerank)

        search_results = retriever.retrieve(question, k=limit, doc_ids=doc_ids)

        rag = self._get_rag_interface()
        return rag.query(question, search_results, retrieval_mode=mode)

    def query_stream(
        self,
        question: str,
        retriever: Retriever | None = None,
        mode: str = "hybrid",
        limit: int = 10,
        doc_ids: list[UUID] | None = None,
        rerank: bool = True,
    ) -> RAGStream:
        """Ask a question and get a streaming RAG-generated answer.

        Like query(), but returns a RAGStream that yields tokens as they
        arrive from the LLM.

        Args:
            question: Natural language question.
            retriever: Pre-configured retriever (if None, creates one via get_retriever).
            mode: Retrieval mode if creating retriever ("hybrid", "vector", "fts").
            limit: Maximum number of context chunks to retrieve.
            doc_ids: Optional document ID filter.
            rerank: Whether to use cross-encoder reranking (default: True).

        Returns:
            RAGStream yielding answer tokens.

        Raises:
            RAGError: If LLM generation fails during streaming.
            EmbeddingError: If retriever creation fails (sqlite-vec unavailable).
        """
        if retriever is None:
            retriever = self.get_retriever(mode=mode, rerank=rerank)

        search_results = retriever.retrieve(question, k=limit, doc_ids=doc_ids)

        rag = self._get_rag_interface()
        return rag.query_stream(question, search_results, retrieval_mode=mode)
