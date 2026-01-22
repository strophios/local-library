"""Core module - models, storage, orchestration."""

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
from local_library.core.library import Library
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
