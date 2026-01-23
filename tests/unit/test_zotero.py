"""Unit tests for Zotero data models."""

from pathlib import Path

import pytest

from local_library.ingestion.zotero import ZoteroAttachment, ZoteroItem


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
