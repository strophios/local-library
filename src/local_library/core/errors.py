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
    EXTRACTION_FALLBACK = "EXTRACTION_FALLBACK"
    EXTRACTION_UNSUPPORTED_FORMAT = "EXTRACTION_UNSUPPORTED_FORMAT"

    # Quality validation errors
    QUALITY_LOW_PRINTABLE = "QUALITY_LOW_PRINTABLE"
    QUALITY_TOO_SHORT = "QUALITY_TOO_SHORT"
    QUALITY_GARBLED_OUTPUT = "QUALITY_GARBLED_OUTPUT"

    # Storage errors
    STORAGE_DATABASE_ERROR = "STORAGE_DATABASE_ERROR"
    STORAGE_WRITE_FAILED = "STORAGE_WRITE_FAILED"
    STORAGE_MIGRATION_FAILED = "STORAGE_MIGRATION_FAILED"

    # Lookup errors
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"

    # Metadata errors
    METADATA_INVALID_SCHEMA = "METADATA_INVALID_SCHEMA"
    METADATA_INVALID_TYPE = "METADATA_INVALID_TYPE"
    METADATA_CITEKEY_INVALID = "METADATA_CITEKEY_INVALID"

    # Zotero integration errors
    ZOTERO_DIR_NOT_FOUND = "ZOTERO_DIR_NOT_FOUND"
    ZOTERO_DATABASE_NOT_FOUND = "ZOTERO_DATABASE_NOT_FOUND"
    ZOTERO_DATABASE_LOCKED = "ZOTERO_DATABASE_LOCKED"
    ZOTERO_DATABASE_ERROR = "ZOTERO_DATABASE_ERROR"
    ZOTERO_LIBRARY_JSON_NOT_FOUND = "ZOTERO_LIBRARY_JSON_NOT_FOUND"
    ZOTERO_LIBRARY_JSON_PARSE_ERROR = "ZOTERO_LIBRARY_JSON_PARSE_ERROR"
    ZOTERO_ITEM_NOT_FOUND = "ZOTERO_ITEM_NOT_FOUND"
    ZOTERO_CITEKEY_NOT_FOUND = "ZOTERO_CITEKEY_NOT_FOUND"
    ZOTERO_ATTACHMENT_MISSING = "ZOTERO_ATTACHMENT_MISSING"
    ZOTERO_COLLECTION_NOT_FOUND = "ZOTERO_COLLECTION_NOT_FOUND"
    ZOTERO_LIBRARY_NOT_FOUND = "ZOTERO_LIBRARY_NOT_FOUND"

    # Embedding errors
    EMBEDDING_EXTENSION_UNAVAILABLE = "EMBEDDING_EXTENSION_UNAVAILABLE"
    EMBEDDING_MODEL_LOAD_FAILED = "EMBEDDING_MODEL_LOAD_FAILED"
    EMBEDDING_COMPUTATION_FAILED = "EMBEDDING_COMPUTATION_FAILED"
    EMBEDDING_STORAGE_FAILED = "EMBEDDING_STORAGE_FAILED"
    EMBEDDING_CHUNK_FAILED = "EMBEDDING_CHUNK_FAILED"
    EMBEDDING_DOCUMENT_NOT_READY = "EMBEDDING_DOCUMENT_NOT_READY"
    EMBEDDING_FTS_QUERY_SYNTAX = "EMBEDDING_FTS_QUERY_SYNTAX"

    # RAG / LLM errors
    RAG_NO_CONTEXT = "RAG_NO_CONTEXT"
    LLM_GENERATION_FAILED = "LLM_GENERATION_FAILED"
    LLM_MODEL_NOT_FOUND = "LLM_MODEL_NOT_FOUND"
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"


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


class MetadataError(LocalLibraryError):
    """Error during metadata validation or processing."""

    pass


class ZoteroError(LocalLibraryError):
    """Error during Zotero data access."""

    pass


class EmbeddingError(LocalLibraryError):
    """Error during embedding operations (chunking, computation, storage)."""

    pass


class FTSQueryError(EmbeddingError):
    """FTS5 query syntax error.

    Raised when a user query contains syntax that SQLite FTS5 cannot parse
    (e.g., unbalanced quotes, invalid operators).
    """

    pass


class LLMError(LocalLibraryError):
    """Error during LLM API interaction."""

    pass


class RAGError(LocalLibraryError):
    """Error during RAG query pipeline."""

    pass
