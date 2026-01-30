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
    "ZoteroCollection",
    "ZoteroItem",
    "ZoteroLibrary",
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


@dataclass(frozen=True)
class ZoteroCollection:
    """A Zotero collection (folder for organizing items).

    Represents a collection with its metadata and position in the
    collection hierarchy.

    Attributes:
        collection_id: Zotero's internal numeric ID
        name: Display name of the collection
        key: Zotero's 8-character key (stable across syncs)
        parent_id: Parent collection's ID (None for top-level)
        library_id: Library this collection belongs to (1 = personal)
    """

    collection_id: int
    name: str
    key: str
    parent_id: int | None
    library_id: int

    def is_top_level(self) -> bool:
        """Check if this is a top-level collection (no parent)."""
        return self.parent_id is None


@dataclass(frozen=True)
class ZoteroLibrary:
    """A Zotero library (personal or group).

    Represents a library with its type and optional group metadata.

    Attributes:
        library_id: Zotero's internal library ID (1 = personal library)
        library_type: 'user' for personal, 'group' for group libraries
        name: Display name (personal library name or group name)
        editable: Whether the library is editable
    """

    library_id: int
    library_type: str
    name: str
    editable: bool

    def is_personal(self) -> bool:
        """Check if this is the user's personal library."""
        return self.library_type == "user"

    def is_group(self) -> bool:
        """Check if this is a group library."""
        return self.library_type == "group"


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
        # parentItemID links attachment to parent item (renamed from sourceItemID in Zotero 7+)
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
            WHERE ia.parentItemID = ?
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


class CollectionResolver:
    """Resolves Zotero collections and their item memberships.

    Queries the Zotero SQLite database to list collections and
    determine which items belong to each collection.

    The Zotero schema:
    - collections: collectionID, collectionName, parentCollectionID, key
    - collectionItems: collectionID, itemID (many-to-many junction)
    """

    def __init__(self, db_manager: DatabaseManager, key_mapper: BbtKeyMapper) -> None:
        """Initialize collection resolver.

        Args:
            db_manager: DatabaseManager providing database access
            key_mapper: BbtKeyMapper for resolving itemID to citekey
        """
        self._db_manager = db_manager
        self._key_mapper = key_mapper
        self._collection_cache: dict[str, ZoteroCollection] | None = None

    def _load_collections(self) -> dict[str, ZoteroCollection]:
        """Load all collections from database, indexed by name.

        Returns:
            Dictionary mapping collection name to ZoteroCollection
        """
        conn = self._db_manager.get_connection(DatabaseManager.ZOTERO_DB)

        cursor = conn.execute(
            """
            SELECT collectionID, collectionName, parentCollectionID, key, libraryID
            FROM collections
            """
        )

        collections = {}
        for row in cursor:
            collection = ZoteroCollection(
                collection_id=row["collectionID"],
                name=row["collectionName"],
                key=row["key"],
                parent_id=row["parentCollectionID"],
                library_id=row["libraryID"],
            )
            collections[collection.name] = collection

        return collections

    def _ensure_loaded(self) -> dict[str, ZoteroCollection]:
        """Ensure collection cache is loaded."""
        if self._collection_cache is None:
            self._collection_cache = self._load_collections()
        return self._collection_cache

    def list_collections(self, library_id: int | None = None) -> list[ZoteroCollection]:
        """List collections, optionally filtered by library.

        Args:
            library_id: If provided, filter to collections in this library only

        Returns:
            List of ZoteroCollection objects sorted by name
        """
        collections = self._ensure_loaded()
        result = collections.values()

        if library_id is not None:
            result = [c for c in result if c.library_id == library_id]

        return sorted(result, key=lambda c: c.name.lower())

    def get_collection(self, name: str) -> ZoteroCollection:
        """Get a collection by name.

        Args:
            name: Collection name (case-sensitive)

        Returns:
            ZoteroCollection

        Raises:
            ZoteroError: If collection not found (ZOTERO_COLLECTION_NOT_FOUND)
        """
        collections = self._ensure_loaded()

        if name not in collections:
            raise ZoteroError(
                message=f"collection not found: {name}",
                code=ErrorCode.ZOTERO_COLLECTION_NOT_FOUND,
                details={"name": name, "available": list(collections.keys())},
            )

        return collections[name]

    def get_item_ids_in_collection(self, collection_id: int) -> list[int]:
        """Get all item IDs in a collection.

        Args:
            collection_id: The collection's internal ID

        Returns:
            List of itemIDs in the collection
        """
        conn = self._db_manager.get_connection(DatabaseManager.ZOTERO_DB)

        cursor = conn.execute(
            """
            SELECT itemID FROM collectionItems WHERE collectionID = ?
            """,
            (collection_id,),
        )

        return [row["itemID"] for row in cursor]

    def get_citekeys_in_collection(self, collection_name: str) -> Iterator[str]:
        """Get all citekeys for items in a collection.

        Resolves item IDs to citekeys via Better BibTeX. Items without
        citekeys (not in BBT) are silently skipped.

        Args:
            collection_name: Collection name (case-sensitive)

        Yields:
            Citekeys for items in the collection

        Raises:
            ZoteroError: If collection not found (ZOTERO_COLLECTION_NOT_FOUND)
        """
        collection = self.get_collection(collection_name)
        item_ids = self.get_item_ids_in_collection(collection.collection_id)

        # Get BBT database connection for reverse lookup
        bbt_conn = self._db_manager.get_connection(DatabaseManager.BBT_DB)

        for item_id in item_ids:
            # Look up citekey from BBT
            cursor = bbt_conn.execute(
                "SELECT citationKey FROM citationkey WHERE itemID = ?",
                (item_id,),
            )
            row = cursor.fetchone()
            if row is not None:
                yield row["citationKey"]


class LibraryResolver:
    """Resolves Zotero libraries and provides filtering.

    Queries the Zotero SQLite database to list libraries and
    determine which items belong to each library.

    The Zotero schema:
    - libraries: libraryID, type ('user' or 'group'), editable
    - groups: groupID, libraryID, name (for group libraries)
    """

    # Personal library is always libraryID = 1
    PERSONAL_LIBRARY_ID = 1

    def __init__(self, db_manager: DatabaseManager) -> None:
        """Initialize library resolver.

        Args:
            db_manager: DatabaseManager providing database access
        """
        self._db_manager = db_manager
        self._library_cache: dict[int, ZoteroLibrary] | None = None

    def _load_libraries(self) -> dict[int, ZoteroLibrary]:
        """Load all libraries from database, indexed by libraryID.

        Returns:
            Dictionary mapping libraryID to ZoteroLibrary
        """
        conn = self._db_manager.get_connection(DatabaseManager.ZOTERO_DB)

        # Load base library info
        cursor = conn.execute(
            """
            SELECT libraryID, type, editable FROM libraries
            """
        )

        libraries = {}
        for row in cursor:
            library_id = row["libraryID"]
            library_type = row["type"]

            # Personal library gets special name
            if library_type == "user":
                name = "My Library"
            else:
                name = f"Library {library_id}"  # Default, will be overwritten

            libraries[library_id] = ZoteroLibrary(
                library_id=library_id,
                library_type=library_type,
                name=name,
                editable=bool(row["editable"]),
            )

        # Load group names for group libraries
        cursor = conn.execute(
            """
            SELECT libraryID, name FROM groups
            """
        )

        for row in cursor:
            library_id = row["libraryID"]
            if library_id in libraries:
                # Replace with named version
                old = libraries[library_id]
                libraries[library_id] = ZoteroLibrary(
                    library_id=old.library_id,
                    library_type=old.library_type,
                    name=row["name"],
                    editable=old.editable,
                )

        return libraries

    def _ensure_loaded(self) -> dict[int, ZoteroLibrary]:
        """Ensure library cache is loaded."""
        if self._library_cache is None:
            self._library_cache = self._load_libraries()
        return self._library_cache

    def list_libraries(self) -> list[ZoteroLibrary]:
        """List all libraries, personal first then groups alphabetically.

        Returns:
            List of ZoteroLibrary objects
        """
        libraries = self._ensure_loaded()

        # Sort: personal library first, then groups by name
        def sort_key(lib: ZoteroLibrary) -> tuple[int, str]:
            return (0 if lib.is_personal() else 1, lib.name.lower())

        return sorted(libraries.values(), key=sort_key)

    def get_library(self, library_id: int) -> ZoteroLibrary:
        """Get a library by ID.

        Args:
            library_id: The library's ID (1 for personal)

        Returns:
            ZoteroLibrary

        Raises:
            ZoteroError: If library not found (ZOTERO_LIBRARY_NOT_FOUND)
        """
        libraries = self._ensure_loaded()

        if library_id not in libraries:
            raise ZoteroError(
                message=f"library not found: {library_id}",
                code=ErrorCode.ZOTERO_LIBRARY_NOT_FOUND,
                details={"library_id": library_id, "available": list(libraries.keys())},
            )

        return libraries[library_id]

    def get_personal_library(self) -> ZoteroLibrary:
        """Get the user's personal library.

        Returns:
            ZoteroLibrary for the personal library

        Raises:
            ZoteroError: If personal library not found
        """
        return self.get_library(self.PERSONAL_LIBRARY_ID)

    def get_item_ids_in_library(self, library_id: int) -> list[int]:
        """Get all item IDs in a library.

        Args:
            library_id: The library's ID

        Returns:
            List of itemIDs in the library
        """
        conn = self._db_manager.get_connection(DatabaseManager.ZOTERO_DB)

        cursor = conn.execute(
            """
            SELECT itemID FROM items WHERE libraryID = ?
            """,
            (library_id,),
        )

        return [row["itemID"] for row in cursor]


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
        self._collection_resolver = CollectionResolver(self._db_manager, self._key_mapper)
        self._library_resolver = LibraryResolver(self._db_manager)

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

    def list_collections(self, library_id: int | None = None) -> list[ZoteroCollection]:
        """List collections, optionally filtered by library.

        Args:
            library_id: If provided, filter to collections in this library only

        Returns:
            List of ZoteroCollection objects sorted by name
        """
        return self._collection_resolver.list_collections(library_id=library_id)

    def list_citekeys_in_collection(self, collection_name: str) -> Iterator[str]:
        """Iterate over citekeys in a specific collection.

        Args:
            collection_name: Collection name (case-sensitive)

        Yields:
            Citekeys for items in the collection

        Raises:
            ZoteroError: If collection not found (ZOTERO_COLLECTION_NOT_FOUND)
        """
        return self._collection_resolver.get_citekeys_in_collection(collection_name)

    def list_libraries(self) -> list[ZoteroLibrary]:
        """List all libraries (personal and group).

        Returns:
            List of ZoteroLibrary objects, personal first then groups
        """
        return self._library_resolver.list_libraries()

    def get_personal_library(self) -> ZoteroLibrary:
        """Get the user's personal library.

        Returns:
            ZoteroLibrary for the personal library
        """
        return self._library_resolver.get_personal_library()

    def list_citekeys_in_library(self, library_id: int) -> Iterator[str]:
        """Iterate over citekeys in a specific library.

        Filters to items that belong to the specified library.
        Items without citekeys (not in BBT) are silently skipped.

        Args:
            library_id: Library ID (1 for personal library)

        Yields:
            Citekeys for items in the library
        """
        # Get item IDs in this library
        item_ids = set(self._library_resolver.get_item_ids_in_library(library_id))

        # Get BBT connection for citekey lookup
        bbt_conn = self._db_manager.get_connection(DatabaseManager.BBT_DB)

        for item_id in item_ids:
            cursor = bbt_conn.execute(
                "SELECT citationKey FROM citationkey WHERE itemID = ?",
                (item_id,),
            )
            row = cursor.fetchone()
            if row is not None:
                # Verify it's also in library.json
                if self._json_parser.has_citekey(row["citationKey"]):
                    yield row["citationKey"]

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
