"""Unit tests for Zotero data models, parsers, and database access."""

import json
import sqlite3
from pathlib import Path

import pytest

from local_library.core.errors import ErrorCode, ZoteroError
from local_library.ingestion.zotero import (
    AttachmentResolver,
    BbtKeyMapper,
    CollectionResolver,
    DatabaseManager,
    LibraryJsonParser,
    ZoteroAttachment,
    ZoteroCollection,
    ZoteroItem,
    ZoteroReader,
)


class TestZoteroAttachment:
    """Tests for ZoteroAttachment dataclass."""

    def test_creates_frozen_dataclass(self) -> None:
        """ZoteroAttachment should be immutable."""
        attachment = ZoteroAttachment(
            path=Path("/zotero/storage/ABCD1234/paper.pdf"),
            filename="paper.pdf",
            content_type="application/pdf",
            attachment_key="ABCD1234",
            link_mode=0,
        )

        with pytest.raises(AttributeError):
            attachment.path = Path("/other/path.pdf")  # type: ignore[misc]

    def test_is_pdf_returns_true_for_pdf(self) -> None:
        """is_pdf should return True for PDF content type."""
        attachment = ZoteroAttachment(
            path=Path("/storage/doc.pdf"),
            filename="doc.pdf",
            content_type="application/pdf",
            attachment_key="KEY12345",
            link_mode=0,
        )

        assert attachment.is_pdf() is True

    def test_is_pdf_returns_false_for_non_pdf(self) -> None:
        """is_pdf should return False for non-PDF content types."""
        attachment = ZoteroAttachment(
            path=Path("/storage/image.png"),
            filename="image.png",
            content_type="image/png",
            attachment_key="KEY12345",
            link_mode=0,
        )

        assert attachment.is_pdf() is False

    def test_is_imported_for_link_mode_0(self) -> None:
        """is_imported should return True for link_mode 0."""
        attachment = ZoteroAttachment(
            path=Path("/storage/doc.pdf"),
            filename="doc.pdf",
            content_type="application/pdf",
            attachment_key="KEY12345",
            link_mode=0,
        )

        assert attachment.is_imported() is True

    def test_is_linked_file_for_link_mode_1(self) -> None:
        """is_linked_file should return True for link_mode 1."""
        attachment = ZoteroAttachment(
            path=Path("/external/doc.pdf"),
            filename="doc.pdf",
            content_type="application/pdf",
            attachment_key="KEY12345",
            link_mode=1,
        )

        assert attachment.is_linked_file() is True

    def test_is_imported_returns_false_for_link_mode_1(self) -> None:
        """is_imported should return False for link_mode 1."""
        attachment = ZoteroAttachment(
            path=Path("/external/doc.pdf"),
            filename="doc.pdf",
            content_type="application/pdf",
            attachment_key="KEY12345",
            link_mode=1,
        )

        assert attachment.is_imported() is False

    def test_is_linked_file_returns_false_for_link_mode_0(self) -> None:
        """is_linked_file should return False for link_mode 0."""
        attachment = ZoteroAttachment(
            path=Path("/storage/doc.pdf"),
            filename="doc.pdf",
            content_type="application/pdf",
            attachment_key="KEY12345",
            link_mode=0,
        )

        assert attachment.is_linked_file() is False


class TestZoteroItem:
    """Tests for ZoteroItem dataclass."""

    @pytest.fixture
    def pdf_attachment(self) -> ZoteroAttachment:
        """Provide a sample PDF attachment."""
        return ZoteroAttachment(
            path=Path("/storage/paper.pdf"),
            filename="paper.pdf",
            content_type="application/pdf",
            attachment_key="PDFKEY12",
            link_mode=0,
        )

    @pytest.fixture
    def image_attachment(self) -> ZoteroAttachment:
        """Provide a sample image attachment."""
        return ZoteroAttachment(
            path=Path("/storage/figure.png"),
            filename="figure.png",
            content_type="image/png",
            attachment_key="IMGKEY12",
            link_mode=0,
        )

    @pytest.fixture
    def sample_csl_json(self) -> dict:
        """Provide sample CSL-JSON metadata."""
        return {
            "id": "smith2023",
            "type": "article-journal",
            "title": "A Sample Paper",
            "author": [{"family": "Smith", "given": "John"}],
            "issued": {"date-parts": [[2023]]},
        }

    def test_creates_frozen_dataclass(
        self, pdf_attachment: ZoteroAttachment, sample_csl_json: dict
    ) -> None:
        """ZoteroItem should be immutable."""
        item = ZoteroItem(
            citekey="smith2023",
            csl_json=sample_csl_json,
            attachments=(pdf_attachment,),
            zotero_key="ITEMKEY1",
            item_id=12345,
        )

        with pytest.raises(AttributeError):
            item.citekey = "other"  # type: ignore[misc]

    def test_pdf_attachments_filters_pdfs(
        self,
        pdf_attachment: ZoteroAttachment,
        image_attachment: ZoteroAttachment,
        sample_csl_json: dict,
    ) -> None:
        """pdf_attachments should return only PDF attachments."""
        item = ZoteroItem(
            citekey="smith2023",
            csl_json=sample_csl_json,
            attachments=(pdf_attachment, image_attachment),
            zotero_key="ITEMKEY1",
            item_id=12345,
        )

        pdfs = item.pdf_attachments()

        assert len(pdfs) == 1
        assert pdfs[0].content_type == "application/pdf"

    def test_has_attachments_true_when_present(
        self, pdf_attachment: ZoteroAttachment, sample_csl_json: dict
    ) -> None:
        """has_attachments should return True when attachments exist."""
        item = ZoteroItem(
            citekey="smith2023",
            csl_json=sample_csl_json,
            attachments=(pdf_attachment,),
            zotero_key="ITEMKEY1",
            item_id=12345,
        )

        assert item.has_attachments() is True

    def test_has_attachments_false_when_empty(self, sample_csl_json: dict) -> None:
        """has_attachments should return False when no attachments."""
        item = ZoteroItem(
            citekey="smith2023",
            csl_json=sample_csl_json,
            attachments=(),
            zotero_key="ITEMKEY1",
            item_id=12345,
        )

        assert item.has_attachments() is False

    def test_has_pdf_true_when_pdf_present(
        self, pdf_attachment: ZoteroAttachment, sample_csl_json: dict
    ) -> None:
        """has_pdf should return True when PDF attachment exists."""
        item = ZoteroItem(
            citekey="smith2023",
            csl_json=sample_csl_json,
            attachments=(pdf_attachment,),
            zotero_key="ITEMKEY1",
            item_id=12345,
        )

        assert item.has_pdf() is True

    def test_has_pdf_false_when_no_pdf(
        self, image_attachment: ZoteroAttachment, sample_csl_json: dict
    ) -> None:
        """has_pdf should return False when no PDF attachments."""
        item = ZoteroItem(
            citekey="smith2023",
            csl_json=sample_csl_json,
            attachments=(image_attachment,),
            zotero_key="ITEMKEY1",
            item_id=12345,
        )

        assert item.has_pdf() is False


class TestLibraryJsonParser:
    """Tests for LibraryJsonParser class."""

    @pytest.fixture
    def sample_library_json(self) -> list[dict]:
        """Provide sample CSL-JSON library data."""
        return [
            {
                "id": "smith2023",
                "citation-key": "smith2023",
                "type": "article-journal",
                "title": "A Sample Paper",
                "author": [{"family": "Smith", "given": "John"}],
                "issued": {"date-parts": [[2023]]},
            },
            {
                "id": "jones2022",
                "citation-key": "jones2022",
                "type": "book",
                "title": "A Sample Book",
                "author": [{"family": "Jones", "given": "Jane"}],
                "issued": {"date-parts": [[2022]]},
            },
        ]

    @pytest.fixture
    def library_json_file(self, temp_dir: Path, sample_library_json: list[dict]) -> Path:
        """Create a temporary library.json file."""
        path = temp_dir / "library.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sample_library_json, f)
        return path

    def test_get_metadata_returns_csl_json(
        self, library_json_file: Path, sample_library_json: list[dict]
    ) -> None:
        """get_metadata should return CSL-JSON for valid citekey."""
        parser = LibraryJsonParser(library_json_file)

        metadata = parser.get_metadata("smith2023")

        assert metadata is not None
        assert metadata["title"] == "A Sample Paper"
        assert metadata["type"] == "article-journal"

    def test_get_metadata_returns_none_for_unknown(self, library_json_file: Path) -> None:
        """get_metadata should return None for unknown citekey."""
        parser = LibraryJsonParser(library_json_file)

        metadata = parser.get_metadata("nonexistent")

        assert metadata is None

    def test_has_citekey_returns_true_for_existing(self, library_json_file: Path) -> None:
        """has_citekey should return True for existing citekey."""
        parser = LibraryJsonParser(library_json_file)

        assert parser.has_citekey("smith2023") is True
        assert parser.has_citekey("jones2022") is True

    def test_has_citekey_returns_false_for_missing(self, library_json_file: Path) -> None:
        """has_citekey should return False for missing citekey."""
        parser = LibraryJsonParser(library_json_file)

        assert parser.has_citekey("nonexistent") is False

    def test_list_citekeys_yields_all_keys(self, library_json_file: Path) -> None:
        """list_citekeys should yield all citekeys."""
        parser = LibraryJsonParser(library_json_file)

        keys = set(parser.list_citekeys())

        assert keys == {"smith2023", "jones2022"}

    def test_lazy_loading(self, library_json_file: Path) -> None:
        """Parser should not load until first access."""
        parser = LibraryJsonParser(library_json_file)

        # Not loaded yet
        assert parser._index is None

        # Triggers load
        _ = parser.get_metadata("smith2023")

        # Now loaded
        assert parser._index is not None

    def test_refresh_clears_cache(self, library_json_file: Path) -> None:
        """refresh should clear the cache for reload on next access."""
        parser = LibraryJsonParser(library_json_file)

        # Load data
        _ = parser.get_metadata("smith2023")
        assert parser._index is not None

        # Refresh
        parser.refresh()
        assert parser._index is None

        # Access triggers reload
        _ = parser.get_metadata("smith2023")
        assert parser._index is not None

    def test_raises_error_for_missing_file(self, temp_dir: Path) -> None:
        """Parser should raise error if library.json doesn't exist."""
        missing_path = temp_dir / "nonexistent.json"

        with pytest.raises(ZoteroError) as exc_info:
            LibraryJsonParser(missing_path)

        assert exc_info.value.code == ErrorCode.ZOTERO_LIBRARY_JSON_NOT_FOUND
        assert "nonexistent.json" in str(exc_info.value)

    def test_raises_error_for_invalid_json(self, temp_dir: Path) -> None:
        """Parser should raise error for malformed JSON."""
        bad_json = temp_dir / "bad.json"
        bad_json.write_text("{ not valid json }", encoding="utf-8")

        parser = LibraryJsonParser(bad_json)

        with pytest.raises(ZoteroError) as exc_info:
            parser.get_metadata("anything")

        assert exc_info.value.code == ErrorCode.ZOTERO_LIBRARY_JSON_PARSE_ERROR

    def test_raises_error_for_non_array_json(self, temp_dir: Path) -> None:
        """Parser should raise error if JSON is not an array."""
        object_json = temp_dir / "object.json"
        object_json.write_text('{"not": "an array"}', encoding="utf-8")

        parser = LibraryJsonParser(object_json)

        with pytest.raises(ZoteroError) as exc_info:
            parser.get_metadata("anything")

        assert exc_info.value.code == ErrorCode.ZOTERO_LIBRARY_JSON_PARSE_ERROR
        assert "array" in str(exc_info.value).lower()

    def test_handles_items_without_citation_key(self, temp_dir: Path) -> None:
        """Parser should use 'id' field if 'citation-key' is missing."""
        items = [
            {
                "id": "fallback-id",
                "type": "article",
                "title": "No Citation Key",
            }
        ]
        json_file = temp_dir / "library.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(items, f)

        parser = LibraryJsonParser(json_file)

        # Should find by 'id' field
        metadata = parser.get_metadata("fallback-id")
        assert metadata is not None
        assert metadata["title"] == "No Citation Key"

    def test_handles_empty_library(self, temp_dir: Path) -> None:
        """Parser should handle empty library array."""
        empty_json = temp_dir / "empty.json"
        empty_json.write_text("[]", encoding="utf-8")

        parser = LibraryJsonParser(empty_json)

        assert parser.has_citekey("anything") is False
        assert list(parser.list_citekeys()) == []


class TestDatabaseManager:
    """Tests for DatabaseManager class."""

    @pytest.fixture
    def zotero_dir(self, temp_dir: Path) -> Path:
        """Create a mock Zotero directory with test databases."""
        # Create directory structure
        zotero_path = temp_dir / "Zotero"
        zotero_path.mkdir()

        # Create minimal zotero.sqlite
        zotero_db = zotero_path / "zotero.sqlite"
        conn = sqlite3.connect(zotero_db)
        conn.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO items (itemID) VALUES (1)")
        conn.commit()
        conn.close()

        # Create minimal better-bibtex.sqlite
        bbt_db = zotero_path / "better-bibtex.sqlite"
        conn = sqlite3.connect(bbt_db)
        conn.execute("CREATE TABLE citationkey (itemID INTEGER, citationKey TEXT)")
        conn.execute("INSERT INTO citationkey VALUES (1, 'smith2023')")
        conn.commit()
        conn.close()

        return zotero_path

    def test_get_connection_returns_readonly_connection(self, zotero_dir: Path) -> None:
        """get_connection should return a readable connection."""
        manager = DatabaseManager(zotero_dir)

        try:
            conn = manager.get_connection("zotero.sqlite")

            # Should be able to read
            cursor = conn.execute("SELECT itemID FROM items")
            rows = cursor.fetchall()
            assert len(rows) == 1
            assert rows[0]["itemID"] == 1
        finally:
            manager.close()

    def test_connection_is_cached(self, zotero_dir: Path) -> None:
        """get_connection should return cached connection on subsequent calls."""
        manager = DatabaseManager(zotero_dir)

        try:
            conn1 = manager.get_connection("zotero.sqlite")
            conn2 = manager.get_connection("zotero.sqlite")

            assert conn1 is conn2
        finally:
            manager.close()

    def test_can_access_both_databases(self, zotero_dir: Path) -> None:
        """Manager should provide access to both Zotero and BBT databases."""
        manager = DatabaseManager(zotero_dir)

        try:
            zotero_conn = manager.get_connection("zotero.sqlite")
            bbt_conn = manager.get_connection("better-bibtex.sqlite")

            # Verify we can read from both
            zotero_rows = zotero_conn.execute("SELECT * FROM items").fetchall()
            bbt_rows = bbt_conn.execute("SELECT * FROM citationkey").fetchall()

            assert len(zotero_rows) == 1
            assert len(bbt_rows) == 1
        finally:
            manager.close()

    def test_close_clears_connections(self, zotero_dir: Path) -> None:
        """close should clear all cached connections."""
        manager = DatabaseManager(zotero_dir)

        _ = manager.get_connection("zotero.sqlite")
        assert len(manager._connections) == 1

        manager.close()

        assert len(manager._connections) == 0

    def test_row_factory_enables_column_access(self, zotero_dir: Path) -> None:
        """Connections should use Row factory for column name access."""
        manager = DatabaseManager(zotero_dir)

        try:
            conn = manager.get_connection("zotero.sqlite")
            cursor = conn.execute("SELECT itemID FROM items")
            row = cursor.fetchone()

            # Should be able to access by column name
            assert row["itemID"] == 1
        finally:
            manager.close()

    def test_raises_error_for_missing_directory(self, temp_dir: Path) -> None:
        """Manager should raise error if Zotero directory doesn't exist."""
        missing_dir = temp_dir / "nonexistent"

        with pytest.raises(ZoteroError) as exc_info:
            DatabaseManager(missing_dir)

        assert exc_info.value.code == ErrorCode.ZOTERO_DIR_NOT_FOUND

    def test_raises_error_for_missing_database(self, zotero_dir: Path) -> None:
        """Manager should raise error if requested database doesn't exist."""
        manager = DatabaseManager(zotero_dir)

        try:
            with pytest.raises(ZoteroError) as exc_info:
                manager.get_connection("nonexistent.sqlite")

            assert exc_info.value.code == ErrorCode.ZOTERO_DATABASE_NOT_FOUND
        finally:
            manager.close()

    def test_copy_if_locked_creates_temp_copy(self, zotero_dir: Path) -> None:
        """Manager should copy database to temp if locked."""
        from unittest.mock import patch

        manager = DatabaseManager(zotero_dir)

        # Mock _open_readonly to raise LOCKED error on first call (original),
        # then succeed on second call (temp copy)
        call_count = 0
        original_open_readonly = manager._open_readonly

        def mock_open_readonly(db_path):
            nonlocal call_count
            call_count += 1
            is_original = (
                call_count == 1
                and "zotero.sqlite" in str(db_path)
                and "zotero_reader_" not in str(db_path)
            )
            if is_original:
                # First call to original database - simulate locked
                raise ZoteroError(
                    message=f"database is locked: {db_path}",
                    code=ErrorCode.ZOTERO_DATABASE_LOCKED,
                    details={"path": str(db_path)},
                )
            # Second call or other databases - use real implementation
            return original_open_readonly(db_path)

        with patch.object(manager, "_open_readonly", side_effect=mock_open_readonly):
            conn = manager.get_connection("zotero.sqlite")

            # Temp copy should have been created
            assert len(manager._temp_copies) == 1

            # Should be able to read from copy
            cursor = conn.execute("SELECT itemID FROM items")
            rows = cursor.fetchall()
            assert len(rows) == 1

        manager.close()

    def test_custom_temp_dir_is_used(self, zotero_dir: Path, temp_dir: Path) -> None:
        """Manager should use provided temp_dir for copies."""
        from unittest.mock import patch

        custom_temp = temp_dir / "custom_temp"
        custom_temp.mkdir()
        manager = DatabaseManager(zotero_dir, temp_dir=custom_temp)

        # Mock _open_readonly to raise LOCKED error on first call
        call_count = 0
        original_open_readonly = manager._open_readonly

        def mock_open_readonly(db_path):
            nonlocal call_count
            call_count += 1
            is_original = (
                call_count == 1
                and "zotero.sqlite" in str(db_path)
                and str(custom_temp) not in str(db_path)
            )
            if is_original:
                # First call to original database - simulate locked
                raise ZoteroError(
                    message=f"database is locked: {db_path}",
                    code=ErrorCode.ZOTERO_DATABASE_LOCKED,
                    details={"path": str(db_path)},
                )
            # Second call (temp copy) - use real implementation
            return original_open_readonly(db_path)

        with patch.object(manager, "_open_readonly", side_effect=mock_open_readonly):
            _ = manager.get_connection("zotero.sqlite")

            # Check copy is in custom temp dir
            assert len(manager._temp_copies) == 1
            assert manager._temp_copies[0].parent == custom_temp

            # Verify it's in the custom temp directory
            assert manager._temp_copies[0].exists()

        manager.close()

    def test_close_removes_temp_copies(self, zotero_dir: Path) -> None:
        """close should remove temporary database copies."""
        from unittest.mock import patch

        manager = DatabaseManager(zotero_dir)

        # Mock _open_readonly to raise LOCKED error on first call
        call_count = 0
        original_open_readonly = manager._open_readonly

        def mock_open_readonly(db_path):
            nonlocal call_count
            call_count += 1
            is_original = (
                call_count == 1
                and "zotero.sqlite" in str(db_path)
                and "zotero_reader_" not in str(db_path)
            )
            if is_original:
                # First call to original database - simulate locked
                raise ZoteroError(
                    message=f"database is locked: {db_path}",
                    code=ErrorCode.ZOTERO_DATABASE_LOCKED,
                    details={"path": str(db_path)},
                )
            # Second call (temp copy) - use real implementation
            return original_open_readonly(db_path)

        with patch.object(manager, "_open_readonly", side_effect=mock_open_readonly):
            _ = manager.get_connection("zotero.sqlite")
            temp_path = manager._temp_copies[0]
            assert temp_path.exists()

            manager.close()

            # Temp copy should be removed
            assert not temp_path.exists()


class TestBbtKeyMapper:
    """Tests for BbtKeyMapper class."""

    @pytest.fixture
    def zotero_dir_with_citekeys(self, temp_dir: Path) -> Path:
        """Create mock Zotero directory with BBT citekey data."""
        zotero_path = temp_dir / "Zotero"
        zotero_path.mkdir()

        # Create zotero.sqlite with items table
        zotero_db = zotero_path / "zotero.sqlite"
        conn = sqlite3.connect(zotero_db)
        conn.execute("""
            CREATE TABLE items (
                itemID INTEGER PRIMARY KEY,
                key TEXT NOT NULL
            )
        """)
        conn.execute("INSERT INTO items (itemID, key) VALUES (100, 'SMITH001')")
        conn.execute("INSERT INTO items (itemID, key) VALUES (200, 'JONES002')")
        conn.execute("INSERT INTO items (itemID, key) VALUES (300, 'BROWN003')")
        conn.commit()
        conn.close()

        # Create better-bibtex.sqlite with citationkey table
        bbt_db = zotero_path / "better-bibtex.sqlite"
        conn = sqlite3.connect(bbt_db)
        conn.execute("""
            CREATE TABLE citationkey (
                itemID INTEGER PRIMARY KEY,
                citationKey TEXT NOT NULL
            )
        """)
        conn.execute("INSERT INTO citationkey VALUES (100, 'smith2023')")
        conn.execute("INSERT INTO citationkey VALUES (200, 'jones2022')")
        # Note: itemID 300 has no citekey in BBT
        conn.commit()
        conn.close()

        return zotero_path

    @pytest.fixture
    def db_manager(self, zotero_dir_with_citekeys: Path) -> DatabaseManager:
        """Provide DatabaseManager for tests."""
        manager = DatabaseManager(zotero_dir_with_citekeys)
        yield manager
        manager.close()

    def test_lookup_returns_item_ids(self, db_manager: DatabaseManager) -> None:
        """lookup should return (itemID, itemKey) tuple."""
        mapper = BbtKeyMapper(db_manager)

        item_id, item_key = mapper.lookup("smith2023")

        assert item_id == 100
        assert item_key == "SMITH001"

    def test_lookup_different_citekey(self, db_manager: DatabaseManager) -> None:
        """lookup should work for different citekeys."""
        mapper = BbtKeyMapper(db_manager)

        item_id, item_key = mapper.lookup("jones2022")

        assert item_id == 200
        assert item_key == "JONES002"

    def test_has_citekey_returns_true_for_existing(self, db_manager: DatabaseManager) -> None:
        """has_citekey should return True for existing citekey."""
        mapper = BbtKeyMapper(db_manager)

        assert mapper.has_citekey("smith2023") is True
        assert mapper.has_citekey("jones2022") is True

    def test_has_citekey_returns_false_for_missing(self, db_manager: DatabaseManager) -> None:
        """has_citekey should return False for missing citekey."""
        mapper = BbtKeyMapper(db_manager)

        assert mapper.has_citekey("nonexistent") is False

    def test_lookup_raises_for_missing_citekey(self, db_manager: DatabaseManager) -> None:
        """lookup should raise error for citekey not in BBT."""
        mapper = BbtKeyMapper(db_manager)

        with pytest.raises(ZoteroError) as exc_info:
            mapper.lookup("nonexistent")

        assert exc_info.value.code == ErrorCode.ZOTERO_CITEKEY_NOT_IN_BBT
        assert "nonexistent" in str(exc_info.value)

    def test_lookup_raises_for_orphaned_bbt_entry(self, temp_dir: Path) -> None:
        """lookup should raise if BBT entry points to missing Zotero item."""
        # Create Zotero dir with mismatched data
        zotero_path = temp_dir / "ZoteroOrphan"
        zotero_path.mkdir()

        # Zotero DB without itemID 999
        zotero_db = zotero_path / "zotero.sqlite"
        conn = sqlite3.connect(zotero_db)
        conn.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT)")
        conn.execute("INSERT INTO items VALUES (1, 'REAL0001')")
        conn.commit()
        conn.close()

        # BBT DB with orphaned reference to itemID 999
        bbt_db = zotero_path / "better-bibtex.sqlite"
        conn = sqlite3.connect(bbt_db)
        conn.execute("CREATE TABLE citationkey (itemID INTEGER, citationKey TEXT)")
        conn.execute("INSERT INTO citationkey VALUES (999, 'orphan2023')")
        conn.commit()
        conn.close()

        manager = DatabaseManager(zotero_path)
        mapper = BbtKeyMapper(manager)

        try:
            with pytest.raises(ZoteroError) as exc_info:
                mapper.lookup("orphan2023")

            assert exc_info.value.code == ErrorCode.ZOTERO_ITEM_NOT_FOUND
        finally:
            manager.close()

    def test_lookup_is_case_sensitive(self, db_manager: DatabaseManager) -> None:
        """Citekey lookup should be case-sensitive."""
        mapper = BbtKeyMapper(db_manager)

        # smith2023 exists, SMITH2023 does not
        assert mapper.has_citekey("smith2023") is True
        assert mapper.has_citekey("SMITH2023") is False
        assert mapper.has_citekey("Smith2023") is False


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
                parentItemID INTEGER,
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
    def db_manager_attachments(self, zotero_dir_with_attachments: Path) -> DatabaseManager:
        """Provide DatabaseManager for attachment tests."""
        manager = DatabaseManager(zotero_dir_with_attachments)
        yield manager
        manager.close()

    def test_get_attachments_returns_all(
        self, db_manager_attachments: DatabaseManager, zotero_dir_with_attachments: Path
    ) -> None:
        """get_attachments should return all attachments for an item."""
        resolver = AttachmentResolver(db_manager_attachments, zotero_dir_with_attachments)

        attachments = resolver.get_attachments(100)

        assert len(attachments) == 3

    def test_attachment_paths_resolved_correctly(
        self, db_manager_attachments: DatabaseManager, zotero_dir_with_attachments: Path
    ) -> None:
        """Attachment paths should be resolved to filesystem paths."""
        resolver = AttachmentResolver(db_manager_attachments, zotero_dir_with_attachments)

        attachments = resolver.get_attachments(100)
        pdf_attachment = next(a for a in attachments if a.filename == "paper.pdf")

        expected_path = zotero_dir_with_attachments / "storage" / "ATTACH01" / "paper.pdf"
        assert pdf_attachment.path == expected_path
        assert pdf_attachment.path.exists()

    def test_attachment_metadata_populated(
        self, db_manager_attachments: DatabaseManager, zotero_dir_with_attachments: Path
    ) -> None:
        """Attachment objects should have correct metadata."""
        resolver = AttachmentResolver(db_manager_attachments, zotero_dir_with_attachments)

        attachments = resolver.get_attachments(100)
        pdf_attachment = next(a for a in attachments if a.filename == "paper.pdf")

        assert pdf_attachment.content_type == "application/pdf"
        assert pdf_attachment.attachment_key == "ATTACH01"
        assert pdf_attachment.link_mode == 0

    def test_returns_empty_tuple_for_no_attachments(
        self, db_manager_attachments: DatabaseManager, zotero_dir_with_attachments: Path
    ) -> None:
        """get_attachments should return empty tuple for items without attachments."""
        resolver = AttachmentResolver(db_manager_attachments, zotero_dir_with_attachments)

        # Item 999 doesn't exist
        attachments = resolver.get_attachments(999)

        assert attachments == ()

    def test_attachments_are_immutable_tuple(
        self, db_manager_attachments: DatabaseManager, zotero_dir_with_attachments: Path
    ) -> None:
        """get_attachments should return immutable tuple."""
        resolver = AttachmentResolver(db_manager_attachments, zotero_dir_with_attachments)

        attachments = resolver.get_attachments(100)

        assert isinstance(attachments, tuple)

    def test_validation_passes_when_files_exist(
        self, db_manager_attachments: DatabaseManager, zotero_dir_with_attachments: Path
    ) -> None:
        """get_attachments_with_validation should pass when files exist."""
        resolver = AttachmentResolver(db_manager_attachments, zotero_dir_with_attachments)

        # Should not raise
        attachments = resolver.get_attachments_with_validation(100, require_exists=True)

        assert len(attachments) == 3

    def test_validation_raises_for_missing_file(
        self, db_manager_attachments: DatabaseManager, zotero_dir_with_attachments: Path
    ) -> None:
        """get_attachments_with_validation should raise for missing files."""
        resolver = AttachmentResolver(db_manager_attachments, zotero_dir_with_attachments)

        # Delete one attachment file
        missing_file = zotero_dir_with_attachments / "storage" / "ATTACH01" / "paper.pdf"
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
                itemID INTEGER, parentItemID INTEGER,
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
                itemID INTEGER, parentItemID INTEGER,
                linkMode INTEGER, contentType TEXT, path TEXT
            )
        """)
        # Attachment with NULL path (e.g., embedded note or URL-only)
        conn.execute("INSERT INTO itemAttachments VALUES (301, 300, 2, 'text/html', NULL)")
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

        resolver = AttachmentResolver(db_manager_attachments, zotero_dir_with_attachments)

        attachments = resolver.get_attachments(100)
        unknown_att = next((a for a in attachments if a.filename == "unknown.dat"), None)

        assert unknown_att is not None
        assert unknown_att.content_type == "application/octet-stream"


class TestZoteroReader:
    """Tests for ZoteroReader public API."""

    @pytest.fixture
    def complete_zotero_dir(self, temp_dir: Path) -> Path:
        """Create a complete mock Zotero directory with all required data."""
        zotero_path = temp_dir / "Zotero"
        zotero_path.mkdir()

        # Create library.json (CSL-JSON export)
        library_json = [
            {
                "id": "smith2023",
                "citation-key": "smith2023",
                "type": "article-journal",
                "title": "A Sample Paper",
                "author": [{"family": "Smith", "given": "John"}],
                "issued": {"date-parts": [[2023]]},
            },
            {
                "id": "jones2022",
                "citation-key": "jones2022",
                "type": "book",
                "title": "A Sample Book",
                "author": [{"family": "Jones", "given": "Jane"}],
            },
        ]
        with open(zotero_path / "library.json", "w") as f:
            json.dump(library_json, f)

        # Create zotero.sqlite
        zotero_db = zotero_path / "zotero.sqlite"
        conn = sqlite3.connect(zotero_db)
        conn.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT)")
        conn.execute("INSERT INTO items VALUES (100, 'SMITH001')")  # Parent
        conn.execute("INSERT INTO items VALUES (101, 'ATTACH01')")  # Attachment
        conn.execute("INSERT INTO items VALUES (200, 'JONES001')")  # Parent (no att)
        conn.execute("""
            CREATE TABLE itemAttachments (
                itemID INTEGER, parentItemID INTEGER,
                linkMode INTEGER, contentType TEXT, path TEXT
            )
        """)
        conn.execute("""
            INSERT INTO itemAttachments VALUES
            (101, 100, 0, 'application/pdf', 'storage:paper.pdf')
        """)
        conn.commit()
        conn.close()

        # Create better-bibtex.sqlite
        bbt_db = zotero_path / "better-bibtex.sqlite"
        conn = sqlite3.connect(bbt_db)
        conn.execute("CREATE TABLE citationkey (itemID INTEGER, citationKey TEXT)")
        conn.execute("INSERT INTO citationkey VALUES (100, 'smith2023')")
        conn.execute("INSERT INTO citationkey VALUES (200, 'jones2022')")
        conn.commit()
        conn.close()

        # Create storage with attachment file
        storage_dir = zotero_path / "storage" / "ATTACH01"
        storage_dir.mkdir(parents=True)
        (storage_dir / "paper.pdf").write_bytes(b"%PDF-1.4 test content")

        return zotero_path

    def test_get_item_returns_complete_item(self, complete_zotero_dir: Path) -> None:
        """get_item should return ZoteroItem with metadata and attachments."""
        with ZoteroReader(complete_zotero_dir) as reader:
            item = reader.get_item("smith2023")

        assert item.citekey == "smith2023"
        assert item.csl_json["title"] == "A Sample Paper"
        assert item.zotero_key == "SMITH001"
        assert item.item_id == 100
        assert len(item.attachments) == 1
        assert item.attachments[0].content_type == "application/pdf"

    def test_get_item_without_attachments(self, complete_zotero_dir: Path) -> None:
        """get_item should work for items without attachments."""
        with ZoteroReader(complete_zotero_dir) as reader:
            item = reader.get_item("jones2022")

        assert item.citekey == "jones2022"
        assert item.csl_json["title"] == "A Sample Book"
        assert len(item.attachments) == 0

    def test_list_citekeys_returns_all(self, complete_zotero_dir: Path) -> None:
        """list_citekeys should yield all citekeys from library.json."""
        with ZoteroReader(complete_zotero_dir) as reader:
            keys = set(reader.list_citekeys())

        assert keys == {"smith2023", "jones2022"}

    def test_has_item_returns_true_for_existing(self, complete_zotero_dir: Path) -> None:
        """has_item should return True for existing citekeys."""
        with ZoteroReader(complete_zotero_dir) as reader:
            assert reader.has_item("smith2023") is True
            assert reader.has_item("jones2022") is True

    def test_has_item_returns_false_for_missing(self, complete_zotero_dir: Path) -> None:
        """has_item should return False for missing citekeys."""
        with ZoteroReader(complete_zotero_dir) as reader:
            assert reader.has_item("nonexistent") is False

    def test_context_manager_cleanup(self, complete_zotero_dir: Path) -> None:
        """Context manager should close connections on exit."""
        reader = ZoteroReader(complete_zotero_dir)
        reader.__enter__()

        # Access something to open connections
        _ = reader.get_item("smith2023")
        assert len(reader._db_manager._connections) > 0

        reader.__exit__(None, None, None)

        # Connections should be closed
        assert len(reader._db_manager._connections) == 0

    def test_raises_for_missing_zotero_dir(self, temp_dir: Path) -> None:
        """ZoteroReader should raise error if Zotero directory missing."""
        missing_dir = temp_dir / "nonexistent"

        with pytest.raises(ZoteroError) as exc_info:
            ZoteroReader(missing_dir)

        assert exc_info.value.code == ErrorCode.ZOTERO_DIR_NOT_FOUND

    def test_raises_for_missing_library_json(self, temp_dir: Path) -> None:
        """ZoteroReader should raise error if library.json missing."""
        zotero_dir = temp_dir / "ZoteroNoJson"
        zotero_dir.mkdir()

        # Create databases but no library.json
        (zotero_dir / "zotero.sqlite").touch()
        (zotero_dir / "better-bibtex.sqlite").touch()

        with pytest.raises(ZoteroError) as exc_info:
            ZoteroReader(zotero_dir)

        assert exc_info.value.code == ErrorCode.ZOTERO_LIBRARY_JSON_NOT_FOUND

    def test_get_item_raises_for_unknown_citekey(self, complete_zotero_dir: Path) -> None:
        """get_item should raise error for citekey not in library.json."""
        with ZoteroReader(complete_zotero_dir) as reader:
            with pytest.raises(ZoteroError) as exc_info:
                reader.get_item("nonexistent")

        assert exc_info.value.code == ErrorCode.ZOTERO_ITEM_NOT_FOUND

    def test_get_item_raises_for_citekey_not_in_bbt(self, complete_zotero_dir: Path) -> None:
        """get_item should raise error if citekey in JSON but not BBT database."""
        # Add citekey to library.json but not to BBT database
        library_json_path = complete_zotero_dir / "library.json"
        with open(library_json_path) as f:
            items = json.load(f)
        items.append(
            {
                "id": "orphan2023",
                "citation-key": "orphan2023",
                "type": "article",
                "title": "Orphaned Item",
            }
        )
        with open(library_json_path, "w") as f:
            json.dump(items, f)

        with ZoteroReader(complete_zotero_dir) as reader:
            # Force reload to pick up new item
            reader.refresh()

            with pytest.raises(ZoteroError) as exc_info:
                reader.get_item("orphan2023")

        assert exc_info.value.code == ErrorCode.ZOTERO_CITEKEY_NOT_IN_BBT

    def test_custom_library_json_path(self, complete_zotero_dir: Path) -> None:
        """ZoteroReader should accept custom library.json path."""
        # Move library.json to custom location
        custom_path = complete_zotero_dir / "exports" / "my_library.json"
        custom_path.parent.mkdir()
        (complete_zotero_dir / "library.json").rename(custom_path)

        with ZoteroReader(complete_zotero_dir, library_json_path=custom_path) as reader:
            assert reader.has_item("smith2023") is True

    def test_refresh_reloads_library_json(self, complete_zotero_dir: Path) -> None:
        """refresh should reload library.json from disk."""
        with ZoteroReader(complete_zotero_dir) as reader:
            # Initial state
            assert reader.has_item("new2024") is False

            # Add new item to library.json
            library_json_path = complete_zotero_dir / "library.json"
            with open(library_json_path) as f:
                items = json.load(f)
            items.append(
                {
                    "id": "new2024",
                    "citation-key": "new2024",
                    "type": "article",
                    "title": "New Item",
                }
            )
            with open(library_json_path, "w") as f:
                json.dump(items, f)

            # Still cached - not visible
            assert reader.has_item("new2024") is False

            # After refresh - visible
            reader.refresh()
            assert reader.has_item("new2024") is True


class TestZoteroCollection:
    """Tests for ZoteroCollection dataclass."""

    def test_creates_frozen_dataclass(self) -> None:
        """ZoteroCollection should be immutable."""
        collection = ZoteroCollection(
            collection_id=1,
            name="My Collection",
            key="COLL0001",
            parent_id=None,
            library_id=1,
        )

        with pytest.raises(AttributeError):
            collection.name = "Other"  # type: ignore[misc]

    def test_is_top_level_true_for_no_parent(self) -> None:
        """is_top_level should return True when parent_id is None."""
        collection = ZoteroCollection(
            collection_id=1,
            name="Top Level",
            key="TOP00001",
            parent_id=None,
            library_id=1,
        )

        assert collection.is_top_level() is True

    def test_is_top_level_false_for_nested(self) -> None:
        """is_top_level should return False when parent_id is set."""
        collection = ZoteroCollection(
            collection_id=2,
            name="Nested",
            key="NEST0001",
            parent_id=1,
            library_id=1,
        )

        assert collection.is_top_level() is False


class TestCollectionResolver:
    """Tests for CollectionResolver database queries."""

    @pytest.fixture
    def temp_dir(self, tmp_path: Path) -> Path:
        """Provide a temporary directory for test files."""
        return tmp_path

    @pytest.fixture
    def zotero_dir_with_collections(self, temp_dir: Path) -> Path:
        """Create mock Zotero directory with collection data."""
        zotero_path = temp_dir / "Zotero"
        zotero_path.mkdir()

        # Create zotero.sqlite with collections and items
        zotero_db = zotero_path / "zotero.sqlite"
        conn = sqlite3.connect(zotero_db)

        # Items table
        conn.execute("""
            CREATE TABLE items (
                itemID INTEGER PRIMARY KEY,
                key TEXT NOT NULL
            )
        """)
        conn.execute("INSERT INTO items (itemID, key) VALUES (100, 'ITEM0001')")
        conn.execute("INSERT INTO items (itemID, key) VALUES (200, 'ITEM0002')")
        conn.execute("INSERT INTO items (itemID, key) VALUES (300, 'ITEM0003')")

        # Collections table
        conn.execute("""
            CREATE TABLE collections (
                collectionID INTEGER PRIMARY KEY,
                collectionName TEXT NOT NULL,
                parentCollectionID INTEGER,
                key TEXT NOT NULL,
                libraryID INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("INSERT INTO collections VALUES (1, 'Research Papers', NULL, 'COLL0001', 1)")
        conn.execute("INSERT INTO collections VALUES (2, 'Books', NULL, 'COLL0002', 1)")
        conn.execute("INSERT INTO collections VALUES (3, 'ML Papers', 1, 'COLL0003', 1)")

        # collectionItems junction table
        conn.execute("""
            CREATE TABLE collectionItems (
                collectionID INTEGER,
                itemID INTEGER,
                PRIMARY KEY (collectionID, itemID)
            )
        """)
        # Research Papers has items 100 and 200
        conn.execute("INSERT INTO collectionItems VALUES (1, 100)")
        conn.execute("INSERT INTO collectionItems VALUES (1, 200)")
        # Books has item 300
        conn.execute("INSERT INTO collectionItems VALUES (2, 300)")
        # ML Papers (nested) has item 200
        conn.execute("INSERT INTO collectionItems VALUES (3, 200)")

        conn.commit()
        conn.close()

        # Create better-bibtex.sqlite with citekey mappings
        bbt_db = zotero_path / "better-bibtex.sqlite"
        conn = sqlite3.connect(bbt_db)
        conn.execute("""
            CREATE TABLE citationkey (
                itemID INTEGER PRIMARY KEY,
                citationKey TEXT NOT NULL
            )
        """)
        conn.execute("INSERT INTO citationkey VALUES (100, 'smith2023')")
        conn.execute("INSERT INTO citationkey VALUES (200, 'jones2022')")
        conn.execute("INSERT INTO citationkey VALUES (300, 'brown2021')")
        conn.commit()
        conn.close()

        return zotero_path

    @pytest.fixture
    def collection_resolver(self, zotero_dir_with_collections: Path) -> CollectionResolver:
        """Provide CollectionResolver for tests."""
        db_manager = DatabaseManager(zotero_dir_with_collections)
        key_mapper = BbtKeyMapper(db_manager)
        resolver = CollectionResolver(db_manager, key_mapper)
        yield resolver
        db_manager.close()

    def test_list_collections_returns_all(self, collection_resolver: CollectionResolver) -> None:
        """list_collections should return all collections."""
        collections = collection_resolver.list_collections()

        assert len(collections) == 3
        names = [c.name for c in collections]
        assert "Research Papers" in names
        assert "Books" in names
        assert "ML Papers" in names

    def test_list_collections_sorted_by_name(self, collection_resolver: CollectionResolver) -> None:
        """list_collections should return collections sorted by name."""
        collections = collection_resolver.list_collections()

        names = [c.name for c in collections]
        assert names == sorted(names, key=str.lower)

    def test_get_collection_returns_correct_data(
        self, collection_resolver: CollectionResolver
    ) -> None:
        """get_collection should return correct collection data."""
        collection = collection_resolver.get_collection("Research Papers")

        assert collection.collection_id == 1
        assert collection.name == "Research Papers"
        assert collection.key == "COLL0001"
        assert collection.parent_id is None

    def test_get_collection_raises_for_unknown(
        self, collection_resolver: CollectionResolver
    ) -> None:
        """get_collection should raise error for unknown collection."""
        with pytest.raises(ZoteroError) as exc_info:
            collection_resolver.get_collection("Nonexistent")

        assert exc_info.value.code == ErrorCode.ZOTERO_COLLECTION_NOT_FOUND

    def test_get_item_ids_in_collection(self, collection_resolver: CollectionResolver) -> None:
        """get_item_ids_in_collection should return correct item IDs."""
        item_ids = collection_resolver.get_item_ids_in_collection(1)

        assert set(item_ids) == {100, 200}

    def test_get_citekeys_in_collection(self, collection_resolver: CollectionResolver) -> None:
        """get_citekeys_in_collection should return citekeys for items."""
        citekeys = list(collection_resolver.get_citekeys_in_collection("Research Papers"))

        assert set(citekeys) == {"smith2023", "jones2022"}

    def test_get_citekeys_in_nested_collection(
        self, collection_resolver: CollectionResolver
    ) -> None:
        """get_citekeys_in_collection should work for nested collections."""
        citekeys = list(collection_resolver.get_citekeys_in_collection("ML Papers"))

        assert citekeys == ["jones2022"]

    def test_empty_collection_returns_empty_list(self, zotero_dir_with_collections: Path) -> None:
        """Empty collection should return empty citekey list."""
        # Add empty collection
        zotero_db = zotero_dir_with_collections / "zotero.sqlite"
        conn = sqlite3.connect(zotero_db)
        conn.execute("INSERT INTO collections VALUES (4, 'Empty Collection', NULL, 'COLL0004', 1)")
        conn.commit()
        conn.close()

        db_manager = DatabaseManager(zotero_dir_with_collections)
        key_mapper = BbtKeyMapper(db_manager)
        resolver = CollectionResolver(db_manager, key_mapper)

        try:
            citekeys = list(resolver.get_citekeys_in_collection("Empty Collection"))
            assert citekeys == []
        finally:
            db_manager.close()


class TestZoteroReaderCollections:
    """Tests for ZoteroReader collection methods."""

    @pytest.fixture
    def temp_dir(self, tmp_path: Path) -> Path:
        """Provide a temporary directory for test files."""
        return tmp_path

    @pytest.fixture
    def complete_zotero_dir_with_collections(self, temp_dir: Path) -> Path:
        """Create complete Zotero directory with collections."""
        zotero_path = temp_dir / "Zotero"
        zotero_path.mkdir()

        # Create library.json
        library_json = [
            {
                "id": "smith2023",
                "citation-key": "smith2023",
                "type": "article-journal",
                "title": "A Sample Paper",
            },
            {
                "id": "jones2022",
                "citation-key": "jones2022",
                "type": "book",
                "title": "A Sample Book",
            },
        ]
        with open(zotero_path / "library.json", "w") as f:
            json.dump(library_json, f)

        # Create zotero.sqlite
        zotero_db = zotero_path / "zotero.sqlite"
        conn = sqlite3.connect(zotero_db)

        conn.execute("CREATE TABLE items (itemID INTEGER PRIMARY KEY, key TEXT)")
        conn.execute("INSERT INTO items VALUES (100, 'ITEM0001')")
        conn.execute("INSERT INTO items VALUES (200, 'ITEM0002')")

        conn.execute("""
            CREATE TABLE collections (
                collectionID INTEGER PRIMARY KEY,
                collectionName TEXT NOT NULL,
                parentCollectionID INTEGER,
                key TEXT NOT NULL,
                libraryID INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("INSERT INTO collections VALUES (1, 'Papers', NULL, 'COLL0001', 1)")
        conn.execute("INSERT INTO collections VALUES (2, 'Books', NULL, 'COLL0002', 1)")

        conn.execute("""
            CREATE TABLE collectionItems (
                collectionID INTEGER,
                itemID INTEGER
            )
        """)
        conn.execute("INSERT INTO collectionItems VALUES (1, 100)")
        conn.execute("INSERT INTO collectionItems VALUES (2, 200)")

        # Attachments table (empty - no attachments needed for collection tests)
        conn.execute("""
            CREATE TABLE itemAttachments (
                itemID INTEGER,
                parentItemID INTEGER,
                path TEXT,
                contentType TEXT,
                linkMode INTEGER
            )
        """)

        conn.commit()
        conn.close()

        # Create better-bibtex.sqlite
        bbt_db = zotero_path / "better-bibtex.sqlite"
        conn = sqlite3.connect(bbt_db)
        conn.execute("""
            CREATE TABLE citationkey (
                itemID INTEGER PRIMARY KEY,
                citationKey TEXT NOT NULL
            )
        """)
        conn.execute("INSERT INTO citationkey VALUES (100, 'smith2023')")
        conn.execute("INSERT INTO citationkey VALUES (200, 'jones2022')")
        conn.commit()
        conn.close()

        return zotero_path

    def test_list_collections_via_reader(self, complete_zotero_dir_with_collections: Path) -> None:
        """ZoteroReader.list_collections should expose collection listing."""
        with ZoteroReader(complete_zotero_dir_with_collections) as reader:
            collections = reader.list_collections()

        assert len(collections) == 2
        assert any(c.name == "Papers" for c in collections)
        assert any(c.name == "Books" for c in collections)

    def test_list_citekeys_in_collection_via_reader(
        self, complete_zotero_dir_with_collections: Path
    ) -> None:
        """ZoteroReader.list_citekeys_in_collection should filter by collection."""
        with ZoteroReader(complete_zotero_dir_with_collections) as reader:
            citekeys = list(reader.list_citekeys_in_collection("Papers"))

        assert citekeys == ["smith2023"]

    def test_list_citekeys_in_collection_raises_for_unknown(
        self, complete_zotero_dir_with_collections: Path
    ) -> None:
        """list_citekeys_in_collection should raise for unknown collection."""
        with ZoteroReader(complete_zotero_dir_with_collections) as reader:
            with pytest.raises(ZoteroError) as exc_info:
                list(reader.list_citekeys_in_collection("Nonexistent"))

        assert exc_info.value.code == ErrorCode.ZOTERO_COLLECTION_NOT_FOUND
