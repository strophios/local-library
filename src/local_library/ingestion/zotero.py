"""Zotero library data access.

Provides read-only access to Zotero library data by coordinating:
- CSL-JSON metadata from Better BibTeX export (library.json)
- Citekey-to-itemID mapping from Better BibTeX SQLite database
- Attachment paths from Zotero's main SQLite database
"""

# pattern: Mixed (unavoidable)
# Reason: JSON file I/O cannot be separated from parsing logic without
# introducing unnecessary complexity. The class encapsulates file access.

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from local_library.core.errors import ErrorCode, ZoteroError


@dataclass(frozen=True)
class ZoteroAttachment:
    """A single attachment from a Zotero item.

    Represents a file attached to a Zotero library item, with resolved
    path and metadata about how the file is stored.

    Attributes:
        path: Resolved absolute path to the attachment file
        filename: Original filename as stored in Zotero
        content_type: MIME type (e.g., "application/pdf")
        attachment_key: Zotero's 8-character key for this attachment
        link_mode: Storage mode - 0=imported, 1=linked file, 2=linked URL
    """

    path: Path
    filename: str
    content_type: str
    attachment_key: str
    link_mode: int

    def is_pdf(self) -> bool:
        """Check if this attachment is a PDF file."""
        return self.content_type == "application/pdf"

    def is_imported(self) -> bool:
        """Check if this attachment is imported into Zotero storage."""
        return self.link_mode == 0

    def is_linked_file(self) -> bool:
        """Check if this attachment is a linked external file."""
        return self.link_mode == 1


@dataclass(frozen=True)
class ZoteroItem:
    """Complete item data from Zotero, ready for Library.add().

    Combines bibliographic metadata (CSL-JSON) with resolved attachments.
    Designed as input for the standard Library ingestion pipeline.

    Attributes:
        citekey: Better BibTeX citation key (primary lookup key)
        csl_json: Full CSL-JSON metadata dictionary
        attachments: All attachments for this item (immutable tuple)
        zotero_key: Zotero's 8-character item key (stable across syncs)
        item_id: Zotero's internal itemID (used for database joins)
    """

    citekey: str
    csl_json: dict[str, Any]
    attachments: tuple[ZoteroAttachment, ...]
    zotero_key: str
    item_id: int

    def pdf_attachments(self) -> tuple[ZoteroAttachment, ...]:
        """Return only PDF attachments."""
        return tuple(a for a in self.attachments if a.is_pdf())

    def has_attachments(self) -> bool:
        """Check if this item has any attachments."""
        return len(self.attachments) > 0

    def has_pdf(self) -> bool:
        """Check if this item has at least one PDF attachment."""
        return any(a.is_pdf() for a in self.attachments)


class LibraryJsonParser:
    """Parses and indexes CSL-JSON metadata from Better BibTeX export.

    Loads library.json (exported by Better BibTeX) and builds an index
    for efficient citekey-based lookup. Metadata is cached in memory
    after first load.

    The expected format is a JSON array of CSL-JSON objects, where each
    object has a `citation-key` field added by Better BibTeX.
    """

    def __init__(self, library_json_path: Path) -> None:
        """Initialize parser with path to library.json.

        Args:
            library_json_path: Path to Better BibTeX CSL-JSON export

        Raises:
            ZoteroError: If file doesn't exist (ZOTERO_LIBRARY_JSON_NOT_FOUND)
        """
        self._path = library_json_path
        self._index: dict[str, dict[str, Any]] | None = None

        if not self._path.exists():
            raise ZoteroError(
                message=f"library.json not found: {library_json_path}",
                code=ErrorCode.ZOTERO_LIBRARY_JSON_NOT_FOUND,
                details={"path": str(library_json_path)},
            )

    def _load(self) -> None:
        """Load and index the library JSON file.

        Builds a dictionary mapping citekey -> CSL-JSON metadata.

        Raises:
            ZoteroError: If JSON parsing fails (ZOTERO_LIBRARY_JSON_PARSE_ERROR)
        """
        try:
            with open(self._path, encoding="utf-8") as f:
                items = json.load(f)
        except json.JSONDecodeError as e:
            raise ZoteroError(
                message=f"failed to parse library.json: {e}",
                code=ErrorCode.ZOTERO_LIBRARY_JSON_PARSE_ERROR,
                details={"path": str(self._path), "error": str(e)},
            ) from e
        except OSError as e:
            raise ZoteroError(
                message=f"failed to read library.json: {e}",
                code=ErrorCode.ZOTERO_LIBRARY_JSON_PARSE_ERROR,
                details={"path": str(self._path), "error": str(e)},
            ) from e

        if not isinstance(items, list):
            raise ZoteroError(
                message="library.json must contain a JSON array",
                code=ErrorCode.ZOTERO_LIBRARY_JSON_PARSE_ERROR,
                details={"path": str(self._path), "type": type(items).__name__},
            )

        self._index = {}
        for item in items:
            # Better BibTeX adds citation-key to each item
            citekey = item.get("citation-key") or item.get("id")
            if citekey:
                self._index[citekey] = item

    def _ensure_loaded(self) -> dict[str, dict[str, Any]]:
        """Ensure index is loaded, loading if necessary."""
        if self._index is None:
            self._load()
        assert self._index is not None  # for type checker
        return self._index

    def get_metadata(self, citekey: str) -> dict[str, Any] | None:
        """Get CSL-JSON metadata for a citekey.

        Args:
            citekey: Better BibTeX citation key

        Returns:
            CSL-JSON metadata dictionary, or None if not found
        """
        index = self._ensure_loaded()
        return index.get(citekey)

    def has_citekey(self, citekey: str) -> bool:
        """Check if a citekey exists in the library.

        Args:
            citekey: Better BibTeX citation key

        Returns:
            True if citekey exists, False otherwise
        """
        index = self._ensure_loaded()
        return citekey in index

    def list_citekeys(self) -> Iterator[str]:
        """Iterate over all citekeys in the library.

        Yields:
            Citation keys in arbitrary order
        """
        index = self._ensure_loaded()
        yield from index.keys()

    def refresh(self) -> None:
        """Clear cache and reload from disk on next access.

        Call this after Better BibTeX has re-exported the library.
        """
        self._index = None
