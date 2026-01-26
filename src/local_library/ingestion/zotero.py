"""Zotero library data access.

Provides read-only access to Zotero library data by coordinating:
- CSL-JSON metadata from Better BibTeX export (library.json)
- Citekey-to-itemID mapping from Better BibTeX SQLite database
- Attachment paths from Zotero's main SQLite database
"""

# pattern: Mixed (unavoidable)
# Reason: JSON file I/O and database I/O cannot be separated from parsing logic without
# introducing unnecessary complexity. Classes encapsulate external access.

import json
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from local_library.core.errors import ErrorCode, ZoteroError

__all__ = [
    "ZoteroAttachment",
    "ZoteroItem",
    "ZoteroReader",
]


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


class DatabaseManager:
    """Manages read-only access to Zotero SQLite databases.

    Handles database locking (when Zotero is running) by copying to a
    temporary location. Provides connection caching and cleanup.

    SQLite databases are opened in read-only mode via URI to prevent
    accidental writes.
    """

    # Database filenames in Zotero profile directory
    ZOTERO_DB = "zotero.sqlite"
    BBT_DB = "better-bibtex.sqlite"

    def __init__(self, zotero_dir: Path, temp_dir: Path | None = None) -> None:
        """Initialize database manager.

        Args:
            zotero_dir: Path to Zotero profile directory containing databases
            temp_dir: Directory for temporary database copies (uses system temp if None)

        Raises:
            ZoteroError: If zotero_dir doesn't exist (ZOTERO_DIR_NOT_FOUND)
        """
        if not zotero_dir.exists():
            raise ZoteroError(
                message=f"zotero directory not found: {zotero_dir}",
                code=ErrorCode.ZOTERO_DIR_NOT_FOUND,
                details={"path": str(zotero_dir)},
            )

        self._zotero_dir = zotero_dir
        self._temp_dir = temp_dir
        self._connections: dict[str, sqlite3.Connection] = {}
        self._temp_copies: list[Path] = []  # Track for cleanup
        self._managed_temp_dir: tempfile.TemporaryDirectory | None = None

    def _get_temp_dir(self) -> Path:
        """Get or create temporary directory for database copies."""
        if self._temp_dir is not None:
            self._temp_dir.mkdir(parents=True, exist_ok=True)
            return self._temp_dir

        # Create managed temp dir if not provided
        if self._managed_temp_dir is None:
            self._managed_temp_dir = tempfile.TemporaryDirectory(prefix="zotero_reader_")
        return Path(self._managed_temp_dir.name)

    def _copy_to_temp(self, db_path: Path) -> Path:
        """Copy database to temporary location.

        Args:
            db_path: Path to the database file

        Returns:
            Path to the temporary copy

        Raises:
            ZoteroError: If copy fails (ZOTERO_DATABASE_ERROR)
        """
        temp_dir = self._get_temp_dir()
        temp_path = temp_dir / db_path.name

        try:
            shutil.copy2(db_path, temp_path)
        except OSError as e:
            raise ZoteroError(
                message=f"failed to copy database: {e}",
                code=ErrorCode.ZOTERO_DATABASE_ERROR,
                details={"source": str(db_path), "dest": str(temp_path), "error": str(e)},
            ) from e

        self._temp_copies.append(temp_path)
        return temp_path

    def _open_readonly(self, db_path: Path) -> sqlite3.Connection:
        """Open database in read-only mode.

        Uses SQLite URI mode to enforce read-only access.

        Args:
            db_path: Path to the database file

        Returns:
            Read-only database connection

        Raises:
            ZoteroError: If database is locked (ZOTERO_DATABASE_LOCKED) or
                        other error (ZOTERO_DATABASE_ERROR)
        """
        # SQLite URI format for read-only access
        uri = f"file:{db_path}?mode=ro"

        try:
            conn = sqlite3.connect(uri, uri=True, timeout=1.0)
            conn.row_factory = sqlite3.Row  # Enable column access by name
            # Test that we can actually read
            conn.execute("SELECT 1")
            return conn
        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if "locked" in error_msg or "busy" in error_msg:
                raise ZoteroError(
                    message=f"database is locked: {db_path}",
                    code=ErrorCode.ZOTERO_DATABASE_LOCKED,
                    details={"path": str(db_path), "error": str(e)},
                ) from e
            raise ZoteroError(
                message=f"database error: {e}",
                code=ErrorCode.ZOTERO_DATABASE_ERROR,
                details={"path": str(db_path), "error": str(e)},
            ) from e

    def get_connection(self, db_name: str) -> sqlite3.Connection:
        """Get a connection to a Zotero database.

        Attempts to open the database directly in read-only mode.
        If the database is locked (Zotero is running), copies to
        a temporary location and opens the copy.

        Connections are cached for reuse within a session.

        Args:
            db_name: Database filename (e.g., "zotero.sqlite" or "better-bibtex.sqlite")

        Returns:
            Read-only database connection

        Raises:
            ZoteroError: If database doesn't exist (ZOTERO_DATABASE_NOT_FOUND)
                        or access fails (ZOTERO_DATABASE_ERROR)
        """
        # Return cached connection if available
        if db_name in self._connections:
            return self._connections[db_name]

        db_path = self._zotero_dir / db_name

        if not db_path.exists():
            raise ZoteroError(
                message=f"database not found: {db_path}",
                code=ErrorCode.ZOTERO_DATABASE_NOT_FOUND,
                details={"path": str(db_path), "db_name": db_name},
            )

        try:
            # Try direct read-only access first
            conn = self._open_readonly(db_path)
        except ZoteroError as e:
            if e.code != ErrorCode.ZOTERO_DATABASE_LOCKED:
                raise
            # Database is locked, copy to temp and retry
            temp_path = self._copy_to_temp(db_path)
            conn = self._open_readonly(temp_path)

        self._connections[db_name] = conn
        return conn

    def close(self) -> None:
        """Close all connections and clean up temporary files."""
        for conn in self._connections.values():
            try:
                conn.close()
            except Exception:
                pass  # Best effort cleanup
        self._connections.clear()

        # Clean up temp copies
        for temp_path in self._temp_copies:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
        self._temp_copies.clear()

        # Clean up managed temp dir
        if self._managed_temp_dir is not None:
            try:
                self._managed_temp_dir.cleanup()
            except Exception:
                pass
            self._managed_temp_dir = None


class BbtKeyMapper:
    """Maps Better BibTeX citekeys to Zotero item identifiers.

    Queries the Better BibTeX SQLite database to resolve citekeys to
    Zotero's internal itemID and stable itemKey.

    The BBT database schema includes a `citationkey` table that maps
    itemID to citationKey. We join with Zotero's items table to get
    the stable itemKey (8-character alphanumeric key).
    """

    def __init__(self, db_manager: DatabaseManager) -> None:
        """Initialize with database manager.

        Args:
            db_manager: DatabaseManager providing access to BBT and Zotero databases
        """
        self._db_manager = db_manager

    def lookup(self, citekey: str) -> tuple[int, str]:
        """Resolve a citekey to Zotero item identifiers.

        Args:
            citekey: Better BibTeX citation key

        Returns:
            Tuple of (itemID, itemKey) where:
            - itemID: Zotero's internal numeric ID (used for database joins)
            - itemKey: Zotero's 8-character stable key (used for storage paths)

        Raises:
            ZoteroError: If citekey not found (ZOTERO_CITEKEY_NOT_IN_BBT)
        """
        bbt_conn = self._db_manager.get_connection(DatabaseManager.BBT_DB)
        zotero_conn = self._db_manager.get_connection(DatabaseManager.ZOTERO_DB)

        # Query BBT for itemID
        cursor = bbt_conn.execute(
            "SELECT itemID FROM citationkey WHERE citationKey = ?",
            (citekey,),
        )
        row = cursor.fetchone()

        if row is None:
            raise ZoteroError(
                message=f"citekey not found in Better BibTeX: {citekey}",
                code=ErrorCode.ZOTERO_CITEKEY_NOT_IN_BBT,
                details={"citekey": citekey},
            )

        item_id = row["itemID"]

        # Query Zotero for itemKey
        cursor = zotero_conn.execute(
            "SELECT key FROM items WHERE itemID = ?",
            (item_id,),
        )
        row = cursor.fetchone()

        if row is None:
            # This shouldn't happen if BBT and Zotero are in sync
            raise ZoteroError(
                message=f"itemID {item_id} from BBT not found in Zotero database",
                code=ErrorCode.ZOTERO_ITEM_NOT_FOUND,
                details={"citekey": citekey, "item_id": item_id},
            )

        return (item_id, row["key"])

    def has_citekey(self, citekey: str) -> bool:
        """Check if a citekey exists in Better BibTeX.

        Args:
            citekey: Better BibTeX citation key

        Returns:
            True if citekey exists, False otherwise
        """
        bbt_conn = self._db_manager.get_connection(DatabaseManager.BBT_DB)

        cursor = bbt_conn.execute(
            "SELECT 1 FROM citationkey WHERE citationKey = ? LIMIT 1",
            (citekey,),
        )
        return cursor.fetchone() is not None


class AttachmentResolver:
    """Resolves Zotero item attachments to file system paths.

    Queries the Zotero SQLite database to find all attachments for a given
    item, then resolves the storage paths to actual filesystem locations.

    Zotero stores attachment paths in formats like:
    - "storage:filename.pdf" -> {zotero_dir}/storage/{attachment_key}/filename.pdf
    - Absolute paths for linked files (linkMode=1)
    - URLs for linked URLs (linkMode=2) - not resolved to filesystem
    """

    # Path prefix for imported files in Zotero storage
    STORAGE_PREFIX = "storage:"

    def __init__(self, db_manager: DatabaseManager, zotero_dir: Path) -> None:
        """Initialize attachment resolver.

        Args:
            db_manager: DatabaseManager providing database access
            zotero_dir: Path to Zotero profile directory (contains storage/ folder)
        """
        self._db_manager = db_manager
        self._zotero_dir = zotero_dir
        self._storage_dir = zotero_dir / "storage"

    def _resolve_storage_path(self, path_value: str, attachment_key: str) -> Path | None:
        """Resolve a Zotero storage path to filesystem path.

        Args:
            path_value: Path value from database (e.g., "storage:file.pdf")
            attachment_key: The attachment's 8-character key

        Returns:
            Resolved Path, or None if path format not recognized
        """
        if path_value.startswith(self.STORAGE_PREFIX):
            # Imported file: storage:filename.pdf
            filename = path_value[len(self.STORAGE_PREFIX) :]
            return self._storage_dir / attachment_key / filename
        elif path_value.startswith("/") or (len(path_value) > 1 and path_value[1] == ":"):
            # Absolute path (Unix or Windows)
            return Path(path_value)
        else:
            # Unknown format (possibly URL or other)
            return None

    def get_attachments(self, item_id: int) -> tuple[ZoteroAttachment, ...]:
        """Get all attachments for a Zotero item.

        Args:
            item_id: Zotero's internal itemID for the parent item

        Returns:
            Tuple of ZoteroAttachment objects (may be empty)
        """
        conn = self._db_manager.get_connection(DatabaseManager.ZOTERO_DB)

        # Query attachments with their keys
        # sourceItemID links attachment to parent item
        # itemID is the attachment's own ID (for its key lookup)
        cursor = conn.execute(
            """
            SELECT
                ia.itemID as attachment_item_id,
                i.key as attachment_key,
                ia.path,
                ia.contentType,
                ia.linkMode
            FROM itemAttachments ia
            JOIN items i ON ia.itemID = i.itemID
            WHERE ia.sourceItemID = ?
            """,
            (item_id,),
        )

        attachments = []
        for row in cursor:
            path_value = row["path"]
            attachment_key = row["attachment_key"]
            content_type = row["contentType"] or "application/octet-stream"
            link_mode = row["linkMode"] or 0

            # Skip if no path (e.g., linked URLs may have no local path)
            if not path_value:
                continue

            resolved_path = self._resolve_storage_path(path_value, attachment_key)

            # Skip if path couldn't be resolved (e.g., URL attachments)
            if resolved_path is None:
                continue

            # Extract filename from path
            if path_value.startswith(self.STORAGE_PREFIX):
                filename = path_value[len(self.STORAGE_PREFIX) :]
            else:
                filename = resolved_path.name

            attachments.append(
                ZoteroAttachment(
                    path=resolved_path,
                    filename=filename,
                    content_type=content_type,
                    attachment_key=attachment_key,
                    link_mode=link_mode,
                )
            )

        return tuple(attachments)

    def get_attachments_with_validation(
        self, item_id: int, require_exists: bool = False
    ) -> tuple[ZoteroAttachment, ...]:
        """Get attachments with optional existence validation.

        Args:
            item_id: Zotero's internal itemID
            require_exists: If True, raise error if any attachment file is missing

        Returns:
            Tuple of ZoteroAttachment objects

        Raises:
            ZoteroError: If require_exists=True and any file is missing
                        (ZOTERO_ATTACHMENT_MISSING)
        """
        attachments = self.get_attachments(item_id)

        if require_exists:
            for attachment in attachments:
                if not attachment.path.exists():
                    raise ZoteroError(
                        message=f"attachment file not found: {attachment.path}",
                        code=ErrorCode.ZOTERO_ATTACHMENT_MISSING,
                        details={
                            "path": str(attachment.path),
                            "attachment_key": attachment.attachment_key,
                            "item_id": item_id,
                        },
                    )

        return attachments


class ZoteroReader:
    """Read-only access to Zotero library data.

    Coordinates three data sources to provide complete item data:
    - library.json (CSL-JSON export from Better BibTeX) for metadata
    - better-bibtex.sqlite for citekey-to-itemID mapping
    - zotero.sqlite for attachment paths

    Usage:
        with ZoteroReader(zotero_dir) as reader:
            for citekey in reader.list_citekeys():
                item = reader.get_item(citekey)
                print(f"{citekey}: {item.csl_json.get('title')}")
                for att in item.pdf_attachments():
                    print(f"  - {att.path}")

    The reader serves as a data source for Library.add() rather than
    implementing ContentAcquirer. Future batch import will iterate
    list_citekeys() and call Library.add() for each.
    """

    def __init__(
        self,
        zotero_dir: Path,
        library_json_path: Path | None = None,
        temp_dir: Path | None = None,
    ) -> None:
        """Initialize Zotero reader.

        Args:
            zotero_dir: Path to Zotero profile directory containing databases
                        and storage/ folder
            library_json_path: Path to Better BibTeX CSL-JSON export.
                              Defaults to zotero_dir/library.json
            temp_dir: Directory for temporary database copies when locked.
                     Uses system temp if None.

        Raises:
            ZoteroError: If zotero_dir doesn't exist (ZOTERO_DIR_NOT_FOUND)
            ZoteroError: If library.json doesn't exist (ZOTERO_LIBRARY_JSON_NOT_FOUND)
        """
        # Check zotero_dir exists first (before trying to access library.json)
        if not zotero_dir.exists():
            raise ZoteroError(
                message=f"zotero directory not found: {zotero_dir}",
                code=ErrorCode.ZOTERO_DIR_NOT_FOUND,
                details={"path": str(zotero_dir)},
            )

        self._zotero_dir = zotero_dir

        # Determine library.json path
        if library_json_path is None:
            library_json_path = zotero_dir / "library.json"
        self._library_json_path = library_json_path

        # Initialize components
        self._json_parser = LibraryJsonParser(library_json_path)
        self._db_manager = DatabaseManager(zotero_dir, temp_dir=temp_dir)
        self._key_mapper = BbtKeyMapper(self._db_manager)
        self._attachment_resolver = AttachmentResolver(self._db_manager, zotero_dir)

    def get_item(self, citekey: str) -> ZoteroItem:
        """Get complete item data for a citekey.

        Combines CSL-JSON metadata with resolved attachment paths.

        Args:
            citekey: Better BibTeX citation key

        Returns:
            ZoteroItem with metadata and attachments

        Raises:
            ZoteroError: If citekey not found in library.json (ZOTERO_ITEM_NOT_FOUND)
            ZoteroError: If citekey not in BBT database (ZOTERO_CITEKEY_NOT_IN_BBT)
        """
        # Get metadata from library.json
        metadata = self._json_parser.get_metadata(citekey)
        if metadata is None:
            raise ZoteroError(
                message=f"item not found in library.json: {citekey}",
                code=ErrorCode.ZOTERO_ITEM_NOT_FOUND,
                details={"citekey": citekey, "source": "library.json"},
            )

        # Resolve citekey to Zotero IDs
        item_id, item_key = self._key_mapper.lookup(citekey)

        # Get attachments
        attachments = self._attachment_resolver.get_attachments(item_id)

        return ZoteroItem(
            citekey=citekey,
            csl_json=metadata,
            attachments=attachments,
            zotero_key=item_key,
            item_id=item_id,
        )

    def list_citekeys(self) -> Iterator[str]:
        """Iterate over all citekeys in the library.

        Yields citekeys from library.json. Note that some citekeys
        may not be in the BBT database if the export is newer than
        the database.

        Yields:
            Citation keys in arbitrary order
        """
        return self._json_parser.list_citekeys()

    def has_item(self, citekey: str) -> bool:
        """Check if a citekey exists in the library.

        Checks library.json only (fast). Does not verify BBT database
        or attachments.

        Args:
            citekey: Better BibTeX citation key

        Returns:
            True if citekey exists in library.json
        """
        return self._json_parser.has_citekey(citekey)

    def get_metadata(self, citekey: str) -> dict[str, Any]:
        """Get CSL-JSON metadata for a citekey without database access.

        This is a lightweight alternative to get_item() that only reads
        from library.json. Use when you only need metadata and not
        attachments or Zotero IDs.

        Args:
            citekey: Better BibTeX citation key

        Returns:
            CSL-JSON metadata dictionary

        Raises:
            ZoteroError: If citekey not found (ZOTERO_ITEM_NOT_FOUND)
        """
        metadata = self._json_parser.get_metadata(citekey)
        if metadata is None:
            raise ZoteroError(
                message=f"item not found in library.json: {citekey}",
                code=ErrorCode.ZOTERO_ITEM_NOT_FOUND,
                details={"citekey": citekey, "source": "library.json"},
            )
        return metadata

    def refresh(self) -> None:
        """Reload library.json from disk.

        Call this after Better BibTeX has re-exported the library.
        Database connections are not affected (they reflect current
        database state on each query).
        """
        self._json_parser.refresh()

    def close(self) -> None:
        """Close all database connections and clean up resources."""
        self._db_manager.close()

    def __enter__(self) -> "ZoteroReader":
        """Enter context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit context manager, closing resources."""
        self.close()
