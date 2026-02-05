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
    NEEDS_REVIEW = "needs_review"  # Extraction succeeded but confidence is low


class EmbeddingStatus(str, Enum):
    """Embedding state of a document."""

    PENDING = "pending"  # No embeddings yet (new document or embedding failed)
    CURRENT = "current"  # Embeddings match current extracted text
    STALE = "stale"  # Extracted text changed; embeddings need refresh


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
    title: str | None = None  # Extracted title for search
    authors: str | None = None  # Formatted author string for search
    issued_date: str | None = None  # ISO date or year for search

    # Error tracking for failed documents
    error_message: str | None = None
    error_code: str | None = None

    embedding_status: EmbeddingStatus = EmbeddingStatus.PENDING  # Embedding state

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
            embedding_status=EmbeddingStatus.PENDING,
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


@dataclass(frozen=True)
class MetadataResult:
    """Result of processing metadata through MetadataHandler.

    Contains validated CSL-JSON, generated citekey, extracted indexed fields,
    and any validation warnings for non-fatal issues.
    """

    csl_json: dict[str, Any]  # Validated CSL-JSON metadata
    citekey: str  # Generated or provided citation key
    title: str | None = None  # Extracted title for indexing
    authors: str | None = None  # Formatted author string for indexing
    issued_date: str | None = None  # ISO date or year for indexing
    validation_warnings: tuple[str, ...] = ()  # Non-fatal validation issues

    # Structured data for future use (e.g., normalized authors table)
    author_list: tuple[str, ...] = ()  # Individual author names

    @classmethod
    def create(
        cls,
        csl_json: dict[str, Any],
        citekey: str,
        title: str | None = None,
        authors: str | None = None,
        issued_date: str | None = None,
        validation_warnings: list[str] | None = None,
        author_list: list[str] | None = None,
    ) -> "MetadataResult":
        """Create a MetadataResult with proper tuple conversion."""
        return cls(
            csl_json=csl_json,
            citekey=citekey,
            title=title,
            authors=authors,
            issued_date=issued_date,
            validation_warnings=tuple(validation_warnings or []),
            author_list=tuple(author_list or []),
        )


@dataclass(frozen=True)
class FieldExtraction:
    """Result of extracting a single metadata field.

    Captures the extracted value along with confidence scoring and provenance
    information. Used by TextMetadataExtractor for per-field extraction results.

    Attributes:
        value: Extracted value, or None if field could not be extracted
        confidence: Confidence score from 0.0 to 1.0 (heuristic confidence,
                   preserved even if LLM provided the value)
        source: Origin of the value - "heuristic" or "llm"
        alternatives: Other candidates that were considered
        reasoning: Explanation of why this value was chosen
    """

    value: str | None
    confidence: float
    source: str  # "heuristic" | "llm"
    alternatives: tuple[str, ...]
    reasoning: str


@dataclass(frozen=True)
class TextExtractionResult:
    """Complete metadata extraction result from document text.

    Aggregates per-field extractions with overall confidence and review status.
    Used by TextMetadataExtractor as the return type for extract().

    Attributes:
        title: Extracted title field
        authors: Tuple of extracted author fields (one per author)
        date: Extracted publication date field
        doc_type: Extracted document type field
        overall_confidence: Minimum of all field confidences
        needs_review: True if any field confidence is below threshold
        review_reasons: Explanations for why review is needed
    """

    title: FieldExtraction
    authors: tuple[FieldExtraction, ...]
    date: FieldExtraction
    doc_type: FieldExtraction
    overall_confidence: float
    needs_review: bool
    review_reasons: tuple[str, ...]
