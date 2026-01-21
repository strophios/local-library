"""Protocol definitions for content acquisition and extraction."""

# pattern: Functional Core

from pathlib import Path
from typing import Protocol, runtime_checkable

from local_library.core.models import AcquisitionResult, ExtractionResult


@runtime_checkable
class ContentAcquirer(Protocol):
    """Protocol for acquiring content from various sources.

    Implementations handle specific source types (local files, URLs, etc.)
    and copy content to a temporary location for processing.
    """

    def can_handle(self, source: str) -> bool:
        """Check if this acquirer can handle the given source.

        Args:
            source: Source identifier (path, URL, etc.)

        Returns:
            True if this acquirer can handle the source
        """
        ...

    def validate(self, source: str) -> None:
        """Validate that the source is accessible and valid.

        Args:
            source: Source identifier to validate

        Raises:
            AcquisitionError: If source is invalid or inaccessible
        """
        ...

    def acquire(self, source: str, dest_dir: Path) -> AcquisitionResult:
        """Acquire content from source to destination directory.

        Copies/downloads the content and computes its hash.

        Args:
            source: Source identifier (path, URL, etc.)
            dest_dir: Directory to place the acquired file

        Returns:
            AcquisitionResult with hash, temp path, and metadata

        Raises:
            AcquisitionError: If acquisition fails
        """
        ...


@runtime_checkable
class ContentExtractor(Protocol):
    """Protocol for extracting text content from files.

    Implementations handle specific file formats (PDF, DOCX, etc.)
    and convert them to markdown text.
    """

    def can_handle(self, file_path: Path) -> bool:
        """Check if this extractor can handle the given file.

        Args:
            file_path: Path to the file to check

        Returns:
            True if this extractor can handle the file
        """
        ...

    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract text content from file.

        Args:
            file_path: Path to the file to extract

        Returns:
            ExtractionResult with extracted text and metadata

        Raises:
            ExtractionError: If extraction fails
        """
        ...

    def extract_and_validate(
        self,
        file_path: Path,
        min_length: int | None = None,
        min_printable_ratio: float | None = None,
    ) -> ExtractionResult:
        """Extract text and validate quality.

        Args:
            file_path: Path to the file to extract
            min_length: Minimum character count
            min_printable_ratio: Minimum printable character ratio

        Returns:
            ExtractionResult if extraction passes quality checks

        Raises:
            ExtractionError: If extraction fails
            QualityError: If extraction fails quality validation
        """
        ...


def compute_storage_path(content_hash: str, extension: str, base_dir: Path) -> Path:
    """Compute content-addressable storage path.

    Uses Git-style layout: ab/cd/abcd1234...ext

    Args:
        content_hash: SHA-256 hash of the content
        extension: File extension (e.g., ".pdf")
        base_dir: Base directory for storage

    Returns:
        Full path for storing the file
    """
    # Git-style: first 2 chars / next 2 chars / full hash
    prefix1 = content_hash[:2]
    prefix2 = content_hash[2:4]
    filename = f"{content_hash}{extension}"

    return base_dir / prefix1 / prefix2 / filename
