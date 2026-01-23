# Phase 5: Attachment Resolution

**Goal:** Resolve Zotero itemID to file system paths for all attachments.

**External research findings:**
- Attachments stored in `itemAttachments` table with `sourceItemID` linking to parent item
- Each attachment has its own `itemID` with corresponding `key` in `items` table
- `path` column contains `storage:filename.pdf` for imported files
- Resolution: `{zotero_dir}/storage/{attachment_key}/filename`
- `linkMode` values: 0=imported_file, 1=linked_file, 2=linked_url (approximately)
- `contentType` column holds MIME type (e.g., "application/pdf")

**Codebase verification findings:**
- DatabaseManager from Phase 3 provides connection to `zotero.sqlite`
- ZoteroAttachment dataclass from Phase 1 holds resolved attachment data
- ZoteroError with ZOTERO_ATTACHMENT_MISSING code for path resolution failures

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add AttachmentResolver Class

**Files:**
- Modify: `src/local_library/ingestion/zotero.py`

**Step 1: Add the AttachmentResolver class after BbtKeyMapper**

Add the following class after the BbtKeyMapper class in `src/local_library/ingestion/zotero.py`:

```python
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

    def _resolve_storage_path(
        self, path_value: str, attachment_key: str
    ) -> Path | None:
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
        elif path_value.startswith("/") or (
            len(path_value) > 1 and path_value[1] == ":"
        ):
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
```

**Step 2: Verify the file is importable**

Run: `uv run python -c "from local_library.ingestion.zotero import AttachmentResolver; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add src/local_library/ingestion/zotero.py
git commit -m "$(cat <<'EOF'
feat(zotero): add AttachmentResolver for itemID-to-paths resolution

Queries Zotero database to resolve item attachments to filesystem paths.
Handles storage:filename format for imported files and absolute paths
for linked files. Supports optional existence validation.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Write Unit Tests for AttachmentResolver - Happy Path

**Files:**
- Modify: `tests/unit/test_zotero.py`

**Step 1: Update imports**

Update the imports at the top of `tests/unit/test_zotero.py`:

```python
"""Unit tests for Zotero data models, parsers, and database access."""

import json
import sqlite3
from pathlib import Path

import pytest

from local_library.core.errors import ErrorCode, ZoteroError
from local_library.ingestion.zotero import (
    AttachmentResolver,
    BbtKeyMapper,
    DatabaseManager,
    LibraryJsonParser,
    ZoteroAttachment,
    ZoteroItem,
)
```

**Step 2: Add AttachmentResolver test class**

Add the following test class after TestBbtKeyMapper:

```python
class TestAttachmentResolver:
    """Tests for AttachmentResolver class."""

    @pytest.fixture
    def zotero_dir_with_attachments(self, temp_dir: Path) -> Path:
        """Create mock Zotero directory with attachment data."""
        zotero_path = temp_dir / "Zotero"
        zotero_path.mkdir()

        # Create storage directory with attachment files
        storage_dir = zotero_path / "storage"
        storage_dir.mkdir()

        # Attachment 1: PDF in storage
        att1_dir = storage_dir / "ATTACH01"
        att1_dir.mkdir()
        (att1_dir / "paper.pdf").write_bytes(b"%PDF-1.4 fake pdf content")

        # Attachment 2: Another PDF
        att2_dir = storage_dir / "ATTACH02"
        att2_dir.mkdir()
        (att2_dir / "supplement.pdf").write_bytes(b"%PDF-1.4 supplement")

        # Attachment 3: Image file
        att3_dir = storage_dir / "ATTACH03"
        att3_dir.mkdir()
        (att3_dir / "figure.png").write_bytes(b"PNG fake image")

        # Create zotero.sqlite with items and attachments
        zotero_db = zotero_path / "zotero.sqlite"
        conn = sqlite3.connect(zotero_db)

        # Items table (both parent items and attachment items)
        conn.execute("""
            CREATE TABLE items (
                itemID INTEGER PRIMARY KEY,
                key TEXT NOT NULL
            )
        """)
        # Parent item
        conn.execute("INSERT INTO items VALUES (100, 'PARENT01')")
        # Attachment items (each has its own itemID and key)
        conn.execute("INSERT INTO items VALUES (101, 'ATTACH01')")
        conn.execute("INSERT INTO items VALUES (102, 'ATTACH02')")
        conn.execute("INSERT INTO items VALUES (103, 'ATTACH03')")

        # itemAttachments table
        conn.execute("""
            CREATE TABLE itemAttachments (
                itemID INTEGER PRIMARY KEY,
                sourceItemID INTEGER,
                linkMode INTEGER,
                contentType TEXT,
                path TEXT
            )
        """)
        # Attachments linked to parent item 100
        conn.execute("""
            INSERT INTO itemAttachments VALUES
            (101, 100, 0, 'application/pdf', 'storage:paper.pdf')
        """)
        conn.execute("""
            INSERT INTO itemAttachments VALUES
            (102, 100, 0, 'application/pdf', 'storage:supplement.pdf')
        """)
        conn.execute("""
            INSERT INTO itemAttachments VALUES
            (103, 100, 0, 'image/png', 'storage:figure.png')
        """)

        conn.commit()
        conn.close()

        # Create empty BBT database (required by DatabaseManager)
        bbt_db = zotero_path / "better-bibtex.sqlite"
        conn = sqlite3.connect(bbt_db)
        conn.execute("CREATE TABLE citationkey (itemID INTEGER, citationKey TEXT)")
        conn.commit()
        conn.close()

        return zotero_path

    @pytest.fixture
    def db_manager_attachments(
        self, zotero_dir_with_attachments: Path
    ) -> DatabaseManager:
        """Provide DatabaseManager for attachment tests."""
        manager = DatabaseManager(zotero_dir_with_attachments)
        yield manager
        manager.close()

    def test_get_attachments_returns_all(
        self, db_manager_attachments: DatabaseManager, zotero_dir_with_attachments: Path
    ) -> None:
        """get_attachments should return all attachments for an item."""
        resolver = AttachmentResolver(
            db_manager_attachments, zotero_dir_with_attachments
        )

        attachments = resolver.get_attachments(100)

        assert len(attachments) == 3

    def test_attachment_paths_resolved_correctly(
        self, db_manager_attachments: DatabaseManager, zotero_dir_with_attachments: Path
    ) -> None:
        """Attachment paths should be resolved to filesystem paths."""
        resolver = AttachmentResolver(
            db_manager_attachments, zotero_dir_with_attachments
        )

        attachments = resolver.get_attachments(100)
        pdf_attachment = next(a for a in attachments if a.filename == "paper.pdf")

        expected_path = (
            zotero_dir_with_attachments / "storage" / "ATTACH01" / "paper.pdf"
        )
        assert pdf_attachment.path == expected_path
        assert pdf_attachment.path.exists()

    def test_attachment_metadata_populated(
        self, db_manager_attachments: DatabaseManager, zotero_dir_with_attachments: Path
    ) -> None:
        """Attachment objects should have correct metadata."""
        resolver = AttachmentResolver(
            db_manager_attachments, zotero_dir_with_attachments
        )

        attachments = resolver.get_attachments(100)
        pdf_attachment = next(a for a in attachments if a.filename == "paper.pdf")

        assert pdf_attachment.content_type == "application/pdf"
        assert pdf_attachment.attachment_key == "ATTACH01"
        assert pdf_attachment.link_mode == 0

    def test_returns_empty_tuple_for_no_attachments(
        self, db_manager_attachments: DatabaseManager, zotero_dir_with_attachments: Path
    ) -> None:
        """get_attachments should return empty tuple for items without attachments."""
        resolver = AttachmentResolver(
            db_manager_attachments, zotero_dir_with_attachments
        )

        # Item 999 doesn't exist
        attachments = resolver.get_attachments(999)

        assert attachments == ()

    def test_attachments_are_immutable_tuple(
        self, db_manager_attachments: DatabaseManager, zotero_dir_with_attachments: Path
    ) -> None:
        """get_attachments should return immutable tuple."""
        resolver = AttachmentResolver(
            db_manager_attachments, zotero_dir_with_attachments
        )

        attachments = resolver.get_attachments(100)

        assert isinstance(attachments, tuple)
```

**Step 3: Run the tests**

Run: `uv run pytest tests/unit/test_zotero.py::TestAttachmentResolver -v`
Expected: All 5 tests pass

**Step 4: Commit**

```bash
git add tests/unit/test_zotero.py
git commit -m "$(cat <<'EOF'
test(zotero): add unit tests for AttachmentResolver happy path

Tests attachment retrieval, path resolution, metadata population,
empty results for items without attachments, and immutable tuple return.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Write Unit Tests for AttachmentResolver - Edge Cases

**Files:**
- Modify: `tests/unit/test_zotero.py`

**Step 1: Add edge case tests to TestAttachmentResolver class**

Add the following test methods to the TestAttachmentResolver class:

```python
    def test_validation_passes_when_files_exist(
        self, db_manager_attachments: DatabaseManager, zotero_dir_with_attachments: Path
    ) -> None:
        """get_attachments_with_validation should pass when files exist."""
        resolver = AttachmentResolver(
            db_manager_attachments, zotero_dir_with_attachments
        )

        # Should not raise
        attachments = resolver.get_attachments_with_validation(100, require_exists=True)

        assert len(attachments) == 3

    def test_validation_raises_for_missing_file(
        self, db_manager_attachments: DatabaseManager, zotero_dir_with_attachments: Path
    ) -> None:
        """get_attachments_with_validation should raise for missing files."""
        resolver = AttachmentResolver(
            db_manager_attachments, zotero_dir_with_attachments
        )

        # Delete one attachment file
        missing_file = (
            zotero_dir_with_attachments / "storage" / "ATTACH01" / "paper.pdf"
        )
        missing_file.unlink()

        with pytest.raises(ZoteroError) as exc_info:
            resolver.get_attachments_with_validation(100, require_exists=True)

        assert exc_info.value.code == ErrorCode.ZOTERO_ATTACHMENT_MISSING

    def test_handles_linked_file_paths(self, temp_dir: Path) -> None:
        """Resolver should handle absolute paths for linked files."""
        zotero_path = temp_dir / "ZoteroLinked"
        zotero_path.mkdir()
        (zotero_path / "storage").mkdir()

        # Create external linked file
        external_file = temp_dir / "external" / "linked.pdf"
        external_file.parent.mkdir()
        external_file.write_bytes(b"%PDF linked")

        # Database with linked file attachment
        zotero_db = zotero_path / "zotero.sqlite"
        conn = sqlite3.connect(zotero_db)
        conn.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT)")
        conn.execute("INSERT INTO items VALUES (200, 'PARENT02')")
        conn.execute("INSERT INTO items VALUES (201, 'LINKED01')")
        conn.execute("""
            CREATE TABLE itemAttachments (
                itemID INTEGER, sourceItemID INTEGER,
                linkMode INTEGER, contentType TEXT, path TEXT
            )
        """)
        # linkMode=1 for linked file, path is absolute
        conn.execute(
            "INSERT INTO itemAttachments VALUES (201, 200, 1, 'application/pdf', ?)",
            (str(external_file),),
        )
        conn.commit()
        conn.close()

        # Empty BBT database
        bbt_db = zotero_path / "better-bibtex.sqlite"
        conn = sqlite3.connect(bbt_db)
        conn.execute("CREATE TABLE citationkey (itemID INTEGER, citationKey TEXT)")
        conn.commit()
        conn.close()

        manager = DatabaseManager(zotero_path)
        resolver = AttachmentResolver(manager, zotero_path)

        try:
            attachments = resolver.get_attachments(200)

            assert len(attachments) == 1
            assert attachments[0].path == external_file
            assert attachments[0].link_mode == 1
        finally:
            manager.close()

    def test_skips_null_paths(self, temp_dir: Path) -> None:
        """Resolver should skip attachments with NULL paths."""
        zotero_path = temp_dir / "ZoteroNull"
        zotero_path.mkdir()
        (zotero_path / "storage").mkdir()

        zotero_db = zotero_path / "zotero.sqlite"
        conn = sqlite3.connect(zotero_db)
        conn.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT)")
        conn.execute("INSERT INTO items VALUES (300, 'PARENT03')")
        conn.execute("INSERT INTO items VALUES (301, 'NULLATT1')")
        conn.execute("""
            CREATE TABLE itemAttachments (
                itemID INTEGER, sourceItemID INTEGER,
                linkMode INTEGER, contentType TEXT, path TEXT
            )
        """)
        # Attachment with NULL path (e.g., embedded note or URL-only)
        conn.execute(
            "INSERT INTO itemAttachments VALUES (301, 300, 2, 'text/html', NULL)"
        )
        conn.commit()
        conn.close()

        bbt_db = zotero_path / "better-bibtex.sqlite"
        conn = sqlite3.connect(bbt_db)
        conn.execute("CREATE TABLE citationkey (itemID INTEGER, citationKey TEXT)")
        conn.commit()
        conn.close()

        manager = DatabaseManager(zotero_path)
        resolver = AttachmentResolver(manager, zotero_path)

        try:
            attachments = resolver.get_attachments(300)

            # NULL path attachment should be skipped
            assert len(attachments) == 0
        finally:
            manager.close()

    def test_handles_null_content_type(
        self, db_manager_attachments: DatabaseManager, zotero_dir_with_attachments: Path
    ) -> None:
        """Resolver should handle NULL contentType with default value."""
        # Add attachment with NULL contentType
        zotero_db = zotero_dir_with_attachments / "zotero.sqlite"
        conn = sqlite3.connect(zotero_db)
        conn.execute("INSERT INTO items VALUES (104, 'ATTACH04')")
        conn.execute("""
            INSERT INTO itemAttachments VALUES
            (104, 100, 0, NULL, 'storage:unknown.dat')
        """)
        conn.commit()
        conn.close()

        # Create the file
        att_dir = zotero_dir_with_attachments / "storage" / "ATTACH04"
        att_dir.mkdir()
        (att_dir / "unknown.dat").write_bytes(b"unknown content")

        resolver = AttachmentResolver(
            db_manager_attachments, zotero_dir_with_attachments
        )

        attachments = resolver.get_attachments(100)
        unknown_att = next(
            (a for a in attachments if a.filename == "unknown.dat"), None
        )

        assert unknown_att is not None
        assert unknown_att.content_type == "application/octet-stream"
```

**Step 2: Run all AttachmentResolver tests**

Run: `uv run pytest tests/unit/test_zotero.py::TestAttachmentResolver -v`
Expected: All 10 tests pass

**Step 3: Commit**

```bash
git add tests/unit/test_zotero.py
git commit -m "$(cat <<'EOF'
test(zotero): add edge case tests for AttachmentResolver

Tests validation with missing files, linked file paths, NULL paths
(skipped), and NULL contentType defaults to application/octet-stream.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

---

**Phase 5 Done When:**
- AttachmentResolver resolves itemID to attachment paths
- Handles imported files (storage:) and linked files (absolute paths)
- Skips NULL paths and handles NULL contentType gracefully
- Optional existence validation with appropriate errors
- All tests pass: `uv run pytest tests/unit/test_zotero.py::TestAttachmentResolver -v`
