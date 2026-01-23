"""Unit tests for Zotero data models, parsers, and database access."""

import json
import sqlite3
from pathlib import Path

import pytest

from local_library.core.errors import ErrorCode, ZoteroError
from local_library.ingestion.zotero import (
    DatabaseManager,
    LibraryJsonParser,
    ZoteroAttachment,
    ZoteroItem,
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

    def test_get_connection_returns_readonly_connection(
        self, zotero_dir: Path
    ) -> None:
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
