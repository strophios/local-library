"""Custom exceptions with error codes for programmatic handling."""

# pattern: Functional Core

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Machine-parseable error codes for categorizing failures."""

    # Acquisition errors
    ACQUISITION_FILE_NOT_FOUND = "ACQUISITION_FILE_NOT_FOUND"
    ACQUISITION_FILE_NOT_READABLE = "ACQUISITION_FILE_NOT_READABLE"
    ACQUISITION_INVALID_FORMAT = "ACQUISITION_INVALID_FORMAT"
    ACQUISITION_COPY_FAILED = "ACQUISITION_COPY_FAILED"
    ACQUISITION_UNSUPPORTED_SOURCE = "ACQUISITION_UNSUPPORTED_SOURCE"

    # Extraction errors
    EXTRACTION_MARKER_CRASH = "EXTRACTION_MARKER_CRASH"
    EXTRACTION_TIMEOUT = "EXTRACTION_TIMEOUT"
    EXTRACTION_EMPTY_OUTPUT = "EXTRACTION_EMPTY_OUTPUT"
    EXTRACTION_UNSUPPORTED_FORMAT = "EXTRACTION_UNSUPPORTED_FORMAT"

    # Quality validation errors
    QUALITY_LOW_PRINTABLE = "QUALITY_LOW_PRINTABLE"
    QUALITY_TOO_SHORT = "QUALITY_TOO_SHORT"
    QUALITY_GARBLED_OUTPUT = "QUALITY_GARBLED_OUTPUT"

    # Storage errors
    STORAGE_DATABASE_ERROR = "STORAGE_DATABASE_ERROR"
    STORAGE_WRITE_FAILED = "STORAGE_WRITE_FAILED"

    # Lookup errors
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"

    # Metadata errors
    METADATA_INVALID_SCHEMA = "METADATA_INVALID_SCHEMA"
    METADATA_INVALID_TYPE = "METADATA_INVALID_TYPE"
    METADATA_CITEKEY_INVALID = "METADATA_CITEKEY_INVALID"


class LocalLibraryError(Exception):
    """Base exception for all local-library errors."""

    def __init__(
        self,
        message: str,
        code: ErrorCode,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"


class AcquisitionError(LocalLibraryError):
    """Error during content acquisition (file access, copying)."""

    pass


class ExtractionError(LocalLibraryError):
    """Error during content extraction (Marker processing)."""

    pass


class QualityError(LocalLibraryError):
    """Error when extracted content fails quality validation."""

    pass


class StorageError(LocalLibraryError):
    """Error during database or file storage operations."""

    pass


class LookupError(LocalLibraryError):
    """Error when looking up records (not found, ambiguous match)."""

    pass
