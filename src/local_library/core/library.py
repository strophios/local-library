"""Library orchestration - coordinates acquisition, extraction, and storage."""

# pattern: Imperative Shell

import shutil
import sqlite3
import tempfile
from pathlib import Path
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
    QualityError,
)
from local_library.core.models import AddResult, Document, DocumentStatus
from local_library.core.storage import (
    create_document,
    delete_document,
    get_connection,
    get_document_by_hash,
    get_document_by_id,
    get_document_by_path,
    get_documents_by_partial_id,
    init_schema,
    list_documents,
    update_document_status,
)
from local_library.ingestion.base import ContentAcquirer, ContentExtractor, compute_storage_path
from local_library.ingestion.file import FileAcquirer
from local_library.ingestion.pdf import PdfExtractor


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
    ) -> None:
        """Initialize the library.

        Args:
            db_path: Path to SQLite database (default: platformdirs user data)
            storage_dir: Directory for content-addressable storage (default: platformdirs)
            extracted_dir: Directory for extracted markdown (default: platformdirs)
        """
        # Use defaults from config if not specified
        self._db_path = db_path or get_database_path()
        self._storage_dir = storage_dir or get_storage_dir()
        self._extracted_dir = extracted_dir or get_extracted_dir()

        # Initialize components
        self._acquirer = FileAcquirer()
        self._extractor = PdfExtractor(lazy_load=True)

        # Ensure directories exist
        ensure_directories()

        # Initialize database
        self._conn = get_connection(self._db_path)
        init_schema(self._conn)

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
        # For now, we only have one acquirer - will be refactored in Phase 3
        if self._acquirer.can_handle(source):
            return self._acquirer

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
        # For now, we only have one extractor - will be refactored in Phase 3
        if self._extractor.can_handle(file_path):
            return self._extractor

        raise ExtractionError(
            f"no extractor can handle file: {file_path}",
            ErrorCode.EXTRACTION_UNSUPPORTED_FORMAT,
            details={"file_path": str(file_path)},
        )

    # --- Add Pipeline ---

    def add(self, source: str, force: bool = False) -> AddResult:
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
        9. Update record status

        Args:
            source: Path to the source file
            force: If True, create failed record for inaccessible files

        Returns:
            AddResult containing the document and duplicate status

        Raises:
            AcquisitionError: If source is invalid and force=False
            ExtractionError: If extraction fails (record created with failed status)
        """
        # Check if we can handle this source
        if not self._acquirer.can_handle(source):
            raise AcquisitionError(
                f"unsupported source type: {source}",
                ErrorCode.ACQUISITION_INVALID_FORMAT,
                details={"source": source},
            )

        # Validate source (unless force mode)
        try:
            self._acquirer.validate(source)
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
            acquisition = self._acquirer.acquire(source, temp_path)

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
            result = self._extractor.extract_and_validate(storage_path)

            # Write extracted markdown
            extracted_path = compute_storage_path(
                doc.content_hash,
                ".md",
                self._extracted_dir,
            )
            extracted_path.parent.mkdir(parents=True, exist_ok=True)
            extracted_path.write_text(result.text, encoding="utf-8")

            # Update record to ready
            doc = update_document_status(
                self._conn,
                doc.id,
                DocumentStatus.READY,
                extracted_path=str(extracted_path),
            )

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
            # Delete storage file
            storage_path = Path(doc.storage_path)
            if storage_path.exists():
                storage_path.unlink()

            # Delete extracted file
            if doc.extracted_path:
                extracted_path = Path(doc.extracted_path)
                if extracted_path.exists():
                    extracted_path.unlink()

        return delete_document(self._conn, doc.id)
