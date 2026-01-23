# M4 Zotero Reader Implementation Plan

**Goal:** Implement read-only access to Zotero library data via a `ZoteroReader` class that coordinates CSL-JSON metadata, Better BibTeX citekey mapping, and attachment path resolution.

**Architecture:** ZoteroReader is a standalone class (not implementing ContentAcquirer) that serves as a data source for `Library.add()`. It reads from three sources: a pre-exported CSL-JSON file (`library.json`), Better BibTeX's SQLite database for citekey→itemID mapping, and Zotero's main SQLite database for attachment paths.

**Tech Stack:** Python 3.11+, sqlite3 (stdlib), frozen dataclasses, pytest

**Scope:** 6 phases from original design (all phases)

**Codebase verified:** 2025-01-22

---

## Phase 1: Data Model and Error Codes

**Goal:** Establish types and error infrastructure for Zotero integration.

**Codebase verification findings:**
- Existing ErrorCode enum in `src/local_library/core/errors.py:9-41` with string enum pattern
- Existing domain subclasses (AcquisitionError, LookupError, MetadataError, etc.) at lines 62-95
- Frozen dataclass pattern established in `src/local_library/core/models.py` with factory methods
- File pattern classification (`# pattern: Functional Core`) required per FCIS skill

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Add Zotero Error Codes

**Files:**
- Modify: `src/local_library/core/errors.py:41` (add after METADATA_CITEKEY_INVALID)

**Step 1: Add the new error codes to the ErrorCode enum**

Add the following after line 41 (after `METADATA_CITEKEY_INVALID`):

```python
    # Zotero integration errors
    ZOTERO_DIR_NOT_FOUND = "ZOTERO_DIR_NOT_FOUND"
    ZOTERO_DATABASE_NOT_FOUND = "ZOTERO_DATABASE_NOT_FOUND"
    ZOTERO_DATABASE_LOCKED = "ZOTERO_DATABASE_LOCKED"
    ZOTERO_DATABASE_ERROR = "ZOTERO_DATABASE_ERROR"
    ZOTERO_LIBRARY_JSON_NOT_FOUND = "ZOTERO_LIBRARY_JSON_NOT_FOUND"
    ZOTERO_LIBRARY_JSON_PARSE_ERROR = "ZOTERO_LIBRARY_JSON_PARSE_ERROR"
    ZOTERO_ITEM_NOT_FOUND = "ZOTERO_ITEM_NOT_FOUND"
    ZOTERO_CITEKEY_NOT_IN_BBT = "ZOTERO_CITEKEY_NOT_IN_BBT"
    ZOTERO_ATTACHMENT_MISSING = "ZOTERO_ATTACHMENT_MISSING"
```

**Step 2: Add the ZoteroError exception class**

Add the following after MetadataError class (after line 95):

```python
class ZoteroError(LocalLibraryError):
    """Error during Zotero data access."""

    pass
```

**Step 3: Run tests to verify no regressions**

Run: `uv run pytest tests/unit/test_errors.py -v`
Expected: All existing tests pass

**Step 4: Commit**

```bash
git add src/local_library/core/errors.py
git commit -m "$(cat <<'EOF'
feat(zotero): add error codes and exception class for Zotero integration

Adds ZOTERO_* error codes for directory/database access, JSON parsing,
item lookup, and attachment resolution. Adds ZoteroError exception class.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add Unit Tests for Zotero Error Codes

**Files:**
- Modify: `tests/unit/test_errors.py` (add test class for new codes)

**Step 1: Read the existing test file to understand the pattern**

First, check what's in `tests/unit/test_errors.py` to see testing patterns for error codes.

**Step 2: Add tests for Zotero error codes**

Add the following test class to the end of `tests/unit/test_errors.py`:

```python
class TestZoteroErrorCodes:
    """Tests for Zotero-specific error codes."""

    def test_zotero_error_codes_exist(self) -> None:
        """All Zotero error codes should be defined in ErrorCode enum."""
        assert ErrorCode.ZOTERO_DIR_NOT_FOUND.value == "ZOTERO_DIR_NOT_FOUND"
        assert ErrorCode.ZOTERO_DATABASE_NOT_FOUND.value == "ZOTERO_DATABASE_NOT_FOUND"
        assert ErrorCode.ZOTERO_DATABASE_LOCKED.value == "ZOTERO_DATABASE_LOCKED"
        assert ErrorCode.ZOTERO_DATABASE_ERROR.value == "ZOTERO_DATABASE_ERROR"
        assert ErrorCode.ZOTERO_LIBRARY_JSON_NOT_FOUND.value == "ZOTERO_LIBRARY_JSON_NOT_FOUND"
        assert ErrorCode.ZOTERO_LIBRARY_JSON_PARSE_ERROR.value == "ZOTERO_LIBRARY_JSON_PARSE_ERROR"
        assert ErrorCode.ZOTERO_ITEM_NOT_FOUND.value == "ZOTERO_ITEM_NOT_FOUND"
        assert ErrorCode.ZOTERO_CITEKEY_NOT_IN_BBT.value == "ZOTERO_CITEKEY_NOT_IN_BBT"
        assert ErrorCode.ZOTERO_ATTACHMENT_MISSING.value == "ZOTERO_ATTACHMENT_MISSING"

    def test_zotero_error_inherits_from_base(self) -> None:
        """ZoteroError should inherit from LocalLibraryError."""
        from local_library.core.errors import ZoteroError

        error = ZoteroError(
            message="zotero directory not found",
            code=ErrorCode.ZOTERO_DIR_NOT_FOUND,
            details={"path": "/nonexistent"},
        )

        assert isinstance(error, LocalLibraryError)
        assert error.code == ErrorCode.ZOTERO_DIR_NOT_FOUND
        assert error.details == {"path": "/nonexistent"}
        assert str(error) == "[ZOTERO_DIR_NOT_FOUND] zotero directory not found"
```

**Step 3: Run the tests**

Run: `uv run pytest tests/unit/test_errors.py::TestZoteroErrorCodes -v`
Expected: 2 tests pass

**Step 4: Commit**

```bash
git add tests/unit/test_errors.py
git commit -m "$(cat <<'EOF'
test(zotero): add unit tests for Zotero error codes

Tests that all ZOTERO_* error codes exist and that ZoteroError
properly inherits from LocalLibraryError.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-5) -->

<!-- START_TASK_3 -->
### Task 3: Create ZoteroAttachment Dataclass

**Files:**
- Create: `src/local_library/ingestion/zotero.py`

**Step 1: Create the new file with ZoteroAttachment dataclass**

Create `src/local_library/ingestion/zotero.py`:

```python
"""Zotero library data access.

Provides read-only access to Zotero library data by coordinating:
- CSL-JSON metadata from Better BibTeX export (library.json)
- Citekey-to-itemID mapping from Better BibTeX SQLite database
- Attachment paths from Zotero's main SQLite database
"""

# pattern: Functional Core (dataclasses only in this initial file)

from dataclasses import dataclass
from pathlib import Path


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
```

**Step 2: Verify the file is importable**

Run: `uv run python -c "from local_library.ingestion.zotero import ZoteroAttachment; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add src/local_library/ingestion/zotero.py
git commit -m "$(cat <<'EOF'
feat(zotero): add ZoteroAttachment frozen dataclass

Immutable dataclass representing a single attachment from a Zotero item.
Includes path, filename, content_type, attachment_key, and link_mode
with helper methods for common checks (is_pdf, is_imported, is_linked_file).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add ZoteroItem Dataclass

**Files:**
- Modify: `src/local_library/ingestion/zotero.py`

**Step 1: Add the ZoteroItem dataclass**

Add the following after ZoteroAttachment class in `src/local_library/ingestion/zotero.py`:

```python
from typing import Any


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
```

**Step 2: Update the import at the top of the file**

Ensure the import section includes `Any`:

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Any
```

**Step 3: Verify the file is importable**

Run: `uv run python -c "from local_library.ingestion.zotero import ZoteroItem, ZoteroAttachment; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add src/local_library/ingestion/zotero.py
git commit -m "$(cat <<'EOF'
feat(zotero): add ZoteroItem frozen dataclass

Immutable dataclass combining citekey, CSL-JSON metadata, and resolved
attachments. Includes helper methods for filtering PDFs and checking
attachment presence.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Add Unit Tests for Zotero Data Models

**Files:**
- Create: `tests/unit/test_zotero.py`

**Step 1: Create the test file**

Create `tests/unit/test_zotero.py`:

```python
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
```

**Step 2: Run the tests**

Run: `uv run pytest tests/unit/test_zotero.py -v`
Expected: All 10 tests pass

**Step 3: Commit**

```bash
git add tests/unit/test_zotero.py
git commit -m "$(cat <<'EOF'
test(zotero): add unit tests for ZoteroAttachment and ZoteroItem

Tests immutability, helper methods (is_pdf, is_imported, is_linked_file,
pdf_attachments, has_attachments, has_pdf), and proper dataclass behavior.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_5 -->

<!-- END_SUBCOMPONENT_B -->

---

**Phase 1 Done When:**
- All 9 Zotero error codes defined in ErrorCode enum
- ZoteroError exception class inherits from LocalLibraryError
- ZoteroAttachment and ZoteroItem frozen dataclasses created
- All unit tests pass: `uv run pytest tests/unit/test_errors.py tests/unit/test_zotero.py -v`
