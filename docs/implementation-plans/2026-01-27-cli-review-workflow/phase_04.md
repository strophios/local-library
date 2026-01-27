## Phase 4: Update Command

**Goal:** Editor-based metadata editing with validation loop

---

<!-- START_SUBCOMPONENT_A (tasks 1-5) -->
<!-- START_TASK_1 -->
### Task 1: Create JSON structure builder for update command

**Files:**
- Create: `src/local_library/cli/update.py`

**Step 1: Write the failing test**

Create `tests/unit/test_cli_update.py`:

```python
"""Unit tests for update command."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from local_library.core.models import Document, DocumentStatus


class TestBuildEditableJson:
    """Tests for JSON structure builder."""

    def test_build_editable_json_structure(self) -> None:
        """Should build correct JSON structure for editing."""
        from local_library.cli.update import build_editable_json

        doc = Document(
            id=UUID("12345678-1234-1234-1234-123456789abc"),
            original_path="/path/to/doc.pdf",
            content_hash="abc123",
            storage_path="/storage/ab/c1/abc123.pdf",
            status=DocumentStatus.NEEDS_REVIEW,
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
            extracted_path="/extracted/abc123.md",
            citekey="Smith2023",
            csl_json={"type": "article", "title": "Test"},
            title="Test Title",
            authors="John Smith",
            issued_date="2023",
        )

        result = build_editable_json(doc)
        parsed = json.loads(result)

        # Check readonly block
        assert "_readonly" in parsed
        assert parsed["_readonly"]["id"] == "12345678-1234-1234-1234-123456789abc"
        assert parsed["_readonly"]["original_path"] == "/path/to/doc.pdf"

        # Check editable fields
        assert parsed["status"] == "needs_review"
        assert parsed["citekey"] == "Smith2023"
        assert parsed["csl_json"] == {"type": "article", "title": "Test"}

    def test_build_editable_json_null_fields(self) -> None:
        """Should handle null fields gracefully."""
        from local_library.cli.update import build_editable_json

        doc = Document(
            id=UUID("12345678-1234-1234-1234-123456789abc"),
            original_path="/path/to/doc.pdf",
            content_hash="abc123",
            storage_path="/storage/ab/c1/abc123.pdf",
            status=DocumentStatus.PENDING,
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
            citekey=None,
            csl_json=None,
        )

        result = build_editable_json(doc)
        parsed = json.loads(result)

        assert parsed["citekey"] is None
        assert parsed["csl_json"] is None
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_update.py::TestBuildEditableJson -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'local_library.cli.update'`

**Step 3: Write minimal implementation**

Create `src/local_library/cli/update.py`:

```python
"""Update command - edit document metadata."""

# pattern: Imperative Shell

import json
from typing import Any

from local_library.core.models import Document


def build_editable_json(doc: Document) -> str:
    """Build JSON structure for editing in $EDITOR.

    The structure includes:
    - _readonly: Informational fields (id, paths, timestamps)
    - status: Editable document status
    - citekey: Editable citation key
    - csl_json: Editable bibliographic metadata

    Args:
        doc: Document to build JSON for

    Returns:
        JSON string formatted for editing
    """
    structure: dict[str, Any] = {
        "_readonly": {
            "id": str(doc.id),
            "original_path": doc.original_path,
            "storage_path": doc.storage_path,
            "extracted_path": doc.extracted_path,
            "content_hash": doc.content_hash,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        },
        "status": doc.status.value,
        "citekey": doc.citekey,
        "csl_json": doc.csl_json,
    }

    return json.dumps(structure, indent=2, ensure_ascii=False)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_update.py::TestBuildEditableJson -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/local_library/cli/update.py tests/unit/test_cli_update.py
git commit -m "feat(cli): add JSON structure builder for update command

Creates editable JSON with readonly info block and editable fields
(status, citekey, csl_json)."
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add validation functions for edited JSON

**Files:**
- Modify: `src/local_library/cli/update.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_cli_update.py`:

```python
from local_library.cli.update import validate_edited_json
from local_library.core.models import DocumentStatus


class TestValidateEditedJson:
    """Tests for edited JSON validation."""

    def test_validate_valid_json(self) -> None:
        """Should return no errors for valid JSON."""
        edited = {
            "status": "ready",
            "citekey": "Smith2023",
            "csl_json": {"type": "article", "title": "Test"},
        }

        errors = validate_edited_json(edited, current_citekey="Smith2023", all_citekeys=["Smith2023"])

        assert errors == []

    def test_validate_invalid_status(self) -> None:
        """Should error on invalid status value."""
        edited = {
            "status": "invalid_status",
            "citekey": "Smith2023",
            "csl_json": {"type": "article", "title": "Test"},
        }

        errors = validate_edited_json(edited, current_citekey="Smith2023", all_citekeys=["Smith2023"])

        assert any("status" in e.lower() for e in errors)

    def test_validate_duplicate_citekey(self) -> None:
        """Should error on duplicate citekey."""
        edited = {
            "status": "ready",
            "citekey": "Jones2024",  # Different from current, exists in library
            "csl_json": {"type": "article", "title": "Test"},
        }

        errors = validate_edited_json(
            edited,
            current_citekey="Smith2023",
            all_citekeys=["Smith2023", "Jones2024"],  # Jones2024 already exists
        )

        assert any("citekey" in e.lower() and "exists" in e.lower() for e in errors)

    def test_validate_citekey_same_as_current(self) -> None:
        """Should allow keeping current citekey."""
        edited = {
            "status": "ready",
            "citekey": "Smith2023",  # Same as current
            "csl_json": {"type": "article", "title": "Test"},
        }

        errors = validate_edited_json(
            edited,
            current_citekey="Smith2023",
            all_citekeys=["Smith2023", "Jones2024"],
        )

        assert errors == []

    def test_validate_invalid_csl_json(self) -> None:
        """Should error on invalid CSL-JSON."""
        edited = {
            "status": "ready",
            "citekey": "Smith2023",
            "csl_json": {"title": "Missing type field"},  # No 'type' field
        }

        errors = validate_edited_json(edited, current_citekey="Smith2023", all_citekeys=["Smith2023"])

        assert any("type" in e.lower() for e in errors)

    def test_validate_missing_status(self) -> None:
        """Should error on missing status."""
        edited = {
            "citekey": "Smith2023",
            "csl_json": {"type": "article", "title": "Test"},
        }

        errors = validate_edited_json(edited, current_citekey="Smith2023", all_citekeys=["Smith2023"])

        assert any("status" in e.lower() for e in errors)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_update.py::TestValidateEditedJson -v`
Expected: FAIL with `ImportError: cannot import name 'validate_edited_json'`

**Step 3: Write minimal implementation**

Add to `src/local_library/cli/update.py`:

```python
from local_library.core.models import Document, DocumentStatus
from local_library.ingestion.metadata import MetadataHandler


def validate_edited_json(
    edited: dict[str, Any],
    current_citekey: str | None,
    all_citekeys: list[str],
) -> list[str]:
    """Validate edited JSON structure.

    Checks:
    - status is valid DocumentStatus value
    - citekey is unique (or unchanged from current)
    - csl_json passes schema validation

    Args:
        edited: Parsed JSON from editor
        current_citekey: Document's current citekey (for uniqueness check)
        all_citekeys: All citekeys in the library

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []

    # Validate status
    if "status" not in edited:
        errors.append("missing required field: status")
    else:
        try:
            DocumentStatus(edited["status"])
        except ValueError:
            valid = ", ".join(s.value for s in DocumentStatus)
            errors.append(f"invalid status '{edited['status']}' (valid: {valid})")

    # Validate citekey uniqueness
    new_citekey = edited.get("citekey")
    if new_citekey is not None and new_citekey != current_citekey:
        if new_citekey in all_citekeys:
            errors.append(f"citekey '{new_citekey}' already exists in library")

    # Validate CSL-JSON if present
    csl_json = edited.get("csl_json")
    if csl_json is not None:
        handler = MetadataHandler()
        is_valid, issues = handler.validate(csl_json)
        if not is_valid:
            for issue in issues:
                if not issue.startswith("warning:"):
                    errors.append(f"CSL-JSON: {issue}")

    return errors
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_update.py::TestValidateEditedJson -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/local_library/cli/update.py tests/unit/test_cli_update.py
git commit -m "feat(cli): add validation for edited JSON

Validates status enum, citekey uniqueness, and CSL-JSON schema."
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add error insertion for re-editing

**Files:**
- Modify: `src/local_library/cli/update.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_cli_update.py`:

```python
from local_library.cli.update import insert_errors_as_comments


class TestInsertErrorsAsComments:
    """Tests for error insertion in JSON."""

    def test_insert_errors_at_top(self) -> None:
        """Should insert errors as comments at top of JSON."""
        original = '{\n  "status": "invalid"\n}'
        errors = ["invalid status 'invalid'", "citekey already exists"]

        result = insert_errors_as_comments(original, errors)

        # Errors should appear as comments before JSON
        lines = result.split("\n")
        assert "// ERROR:" in lines[0] or "// ERRORS:" in lines[0]
        assert any("invalid status" in line for line in lines[:5])
        assert any("citekey" in line for line in lines[:5])

    def test_insert_errors_preserves_json(self) -> None:
        """Should preserve original JSON content."""
        original = '{\n  "status": "ready",\n  "citekey": "Smith2023"\n}'
        errors = ["some error"]

        result = insert_errors_as_comments(original, errors)

        # JSON should still be present after comments
        assert '"status": "ready"' in result
        assert '"citekey": "Smith2023"' in result
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_update.py::TestInsertErrorsAsComments -v`
Expected: FAIL with `ImportError: cannot import name 'insert_errors_as_comments'`

**Step 3: Write minimal implementation**

Add to `src/local_library/cli/update.py`:

```python
def insert_errors_as_comments(json_content: str, errors: list[str]) -> str:
    """Insert validation errors as comments at top of JSON.

    Note: JSON doesn't support comments, but editors will display them.
    The parse step will need to strip these comments before parsing.

    Args:
        json_content: Original JSON string
        errors: List of error messages

    Returns:
        JSON with error comments prepended
    """
    comment_lines = ["// ERRORS (fix these issues and save again):"]
    for error in errors:
        comment_lines.append(f"//   - {error}")
    comment_lines.append("//")
    comment_lines.append("")

    return "\n".join(comment_lines) + json_content
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_update.py::TestInsertErrorsAsComments -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/local_library/cli/update.py tests/unit/test_cli_update.py
git commit -m "feat(cli): add error comment insertion for re-editing

Prepends validation errors as comments for user to see on re-edit."
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add JSON parsing with comment stripping

**Files:**
- Modify: `src/local_library/cli/update.py`

**Step 1: Write the failing test**

Add to `tests/unit/test_cli_update.py`:

```python
from local_library.cli.update import parse_edited_json


class TestParseEditedJson:
    """Tests for JSON parsing with comment handling."""

    def test_parse_clean_json(self) -> None:
        """Should parse clean JSON."""
        content = '{"status": "ready", "citekey": "Smith2023"}'

        result = parse_edited_json(content)

        assert result == {"status": "ready", "citekey": "Smith2023"}

    def test_parse_json_with_comments(self) -> None:
        """Should strip comments and parse JSON."""
        content = """// ERRORS:
//   - some error
//
{"status": "ready", "citekey": "Smith2023"}"""

        result = parse_edited_json(content)

        assert result == {"status": "ready", "citekey": "Smith2023"}

    def test_parse_empty_file_returns_none(self) -> None:
        """Should return None for empty/whitespace-only file (abort signal)."""
        assert parse_edited_json("") is None
        assert parse_edited_json("   \n\n  ") is None
        assert parse_edited_json("// just comments\n// more comments") is None

    def test_parse_invalid_json_raises(self) -> None:
        """Should raise ValueError for invalid JSON."""
        content = '{"status": "ready", missing_quotes: bad}'

        with pytest.raises(ValueError) as exc_info:
            parse_edited_json(content)

        assert "JSON" in str(exc_info.value) or "parse" in str(exc_info.value).lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_update.py::TestParseEditedJson -v`
Expected: FAIL with `ImportError: cannot import name 'parse_edited_json'`

**Step 3: Write minimal implementation**

Add to `src/local_library/cli/update.py`:

```python
def parse_edited_json(content: str) -> dict[str, Any] | None:
    """Parse JSON content, stripping any comment lines.

    Args:
        content: File content (may include // comments)

    Returns:
        Parsed JSON dict, or None if file is empty/aborted

    Raises:
        ValueError: If JSON parsing fails
    """
    # Strip comment lines (lines starting with //)
    lines = content.split("\n")
    json_lines = [line for line in lines if not line.strip().startswith("//")]
    json_content = "\n".join(json_lines).strip()

    # Empty content = abort
    if not json_content:
        return None

    try:
        return json.loads(json_content)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_update.py::TestParseEditedJson -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/local_library/cli/update.py tests/unit/test_cli_update.py
git commit -m "feat(cli): add JSON parsing with comment stripping

Strips // comments before parsing, returns None on empty (abort)."
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Implement update command with editor loop

**Files:**
- Modify: `src/local_library/cli/update.py`
- Modify: `src/local_library/core/library.py` (add update_metadata method)
- Modify: `src/local_library/cli/main.py` (register command)

**Step 1: Write the failing test**

Add to `tests/unit/test_cli_update.py`:

```python
from unittest.mock import MagicMock, patch, mock_open
from typer.testing import CliRunner

from local_library.cli.main import app

runner = CliRunner()


@pytest.fixture
def mock_library_update():
    """Provide a mock Library for update command testing."""
    with patch("local_library.cli.update.Library") as mock_lib_cls:
        mock_lib = MagicMock()
        mock_lib_cls.return_value.__enter__ = MagicMock(return_value=mock_lib)
        mock_lib_cls.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_lib


class TestUpdateCommand:
    """Tests for update command."""

    def test_update_success(self, mock_library_update: MagicMock) -> None:
        """update command should apply valid changes."""
        mock_doc = MagicMock()
        mock_doc.id = UUID("12345678-1234-1234-1234-123456789abc")
        mock_doc.status = DocumentStatus.NEEDS_REVIEW
        mock_doc.citekey = "Smith2023"
        mock_doc.csl_json = {"type": "article", "title": "Test"}
        mock_doc.original_path = "/path/to/doc.pdf"
        mock_doc.storage_path = "/storage/doc.pdf"
        mock_doc.extracted_path = "/extracted/doc.md"
        mock_doc.content_hash = "abc123"
        mock_doc.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mock_doc.updated_at = datetime(2025, 1, 2, tzinfo=timezone.utc)
        mock_doc.title = "Test"
        mock_doc.authors = "Smith"
        mock_doc.issued_date = "2023"

        mock_library_update.get.return_value = mock_doc
        mock_library_update.get_all_citekeys.return_value = ["Smith2023"]

        # Mock the editor to return modified JSON
        edited_json = json.dumps({
            "status": "ready",
            "citekey": "Smith2023",
            "csl_json": {"type": "article", "title": "Updated Title"},
        })

        with (
            patch("local_library.cli.update.find_editor", return_value="/usr/bin/nvim"),
            patch("tempfile.NamedTemporaryFile") as mock_tempfile,
            patch("local_library.cli.update.subprocess.run"),
            patch("builtins.open", mock_open(read_data=edited_json)),
        ):
            mock_tempfile.return_value.__enter__.return_value.name = "/tmp/edit.json"

            result = runner.invoke(app, ["update", "12345678"])

            assert result.exit_code == 0
            mock_library_update.update_metadata.assert_called_once()

    def test_update_abort_on_empty(self, mock_library_update: MagicMock) -> None:
        """update command should abort if file is empty."""
        mock_doc = MagicMock()
        mock_doc.id = UUID("12345678-1234-1234-1234-123456789abc")
        mock_doc.status = DocumentStatus.NEEDS_REVIEW
        mock_doc.citekey = "Smith2023"
        mock_doc.csl_json = {"type": "article", "title": "Test"}
        mock_doc.original_path = "/path/to/doc.pdf"
        mock_doc.storage_path = "/storage/doc.pdf"
        mock_doc.extracted_path = "/extracted/doc.md"
        mock_doc.content_hash = "abc123"
        mock_doc.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mock_doc.updated_at = datetime(2025, 1, 2, tzinfo=timezone.utc)
        mock_doc.title = None
        mock_doc.authors = None
        mock_doc.issued_date = None

        mock_library_update.get.return_value = mock_doc

        with (
            patch("local_library.cli.update.find_editor", return_value="/usr/bin/nvim"),
            patch("tempfile.NamedTemporaryFile") as mock_tempfile,
            patch("local_library.cli.update.subprocess.run"),
            patch("builtins.open", mock_open(read_data="")),  # Empty file = abort
        ):
            mock_tempfile.return_value.__enter__.return_value.name = "/tmp/edit.json"

            result = runner.invoke(app, ["update", "12345678"])

            assert result.exit_code == 0
            assert "aborted" in result.output.lower()
            mock_library_update.update_metadata.assert_not_called()

    def test_update_citekey_lookup(self, mock_library_update: MagicMock) -> None:
        """update @citekey should use citekey lookup."""
        mock_doc = MagicMock()
        mock_doc.id = UUID("12345678-1234-1234-1234-123456789abc")
        mock_doc.status = DocumentStatus.READY
        mock_doc.citekey = "Smith2023"
        mock_doc.csl_json = {"type": "article", "title": "Test"}
        mock_doc.original_path = "/path/to/doc.pdf"
        mock_doc.storage_path = "/storage/doc.pdf"
        mock_doc.extracted_path = "/extracted/doc.md"
        mock_doc.content_hash = "abc123"
        mock_doc.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mock_doc.updated_at = datetime(2025, 1, 2, tzinfo=timezone.utc)
        mock_doc.title = "Test"
        mock_doc.authors = "Smith"
        mock_doc.issued_date = "2023"

        mock_library_update.get_by_citekey.return_value = mock_doc
        mock_library_update.get_all_citekeys.return_value = ["Smith2023"]

        edited_json = json.dumps({
            "status": "ready",
            "citekey": "Smith2023",
            "csl_json": {"type": "article", "title": "Test"},
        })

        with (
            patch("local_library.cli.update.find_editor", return_value="/usr/bin/nvim"),
            patch("tempfile.NamedTemporaryFile") as mock_tempfile,
            patch("local_library.cli.update.subprocess.run"),
            patch("builtins.open", mock_open(read_data=edited_json)),
        ):
            mock_tempfile.return_value.__enter__.return_value.name = "/tmp/edit.json"

            result = runner.invoke(app, ["update", "@Smith2023"])

            assert result.exit_code == 0
            mock_library_update.get_by_citekey.assert_called_once_with("Smith2023")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_update.py::TestUpdateCommand -v`
Expected: FAIL (update command not implemented yet)

**Step 3a: Write full implementation of update.py**

Replace `src/local_library/cli/update.py` with full implementation:

```python
"""Update command - edit document metadata."""

# pattern: Imperative Shell

import json
import subprocess
import tempfile
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.prompt import Confirm

from local_library.cli.open import find_editor
from local_library.cli.utils import resolve_identifier
from local_library.core import Library, LookupError
from local_library.core.models import Document, DocumentStatus
from local_library.ingestion.metadata import MetadataHandler

console = Console()
err_console = Console(stderr=True)


def build_editable_json(doc: Document) -> str:
    """Build JSON structure for editing in $EDITOR.

    The structure includes:
    - _readonly: Informational fields (id, paths, timestamps)
    - status: Editable document status
    - citekey: Editable citation key
    - csl_json: Editable bibliographic metadata

    Args:
        doc: Document to build JSON for

    Returns:
        JSON string formatted for editing
    """
    structure: dict[str, Any] = {
        "_readonly": {
            "id": str(doc.id),
            "original_path": doc.original_path,
            "storage_path": doc.storage_path,
            "extracted_path": doc.extracted_path,
            "content_hash": doc.content_hash,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        },
        "status": doc.status.value,
        "citekey": doc.citekey,
        "csl_json": doc.csl_json,
    }

    return json.dumps(structure, indent=2, ensure_ascii=False)


def validate_edited_json(
    edited: dict[str, Any],
    current_citekey: str | None,
    all_citekeys: list[str],
) -> list[str]:
    """Validate edited JSON structure.

    Checks:
    - status is valid DocumentStatus value
    - citekey is unique (or unchanged from current)
    - csl_json passes schema validation

    Args:
        edited: Parsed JSON from editor
        current_citekey: Document's current citekey (for uniqueness check)
        all_citekeys: All citekeys in the library

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []

    # Validate status
    if "status" not in edited:
        errors.append("missing required field: status")
    else:
        try:
            DocumentStatus(edited["status"])
        except ValueError:
            valid = ", ".join(s.value for s in DocumentStatus)
            errors.append(f"invalid status '{edited['status']}' (valid: {valid})")

    # Validate citekey uniqueness
    new_citekey = edited.get("citekey")
    if new_citekey is not None and new_citekey != current_citekey:
        if new_citekey in all_citekeys:
            errors.append(f"citekey '{new_citekey}' already exists in library")

    # Validate CSL-JSON if present
    csl_json = edited.get("csl_json")
    if csl_json is not None:
        handler = MetadataHandler()
        is_valid, issues = handler.validate(csl_json)
        if not is_valid:
            for issue in issues:
                if not issue.startswith("warning:"):
                    errors.append(f"CSL-JSON: {issue}")

    return errors


def insert_errors_as_comments(json_content: str, errors: list[str]) -> str:
    """Insert validation errors as comments at top of JSON.

    Note: JSON doesn't support comments, but editors will display them.
    The parse step will need to strip these comments before parsing.

    Args:
        json_content: Original JSON string
        errors: List of error messages

    Returns:
        JSON with error comments prepended
    """
    comment_lines = ["// ERRORS (fix these issues and save again):"]
    for error in errors:
        comment_lines.append(f"//   - {error}")
    comment_lines.append("//")
    comment_lines.append("")

    return "\n".join(comment_lines) + json_content


def parse_edited_json(content: str) -> dict[str, Any] | None:
    """Parse JSON content, stripping any comment lines.

    Args:
        content: File content (may include // comments)

    Returns:
        Parsed JSON dict, or None if file is empty/aborted

    Raises:
        ValueError: If JSON parsing fails
    """
    # Strip comment lines (lines starting with //)
    lines = content.split("\n")
    json_lines = [line for line in lines if not line.strip().startswith("//")]
    json_content = "\n".join(json_lines).strip()

    # Empty content = abort
    if not json_content:
        return None

    try:
        return json.loads(json_content)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e


def _check_citekey_regeneration(
    original_csl: dict[str, Any] | None,
    new_csl: dict[str, Any] | None,
    original_citekey: str | None,
    new_citekey: str | None,
) -> bool:
    """Check if citekey should be regenerated based on metadata changes.

    Args:
        original_csl: Original CSL-JSON
        new_csl: New CSL-JSON after edit
        original_citekey: Original citekey
        new_citekey: New citekey after edit

    Returns:
        True if user should be prompted to regenerate citekey
    """
    # Only prompt if citekey wasn't changed manually
    if new_citekey != original_citekey:
        return False

    # Only prompt if CSL-JSON exists in both
    if not original_csl or not new_csl:
        return False

    # Check if relevant fields changed
    def get_citekey_fields(csl: dict[str, Any]) -> tuple:
        return (
            csl.get("title"),
            csl.get("author"),
            csl.get("issued"),
        )

    return get_citekey_fields(original_csl) != get_citekey_fields(new_csl)


def update(
    identifier: Annotated[
        str, typer.Argument(help="Document ID (UUID or @citekey)")
    ],
) -> None:
    """Edit document metadata in your editor.

    Opens a JSON file containing the document's status, citekey, and
    CSL-JSON metadata. Edit the fields and save to apply changes.

    Supports both UUID (full or partial) and @citekey identifiers.

    To abort, save an empty file or delete all content.
    """
    # Find editor first
    editor = find_editor()
    if not editor:
        err_console.print("[red]error:[/red] no editor found")
        err_console.print(
            "[dim]Install nvim/vim or set $EDITOR environment variable.[/dim]"
        )
        raise typer.Exit(code=1) from None

    try:
        with Library() as lib:
            doc = resolve_identifier(identifier, lib)
            all_citekeys = lib.get_all_citekeys()

            # Build initial JSON
            json_content = build_editable_json(doc)

            # Edit loop
            while True:
                # Write to temp file and open editor
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".json",
                    delete=False,
                ) as f:
                    f.write(json_content)
                    temp_path = f.name

                subprocess.run([editor, temp_path], check=False)

                # Read edited content
                with open(temp_path) as f:
                    edited_content = f.read()

                # Parse
                try:
                    parsed = parse_edited_json(edited_content)
                except ValueError as e:
                    # JSON parse error - re-edit with error message
                    json_content = insert_errors_as_comments(edited_content, [str(e)])
                    continue

                # Check for abort
                if parsed is None:
                    console.print("[yellow]Update aborted.[/yellow]")
                    return

                # Validate
                errors = validate_edited_json(parsed, doc.citekey, all_citekeys)
                if errors:
                    # Re-edit with errors
                    json_content = insert_errors_as_comments(edited_content, errors)
                    continue

                # Valid - break out of loop
                break

            # Check if citekey should be regenerated
            new_citekey = parsed.get("citekey")
            new_csl = parsed.get("csl_json")
            if _check_citekey_regeneration(doc.csl_json, new_csl, doc.citekey, new_citekey):
                if Confirm.ask(
                    "Author/title/year changed. Regenerate citekey?",
                    default=False,
                ):
                    handler = MetadataHandler()
                    new_citekey = handler.generate_citekey(new_csl)
                    # Ensure uniqueness
                    if new_citekey in all_citekeys and new_citekey != doc.citekey:
                        from local_library.core.storage import get_unique_citekey, get_connection

                        conn = get_connection()
                        new_citekey = get_unique_citekey(conn, new_citekey)
                    console.print(f"[dim]New citekey: {new_citekey}[/dim]")

            # Apply updates
            lib.update_metadata(
                doc.id,
                status=DocumentStatus(parsed["status"]),
                citekey=new_citekey,
                csl_json=new_csl,
            )

            console.print(f"[green]Updated document {doc.id}[/green]")

    except LookupError as e:
        err_console.print(f"[red]error:[/red] {e.message}")
        if "suggestions" in e.details and e.details["suggestions"]:
            err_console.print("[dim]Did you mean:[/dim]")
            for suggestion in e.details["suggestions"]:
                err_console.print(f"  [cyan]@{suggestion}[/cyan]")
        raise typer.Exit(code=1) from None
```

**Step 3b: Add Library.update_metadata method**

Add to `src/local_library/core/library.py` (after `get_all_citekeys()` method):

```python
def update_metadata(
    self,
    doc_id: UUID,
    status: DocumentStatus | None = None,
    citekey: str | None = None,
    csl_json: dict[str, Any] | None = None,
) -> Document:
    """Update a document's metadata.

    Args:
        doc_id: Document UUID
        status: New status (if changing)
        citekey: New citekey (if changing)
        csl_json: New CSL-JSON (if changing)

    Returns:
        Updated Document
    """
    # Extract indexed fields from CSL-JSON if provided
    title = None
    authors = None
    issued_date = None

    if csl_json:
        title = csl_json.get("title")
        if "author" in csl_json:
            author_names = []
            for author in csl_json["author"]:
                if "family" in author:
                    name = author.get("family", "")
                    if "given" in author:
                        name = f"{author['given']} {name}"
                    author_names.append(name)
                elif "literal" in author:
                    author_names.append(author["literal"])
            authors = "; ".join(author_names) if author_names else None

        if "issued" in csl_json:
            issued = csl_json["issued"]
            if "date-parts" in issued and issued["date-parts"]:
                date_parts = issued["date-parts"][0]
                if date_parts:
                    issued_date = str(date_parts[0])  # Year

    # Update status if provided
    if status is not None:
        update_document_status(self._conn, doc_id, status)

    # Update metadata fields
    return update_document_metadata(
        self._conn,
        doc_id,
        citekey=citekey,
        csl_json=csl_json,
        title=title,
        authors=authors,
        issued_date=issued_date,
    )
```

Add import at top of `library.py`:
```python
from local_library.core.storage import (
    # ... existing imports ...
    update_document_status,
    update_document_metadata,
)
```

**Step 3c: Register command in main.py**

Update `src/local_library/cli/main.py`:

```python
"""CLI entry point with Typer app and shared context."""

# pattern: Imperative Shell

import typer

from local_library.cli import add as add_cmd
from local_library.cli import delete as delete_cmd
from local_library.cli import list as list_cmd
from local_library.cli import open as open_cmd
from local_library.cli import show as show_cmd
from local_library.cli import update as update_cmd

# Create Typer app
app = typer.Typer(
    name="local-library",
    help="Personal knowledge management for local documents.",
    add_completion=False,
)

# Register subcommands
app.command(name="add")(add_cmd.add)
app.command(name="list")(list_cmd.list_docs)
app.command(name="show")(show_cmd.show)
app.command(name="delete")(delete_cmd.delete)
app.command(name="open")(open_cmd.open_doc)
app.command(name="update")(update_cmd.update)


def main() -> None:
    """CLI entry point."""
    app()


if __name__ == "__main__":
    main()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_cli_update.py::TestUpdateCommand -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/local_library/cli/update.py src/local_library/cli/main.py src/local_library/core/library.py tests/unit/test_cli_update.py
git commit -m "feat(cli): implement update command with editor workflow

Editor-based metadata editing with validation loop.
Validates status enum, citekey uniqueness, CSL-JSON schema.
Re-opens editor with error comments on invalid input.
Prompts for citekey regeneration when relevant fields change.
Supports @citekey lookup with suggestions on miss."
```
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_A -->

---

**Phase complete when:** `update @citekey` launches editor, validates changes, applies updates, re-indexes fields.
