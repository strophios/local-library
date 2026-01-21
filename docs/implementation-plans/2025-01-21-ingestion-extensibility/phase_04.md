# Phase 4: Decouple FileAcquirer from PDF

**Goal:** FileAcquirer handles any local file, not just PDFs.

**Codebase verification findings:**
- ✓ `FileAcquirer` in `src/local_library/ingestion/file.py` (line 12)
- ✓ `SUPPORTED_EXTENSIONS = {".pdf"}` at line 20 - **to be removed**
- ✓ `can_handle()` checks extension (line 34) - **to be changed**
- ✓ `validate()` checks extension at lines 81-86 - **to be removed**
- ✓ `acquire()` returns hardcoded `mime_type="application/pdf"` at line 135 - **to be dynamic**

**Key changes:**
1. Remove `SUPPORTED_EXTENSIONS` class attribute
2. Update `can_handle()` to accept any local path (reject URLs)
3. Remove extension check from `validate()`
4. Add `_detect_mime_type()` for dynamic MIME type detection
5. Update `acquire()` to use dynamic MIME type

---

<!-- START_TASK_1 -->
### Task 1: Remove SUPPORTED_EXTENSIONS and update can_handle()

**Files:**
- Modify: `src/local_library/ingestion/file.py`

**Step 1: Remove SUPPORTED_EXTENSIONS**

Delete line 20:
```python
    SUPPORTED_EXTENSIONS = {".pdf"}
```

**Step 2: Update can_handle() to check for local path (not URL)**

Replace the `can_handle` method (lines 22-36) with:

```python
    def can_handle(self, source: str) -> bool:
        """Check if source is a local file path (not a URL).

        Args:
            source: Source path to check

        Returns:
            True if source appears to be a local file path
        """
        # Reject URLs (simple heuristic: starts with common URL schemes)
        if source.startswith(("http://", "https://", "ftp://", "file://")):
            return False

        try:
            # Check it's a valid path-like string
            Path(source)
            return True
        except (ValueError, OSError):
            return False
```

**Step 3: Verify the code works**

Run:
```bash
uv run python -c "
from local_library.ingestion.file import FileAcquirer
fa = FileAcquirer()
print('local path:', fa.can_handle('/some/file.pdf'))
print('txt file:', fa.can_handle('/some/file.txt'))
print('http URL:', fa.can_handle('http://example.com/doc.pdf'))
print('https URL:', fa.can_handle('https://example.com/doc.pdf'))
"
```

Expected output:
```
local path: True
txt file: True
http URL: False
https URL: False
```

**Step 4: Commit**

```bash
git add src/local_library/ingestion/file.py
git commit -m "refactor(file-acquirer): remove SUPPORTED_EXTENSIONS, accept any local path

FileAcquirer.can_handle() now returns True for any local path
and False for URLs. Extension checking is no longer its job."
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Remove extension check from validate()

**Files:**
- Modify: `src/local_library/ingestion/file.py`

**Step 1: Remove extension validation from validate()**

In the `validate` method, delete the extension check block (the lines that check `path.suffix.lower() not in self.SUPPORTED_EXTENSIONS`). The method should end after the readability check.

The complete `validate` method should now be:

```python
    def validate(self, source: str) -> None:
        """Validate that file exists and is readable.

        Args:
            source: Path to the file

        Raises:
            AcquisitionError: If file doesn't exist or isn't readable
        """
        path = Path(source)

        if not path.exists():
            raise AcquisitionError(
                f"file not found: {source}",
                ErrorCode.ACQUISITION_FILE_NOT_FOUND,
                details={"path": source},
            )

        if not path.is_file():
            raise AcquisitionError(
                f"not a file: {source}",
                ErrorCode.ACQUISITION_INVALID_FORMAT,
                details={"path": source},
            )

        # Check readability by attempting to open
        try:
            with open(path, "rb") as f:
                f.read(1)  # Read 1 byte to verify access
        except PermissionError as e:
            raise AcquisitionError(
                f"file not readable: {source}",
                ErrorCode.ACQUISITION_FILE_NOT_READABLE,
                details={"path": source},
            ) from e
        except OSError as e:
            raise AcquisitionError(
                f"cannot access file: {source}: {e}",
                ErrorCode.ACQUISITION_FILE_NOT_READABLE,
                details={"path": source},
            ) from e
```

**Step 2: Verify the code works**

Run:
```bash
uv run python -c "
from local_library.ingestion.file import FileAcquirer
from pathlib import Path
import tempfile

fa = FileAcquirer()
with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
    f.write(b'test content')
    txt_path = f.name

# Should NOT raise - txt is now accepted
fa.validate(txt_path)
print('txt file validated successfully')

Path(txt_path).unlink()
"
```

Expected output:
```
txt file validated successfully
```

**Step 3: Commit**

```bash
git add src/local_library/ingestion/file.py
git commit -m "refactor(file-acquirer): remove extension check from validate()

Extension validation is now the extractor's responsibility, not
the acquirer's. FileAcquirer validates existence and readability only."
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add _detect_mime_type() helper method

**Files:**
- Modify: `src/local_library/ingestion/file.py`

**Step 1: Add mimetypes import**

At the top of the file, add:

```python
import mimetypes
```

**Step 2: Add _detect_mime_type() method**

Add this method to the FileAcquirer class, before the `acquire` method:

```python
    def _detect_mime_type(self, file_path: Path) -> str:
        """Detect MIME type from file extension.

        Args:
            file_path: Path to the file

        Returns:
            MIME type string, or 'application/octet-stream' if unknown
        """
        mime_type, _ = mimetypes.guess_type(str(file_path))
        return mime_type or "application/octet-stream"
```

**Step 3: Verify the method works**

Run:
```bash
uv run python -c "
from local_library.ingestion.file import FileAcquirer
from pathlib import Path

fa = FileAcquirer()
print('pdf:', fa._detect_mime_type(Path('test.pdf')))
print('txt:', fa._detect_mime_type(Path('test.txt')))
print('epub:', fa._detect_mime_type(Path('test.epub')))
print('html:', fa._detect_mime_type(Path('test.html')))
print('unknown:', fa._detect_mime_type(Path('test.xyz')))
"
```

Expected output:
```
pdf: application/pdf
txt: text/plain
epub: application/epub+zip
html: text/html
unknown: application/octet-stream
```

**Step 4: Commit**

```bash
git add src/local_library/ingestion/file.py
git commit -m "feat(file-acquirer): add _detect_mime_type helper

Uses mimetypes.guess_type() to detect MIME type from extension.
Falls back to application/octet-stream for unknown types."
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update acquire() to use dynamic MIME type

**Files:**
- Modify: `src/local_library/ingestion/file.py`

**Step 1: Update acquire() return statement**

In the `acquire` method, replace the hardcoded MIME type in the return statement.

Change line 135 from:
```python
            mime_type="application/pdf",  # For now, only PDFs supported
```

To:
```python
            mime_type=self._detect_mime_type(source_path),
```

**Step 2: Verify the code works**

Run:
```bash
uv run python -c "
from local_library.ingestion.file import FileAcquirer
from pathlib import Path
import tempfile

fa = FileAcquirer()

# Test with a txt file
with tempfile.TemporaryDirectory() as tmpdir:
    txt_file = Path(tmpdir) / 'test.txt'
    txt_file.write_text('test content')
    dest_dir = Path(tmpdir) / 'dest'

    result = fa.acquire(str(txt_file), dest_dir)
    print(f'mime_type: {result.mime_type}')
"
```

Expected output:
```
mime_type: text/plain
```

**Step 3: Commit**

```bash
git add src/local_library/ingestion/file.py
git commit -m "refactor(file-acquirer): use dynamic MIME type detection

acquire() now detects MIME type from file extension instead of
hardcoding 'application/pdf'."
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Update tests for decoupled FileAcquirer

**Files:**
- Modify: `tests/unit/test_ingestion.py`

**Step 1: Update test_can_handle tests**

Find the `TestFileAcquirer` class and update/replace the can_handle tests:

```python
    def test_can_handle_local_path(self, acquirer: FileAcquirer) -> None:
        """can_handle should return True for local file paths."""
        assert acquirer.can_handle("/path/to/file.pdf") is True
        assert acquirer.can_handle("/path/to/file.txt") is True
        assert acquirer.can_handle("relative/path.epub") is True

    def test_can_handle_rejects_http_url(self, acquirer: FileAcquirer) -> None:
        """can_handle should return False for HTTP URLs."""
        assert acquirer.can_handle("http://example.com/doc.pdf") is False

    def test_can_handle_rejects_https_url(self, acquirer: FileAcquirer) -> None:
        """can_handle should return False for HTTPS URLs."""
        assert acquirer.can_handle("https://example.com/doc.pdf") is False

    def test_can_handle_rejects_ftp_url(self, acquirer: FileAcquirer) -> None:
        """can_handle should return False for FTP URLs."""
        assert acquirer.can_handle("ftp://example.com/doc.pdf") is False
```

**Step 2: Remove the old extension-based tests**

Delete these tests if they exist:
- `test_can_handle_pdf_file`
- `test_can_handle_uppercase_extension`
- `test_cannot_handle_unsupported_extension`
- `test_cannot_handle_no_extension`
- `test_validate_unsupported_extension`

**Step 3: Add test for MIME type detection**

Add to the `TestFileAcquirer` class:

```python
    def test_acquire_detects_mime_type_for_pdf(
        self, acquirer: FileAcquirer, temp_dir: Path
    ) -> None:
        """acquire should detect correct MIME type for PDF."""
        pdf_file = temp_dir / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 test content")
        dest_dir = temp_dir / "dest"

        result = acquirer.acquire(str(pdf_file), dest_dir)

        assert result.mime_type == "application/pdf"

    def test_acquire_detects_mime_type_for_txt(
        self, acquirer: FileAcquirer, temp_dir: Path
    ) -> None:
        """acquire should detect correct MIME type for text file."""
        txt_file = temp_dir / "test.txt"
        txt_file.write_text("plain text content")
        dest_dir = temp_dir / "dest"

        result = acquirer.acquire(str(txt_file), dest_dir)

        assert result.mime_type == "text/plain"

    def test_acquire_fallback_mime_type_for_unknown(
        self, acquirer: FileAcquirer, temp_dir: Path
    ) -> None:
        """acquire should use fallback MIME type for unknown extension."""
        unknown_file = temp_dir / "test.xyz"
        unknown_file.write_bytes(b"unknown content")
        dest_dir = temp_dir / "dest"

        result = acquirer.acquire(str(unknown_file), dest_dir)

        assert result.mime_type == "application/octet-stream"
```

**Step 4: Update validate tests**

Update `test_validate_existing_file` to use any file type (not just PDF):

```python
    def test_validate_existing_file(self, acquirer: FileAcquirer, temp_dir: Path) -> None:
        """validate should pass for existing readable file."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("test content")

        # Should not raise
        acquirer.validate(str(test_file))
```

**Step 5: Run the updated tests**

Run:
```bash
uv run pytest tests/unit/test_ingestion.py::TestFileAcquirer -v
```

Expected: All tests pass.

**Step 6: Run all ingestion tests**

Run:
```bash
uv run pytest tests/unit/test_ingestion.py -v
```

Expected: All tests pass.

**Step 7: Commit**

```bash
git add tests/unit/test_ingestion.py
git commit -m "test(ingestion): update FileAcquirer tests for content-agnostic behavior

- Update can_handle tests to verify URL rejection instead of extension checking
- Add MIME type detection tests
- Remove extension-specific validation tests"
```
<!-- END_TASK_5 -->

---

**Phase 4 complete when:**
- FileAcquirer.can_handle() accepts any local path, rejects URLs
- FileAcquirer.validate() checks existence/readability only (no extension check)
- FileAcquirer.acquire() detects MIME type dynamically
- All tests pass with updated assertions
