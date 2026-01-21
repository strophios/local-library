"""Data models for documents and operation results."""

# pattern: Functional Core

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4


class DocumentStatus(str, Enum):
    """Lifecycle status of a document record."""

    PENDING = "pending"  # Created, not yet processed
    READY = "ready"  # Extraction complete, searchable
    FAILED = "failed"  # Extraction failed, needs retry or manual intervention


@dataclass(frozen=True)
class Document:
    """A document record in the library.

    Represents a PDF (or future content type) that has been ingested.
    Tracks the document through its lifecycle from acquisition to extraction.
    """

    id: UUID
    original_path: str  # Path where the document was originally located
    content_hash: str  # SHA-256 hash of file contents
    storage_path: str  # Path in content-addressable storage
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime

    # Nullable fields - populated after extraction or metadata processing
    extracted_path: str | None = None  # Path to extracted markdown
    citekey: str | None = None  # BetterBibTeX-style citation key
    csl_json: dict[str, Any] | None = None  # Bibliographic metadata

    # Error tracking for failed documents
    error_message: str | None = None
    error_code: str | None = None

    @classmethod
    def create_pending(
        cls,
        original_path: str,
        content_hash: str,
        storage_path: str,
    ) -> "Document":
        """Create a new pending document record."""
        now = datetime.now(timezone.utc)
        return cls(
            id=uuid4(),
            original_path=original_path,
            content_hash=content_hash,
            storage_path=storage_path,
            status=DocumentStatus.PENDING,
            created_at=now,
            updated_at=now,
        )


@dataclass(frozen=True)
class AcquisitionResult:
    """Result of acquiring content from a source.

    Returned by ContentAcquirer implementations after successfully
    copying/downloading content to a temporary location.
    """

    content_hash: str  # SHA-256 hash of acquired content
    temp_path: Path  # Temporary location of acquired file
    original_path: str  # Original source path/URL

    # Optional metadata discovered during acquisition
    file_size: int = 0
    mime_type: str | None = None


@dataclass
class ExtractionResult:
    """Result of extracting content from a document.

    Returned by ContentExtractor implementations after processing
    a document (e.g., PDF to markdown conversion).
    """

    text: str  # Extracted text content (markdown)
    metadata: dict[str, Any] = field(default_factory=dict)  # Document metadata
    images: list[bytes] = field(default_factory=list)  # Extracted images (optional)
    page_count: int = 0

    # Quality metrics
    character_count: int = 0
    printable_ratio: float = 0.0

    def validate(self, min_length: int = 100, min_printable_ratio: float = 0.8) -> bool:
        """Check if extraction result meets quality thresholds.

        Args:
            min_length: Minimum character count for valid extraction
            min_printable_ratio: Minimum ratio of printable characters (0.0-1.0)

        Returns:
            True if extraction passes quality checks, False otherwise
        """
        if self.character_count < min_length:
            return False
        if self.printable_ratio < min_printable_ratio:
            return False
        return True

    @classmethod
    def from_text(cls, text: str, metadata: dict[str, Any] | None = None) -> "ExtractionResult":
        """Create an ExtractionResult from extracted text, computing quality metrics."""
        char_count = len(text)
        printable_count = sum(1 for c in text if c.isprintable() or c.isspace())
        printable_ratio = printable_count / char_count if char_count > 0 else 0.0

        return cls(
            text=text,
            metadata=metadata or {},
            character_count=char_count,
            printable_ratio=printable_ratio,
        )


@dataclass(frozen=True)
class AddResult:
    """Result of adding a document to the library.

    Supports idempotent add operations - duplicate detection returns
    existing records rather than erroring.
    """

    document: Document
    is_duplicate: bool = False  # True if returning existing record
    duplicate_reason: str | None = None  # "path" or "hash" if duplicate
