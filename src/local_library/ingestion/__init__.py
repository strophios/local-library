"""Ingestion module - content acquisition and extraction."""

from local_library.ingestion.base import (
    ContentAcquirer,
    ContentExtractor,
    compute_storage_path,
)
from local_library.ingestion.file import FileAcquirer, compute_file_hash

__all__ = [
    # Protocols
    "ContentAcquirer",
    "ContentExtractor",
    # Utilities
    "compute_storage_path",
    "compute_file_hash",
    # Implementations
    "FileAcquirer",
]
