"""Ingestion module - content acquisition and extraction."""

# NOTE: Zotero module is NOT exposed here to avoid circular imports.
# Tests and users must import directly: from local_library.ingestion.zotero import ...
# This keeps zotero isolated from the ingestion -> core -> ingestion dependency chain.

# Lazy imports to prevent circular import on package initialization:
# When zotero.py is imported, we don't want ingestion.__init__.py to trigger
# the base -> core.models -> core.library -> ingestion.base cycle.


def __getattr__(name: str) -> object:  # type: ignore[name-defined]
    """Lazy-load ingestion submodules to avoid circular imports."""
    if name == "ContentAcquirer":
        from local_library.ingestion.base import ContentAcquirer

        return ContentAcquirer
    elif name == "ContentExtractor":
        from local_library.ingestion.base import ContentExtractor

        return ContentExtractor
    elif name == "compute_storage_path":
        from local_library.ingestion.base import compute_storage_path

        return compute_storage_path
    elif name == "FileAcquirer":
        from local_library.ingestion.file import FileAcquirer

        return FileAcquirer
    elif name == "compute_file_hash":
        from local_library.ingestion.file import compute_file_hash

        return compute_file_hash
    elif name == "PdfExtractor":
        from local_library.ingestion.pdf import PdfExtractor

        return PdfExtractor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Protocols
    "ContentAcquirer",
    "ContentExtractor",
    # Utilities
    "compute_storage_path",
    "compute_file_hash",
    # Implementations
    "FileAcquirer",
    "PdfExtractor",
]
