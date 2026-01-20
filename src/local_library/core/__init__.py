"""Core module - models, storage, orchestration."""

from local_library.core.errors import (
    AcquisitionError,
    ErrorCode,
    ExtractionError,
    LocalLibraryError,
    LookupError,
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

__all__ = [
    # Errors
    "ErrorCode",
    "LocalLibraryError",
    "AcquisitionError",
    "ExtractionError",
    "QualityError",
    "StorageError",
    "LookupError",
    # Models
    "DocumentStatus",
    "Document",
    "AcquisitionResult",
    "ExtractionResult",
    "AddResult",
]
