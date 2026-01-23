"""Zotero library data access.

Provides read-only access to Zotero library data by coordinating:
- CSL-JSON metadata from Better BibTeX export (library.json)
- Citekey-to-itemID mapping from Better BibTeX SQLite database
- Attachment paths from Zotero's main SQLite database
"""

# pattern: Functional Core (dataclasses only in this initial file)

from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
