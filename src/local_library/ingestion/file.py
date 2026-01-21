"""Local file acquisition implementation."""

# pattern: Imperative Shell

import hashlib
from pathlib import Path

from local_library.core.errors import AcquisitionError, ErrorCode
from local_library.core.models import AcquisitionResult


class FileAcquirer:
    """Acquirer for local filesystem files.

    Validates file existence and readability, copies to destination,
    and computes SHA-256 content hash.
    """

    def can_handle(self, source: str) -> bool:
        """Check if source is a local file path (not a URL).

        Args:
            source: Source path to check

        Returns:
            True if source appears to be a local file path
        """
        # Reject URLs (simple heuristic: starts with common URL schemes)
        if source.startswith(("http://", "https://", "ftp://", "file://")):
            return False

        try:
            # Check it's a valid path-like string
            Path(source)
            return True
        except (ValueError, OSError):
            return False

    def validate(self, source: str) -> None:
        """Validate that file exists and is readable.

        Args:
            source: Path to the file

        Raises:
            AcquisitionError: If file doesn't exist or isn't readable
        """
        path = Path(source)

        if not path.exists():
            raise AcquisitionError(
                f"file not found: {source}",
                ErrorCode.ACQUISITION_FILE_NOT_FOUND,
                details={"path": source},
            )

        if not path.is_file():
            raise AcquisitionError(
                f"not a file: {source}",
                ErrorCode.ACQUISITION_INVALID_FORMAT,
                details={"path": source},
            )

        # Check readability by attempting to open
        try:
            with open(path, "rb") as f:
                f.read(1)  # Read 1 byte to verify access
        except PermissionError as e:
            raise AcquisitionError(
                f"file not readable: {source}",
                ErrorCode.ACQUISITION_FILE_NOT_READABLE,
                details={"path": source},
            ) from e
        except OSError as e:
            raise AcquisitionError(
                f"cannot access file: {source}: {e}",
                ErrorCode.ACQUISITION_FILE_NOT_READABLE,
                details={"path": source},
            ) from e

        # Validate extension
        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise AcquisitionError(
                f"unsupported file type: {path.suffix}",
                ErrorCode.ACQUISITION_INVALID_FORMAT,
                details={"path": source, "extension": path.suffix},
            )

    def acquire(self, source: str, dest_dir: Path) -> AcquisitionResult:
        """Copy file to destination and compute hash.

        Args:
            source: Path to the source file
            dest_dir: Directory to copy the file to

        Returns:
            AcquisitionResult with hash and temp path

        Raises:
            AcquisitionError: If copy fails
        """
        source_path = Path(source).resolve()

        # Compute hash while copying
        hasher = hashlib.sha256()
        file_size = 0

        # Determine destination filename (preserve extension)
        temp_filename = f"acquired{source_path.suffix}"
        temp_path = dest_dir / temp_filename

        try:
            dest_dir.mkdir(parents=True, exist_ok=True)

            with open(source_path, "rb") as src_file:
                with open(temp_path, "wb") as dst_file:
                    while chunk := src_file.read(8192):
                        hasher.update(chunk)
                        dst_file.write(chunk)
                        file_size += len(chunk)

        except OSError as e:
            raise AcquisitionError(
                f"failed to copy file: {e}",
                ErrorCode.ACQUISITION_COPY_FAILED,
                details={"source": source, "dest": str(temp_path)},
            ) from e

        content_hash = hasher.hexdigest()

        return AcquisitionResult(
            content_hash=content_hash,
            temp_path=temp_path,
            original_path=str(source_path),
            file_size=file_size,
            mime_type="application/pdf",  # For now, only PDFs supported
        )


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file.

    Args:
        file_path: Path to the file

    Returns:
        Hex-encoded SHA-256 hash
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()
