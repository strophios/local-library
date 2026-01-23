"""Core module - models, storage, orchestration."""

# NOTE: Library is lazy-loaded via __getattr__ to prevent circular imports.
# core.library imports ingestion.pdf.PdfExtractor, which imports core.errors.
# If core.__init__ eagerly imports Library, the cycle is:
# core.__init__ -> core.library -> ingestion.pdf -> core.errors
# But core.errors doesn't depend on Library, so lazy import breaks the cycle.

# Eager imports (safe; no circular dependencies)
from local_library.core.errors import (
    AcquisitionError,
    ErrorCode,
    ExtractionError,
    LocalLibraryError,
    LookupError,
    MetadataError,
    QualityError,
    StorageError,
)
from local_library.core.models import (
    AcquisitionResult,
    AddResult,
    Document,
    DocumentStatus,
    ExtractionResult,
)
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
    transaction,
    update_document_status,
)


def __getattr__(name: str) -> object:
    """Lazy-load core submodules to avoid circular imports."""
    if name == "Library":
        from local_library.core.library import Library

        return Library
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Errors
    "ErrorCode",
    "LocalLibraryError",
    "AcquisitionError",
    "ExtractionError",
    "QualityError",
    "StorageError",
    "LookupError",
    "MetadataError",
    # Models
    "DocumentStatus",
    "Document",
    "AcquisitionResult",
    "ExtractionResult",
    "AddResult",
    # Storage
    "get_connection",
    "init_schema",
    "transaction",
    "create_document",
    "get_document_by_id",
    "get_document_by_hash",
    "get_document_by_path",
    "get_documents_by_partial_id",
    "list_documents",
    "update_document_status",
    "delete_document",
    # Orchestration
    "Library",
]
