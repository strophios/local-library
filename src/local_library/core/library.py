"""Library orchestration - coordinates acquisition, extraction, and storage."""

# pattern: Imperative Shell

import shutil
import sqlite3
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

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
from local_library.core.models import AddResult, Document, DocumentStatus, EmbeddingStatus
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
from local_library.embeddings.chunking import MarkdownChunker
from local_library.embeddings.nomic import NomicEmbedder
from local_library.embeddings.storage import (
    EmbeddingStorage,
    get_documents_needing_embedding,
    update_embedding_status,
)
from local_library.ingestion.base import ContentAcquirer, ContentExtractor, compute_storage_path
from local_library.ingestion.file import FileAcquirer
from local_library.ingestion.metadata import MetadataHandler
from local_library.ingestion.pdf import PdfExtractor
from local_library.ingestion.text_extraction import (
    TextMetadataExtractor,
    build_csl_json,
)


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
            else [PdfExtractor(lazy_load=True, llm_enabled=pdf_llm_enabled)]
        )

        # Initialize metadata handler
        self._metadata_handler = MetadataHandler()

        # Initialize text metadata extractor
        self._text_extractor = (
            TextMetadataExtractor(
                confidence_threshold=text_extraction_confidence_threshold,
                llm_enabled=text_extraction_llm_enabled,
                llm_model=text_extraction_llm_model,
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
        self._embed_on_add = embed_on_add and is_vec_available()
        self._embedding_batch_size = embedding_batch_size
        self._chunker = MarkdownChunker() if self._embed_on_add else None
        if self._embed_on_add:
            self._embedder = NomicEmbedder(batch_size=embedding_batch_size, lazy_load=True)
        else:
            self._embedder = None
        self._embedding_storage = None  # Lazy init when needed

    @property
    def conn(self) -> sqlite3.Connection:
        """Get the database connection."""
        return self._conn

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> "Library":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

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

    def _mark_embeddings_stale(self, doc_id: UUID) -> None:
        """Mark document's embeddings as stale.

        Called when extracted text changes and embeddings need refresh.

        Args:
            doc_id: Document UUID
        """
        if is_vec_available():
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

    def add(
        self,
        source: str,
        force: bool = False,
        metadata: dict[str, Any] | None = None,
        citekey: str | None = None,
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
        8. Extract text content
        9. Process metadata (if provided)
        10. Update record status
        11. Embed document (if embed_on_add=True and sqlite-vec available)

        Args:
            source: Path to the source file
            force: If True, create failed record for inaccessible files
            metadata: Optional CSL-JSON metadata dict
            citekey: Optional citekey to use (bypasses generation from metadata).
                    Useful when importing from external systems like Zotero.

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

        # Extract text content
        try:
            extractor = self._find_extractor(storage_path)
            result = extractor.extract_and_validate(storage_path)

            # Write extracted markdown
            extracted_path = compute_storage_path(
                doc.content_hash,
                ".md",
                self._extracted_dir,
            )
            extracted_path.parent.mkdir(parents=True, exist_ok=True)
            extracted_path.write_text(result.text, encoding="utf-8")

            # Update record to ready (temporarily - may change to NEEDS_REVIEW)
            doc = update_document_status(
                self._conn,
                doc.id,
                DocumentStatus.READY,
                extracted_path=str(extracted_path),
            )

            # Process metadata
            if metadata:
                # Explicit metadata provided
                doc = self._process_metadata(doc, metadata, citekey=citekey)
            elif self._text_extractor:
                # Extract metadata from text
                doc = self._process_text_extraction(doc, result.text)

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
        )

    def _process_text_extraction(self, doc: Document, text: str) -> Document:
        """Extract and process metadata from document text.

        Args:
            doc: The document to update
            text: Extracted text content

        Returns:
            Updated document with extracted metadata
        """
        # Extract metadata from text
        extraction = self._text_extractor.extract(text)

        # Convert to CSL-JSON
        csl_json = build_csl_json(extraction)

        # Only process if we have enough metadata
        if "title" not in csl_json and "author" not in csl_json:
            # Nothing useful extracted - update status to NEEDS_REVIEW
            return update_document_status(
                self._conn,
                doc.id,
                DocumentStatus.NEEDS_REVIEW,
                error_message="No metadata could be extracted from document text",
            )

        try:
            # Process through MetadataHandler for validation and citekey
            result = self._metadata_handler.process(csl_json)

            # Get unique citekey
            unique_citekey = get_unique_citekey(self._conn, result.citekey)

            # Determine final status
            final_status = (
                DocumentStatus.NEEDS_REVIEW if extraction.needs_review else DocumentStatus.READY
            )

            # Update document
            doc = update_document_metadata(
                self._conn,
                doc.id,
                citekey=unique_citekey,
                csl_json=result.csl_json,
                title=result.title,
                authors=result.authors,
                issued_date=result.issued_date,
            )

            # Update status if needed
            if final_status == DocumentStatus.NEEDS_REVIEW:
                doc = update_document_status(
                    self._conn,
                    doc.id,
                    DocumentStatus.NEEDS_REVIEW,
                    error_message="; ".join(extraction.review_reasons),
                )

            return doc

        except MetadataError:
            # Extracted metadata failed validation - still set what we can
            return update_document_status(
                self._conn,
                doc.id,
                DocumentStatus.NEEDS_REVIEW,
                error_message="Extracted metadata failed validation",
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
        )

    def list(self, status: DocumentStatus | None = None) -> list[Document]:
        """List all documents, optionally filtered by status.

        Args:
            status: Filter by status if provided

        Returns:
            List of documents, ordered by created_at descending
        """
        return list_documents(self._conn, status=status)

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
