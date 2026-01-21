# Phase 2: Add Dispatch Methods to Library

**Goal:** Implement handler dispatch without changing existing behavior.

**Codebase verification findings:**
- ✓ Library class in `src/local_library/core/library.py` (line 42)
- ✓ Library uses `_acquirer` and `_extractor` as single instances (lines 68-69)
- ✓ ContentAcquirer protocol in `src/local_library/ingestion/base.py` (line 12)
- ✓ ContentExtractor protocol in `src/local_library/ingestion/base.py` (line 60)
- ✓ Both protocols have `can_handle()` methods

**Testing approach:** Following existing patterns:
- Real SQLite in temp directories (no mocking)
- Mock Marker extraction (too expensive)
- Fixtures for test isolation

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Add `_find_acquirer()` dispatch method

**Files:**
- Modify: `src/local_library/core/library.py`

**Step 1: Add the import for the protocol**

At the top of `library.py`, add import for ContentAcquirer protocol. After line 37, add:

```python
from local_library.ingestion.base import compute_storage_path, ContentAcquirer
```

(Modify the existing import to add `ContentAcquirer`)

**Step 2: Add `_find_acquirer()` method**

Add this method to the Library class, after the `__exit__` method (after line 93) and before the `# --- Add Pipeline ---` comment:

```python
    def _find_acquirer(self, source: str) -> ContentAcquirer:
        """Find an acquirer that can handle the given source.

        Iterates through registered acquirers and returns the first
        one whose can_handle() returns True.

        Args:
            source: Source identifier (path, URL, etc.)

        Returns:
            The acquirer that can handle this source

        Raises:
            AcquisitionError: If no acquirer can handle the source
        """
        # For now, we only have one acquirer - will be refactored in Phase 3
        if self._acquirer.can_handle(source):
            return self._acquirer

        raise AcquisitionError(
            f"no acquirer can handle source: {source}",
            ErrorCode.ACQUISITION_UNSUPPORTED_SOURCE,
            details={"source": source},
        )
```

**Step 3: Verify the code imports correctly**

Run:
```bash
uv run python -c "from local_library.core.library import Library; print('OK')"
```

Expected output: `OK`

**Step 4: Commit**

```bash
git add src/local_library/core/library.py
git commit -m "feat(library): add _find_acquirer dispatch method

Returns first acquirer that can handle the source.
Raises ACQUISITION_UNSUPPORTED_SOURCE if no handler matches."
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add `_find_extractor()` dispatch method

**Files:**
- Modify: `src/local_library/core/library.py`

**Step 1: Add the import for ContentExtractor protocol**

Modify the import from `base.py` to include ContentExtractor:

```python
from local_library.ingestion.base import compute_storage_path, ContentAcquirer, ContentExtractor
```

**Step 2: Add `_find_extractor()` method**

Add this method right after `_find_acquirer()`:

```python
    def _find_extractor(self, file_path: Path) -> ContentExtractor:
        """Find an extractor that can handle the given file.

        Iterates through registered extractors and returns the first
        one whose can_handle() returns True.

        Args:
            file_path: Path to the file to extract

        Returns:
            The extractor that can handle this file

        Raises:
            ExtractionError: If no extractor can handle the file
        """
        # For now, we only have one extractor - will be refactored in Phase 3
        if self._extractor.can_handle(file_path):
            return self._extractor

        raise ExtractionError(
            f"no extractor can handle file: {file_path}",
            ErrorCode.EXTRACTION_UNSUPPORTED_FORMAT,
            details={"file_path": str(file_path)},
        )
```

**Step 3: Verify the code imports correctly**

Run:
```bash
uv run python -c "from local_library.core.library import Library; print('OK')"
```

Expected output: `OK`

**Step 4: Run existing tests to verify no regressions**

Run:
```bash
uv run pytest tests/unit/test_library.py -v
```

Expected: All tests pass (methods exist but aren't used yet).

**Step 5: Commit**

```bash
git add src/local_library/core/library.py
git commit -m "feat(library): add _find_extractor dispatch method

Returns first extractor that can handle the file.
Raises EXTRACTION_UNSUPPORTED_FORMAT if no handler matches."
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add unit tests for dispatch methods

**Files:**
- Modify: `tests/unit/test_library.py`

**Step 1: Add imports for the new error code**

The imports at the top already include `AcquisitionError` and `ErrorCode`. Add `ExtractionError` to the imports:

```python
from local_library.core.errors import AcquisitionError, ErrorCode, ExtractionError, LookupError
```

**Step 2: Add test class for dispatch methods**

Add a new test class after `TestLibraryInit` and before `TestLibraryAdd`:

```python
class TestLibraryDispatch:
    """Tests for Library dispatch methods."""

    @pytest.fixture
    def library(self, temp_dir: Path) -> Library:
        """Provide an initialized Library for testing."""
        return Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
        )

    def test_find_acquirer_returns_handler_for_pdf(
        self, library: Library, temp_dir: Path
    ) -> None:
        """_find_acquirer should return handler for supported PDF path."""
        pdf_path = temp_dir / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test")

        acquirer = library._find_acquirer(str(pdf_path))

        assert acquirer is not None
        assert acquirer.can_handle(str(pdf_path))

    def test_find_acquirer_raises_for_unsupported_source(self, library: Library) -> None:
        """_find_acquirer should raise for unsupported source type."""
        with pytest.raises(AcquisitionError) as exc_info:
            library._find_acquirer("https://example.com/doc.html")

        assert exc_info.value.code == ErrorCode.ACQUISITION_UNSUPPORTED_SOURCE

    def test_find_extractor_returns_handler_for_pdf(
        self, library: Library, temp_dir: Path
    ) -> None:
        """_find_extractor should return handler for PDF file."""
        pdf_path = temp_dir / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 test")

        extractor = library._find_extractor(pdf_path)

        assert extractor is not None
        assert extractor.can_handle(pdf_path)

    def test_find_extractor_raises_for_unsupported_format(
        self, library: Library, temp_dir: Path
    ) -> None:
        """_find_extractor should raise for unsupported file format."""
        txt_path = temp_dir / "test.txt"
        txt_path.write_text("plain text")

        with pytest.raises(ExtractionError) as exc_info:
            library._find_extractor(txt_path)

        assert exc_info.value.code == ErrorCode.EXTRACTION_UNSUPPORTED_FORMAT
```

**Step 3: Run the new tests**

Run:
```bash
uv run pytest tests/unit/test_library.py::TestLibraryDispatch -v
```

Expected: All 4 tests pass.

**Step 4: Run all library tests**

Run:
```bash
uv run pytest tests/unit/test_library.py -v
```

Expected: All tests pass.

**Step 5: Commit**

```bash
git add tests/unit/test_library.py
git commit -m "test(library): add tests for dispatch methods

Tests _find_acquirer and _find_extractor for both success
and failure cases."
```
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

---

**Phase 2 complete when:**
- `_find_acquirer()` and `_find_extractor()` methods exist
- Both methods return correct handler for supported types
- Both methods raise appropriate errors for unsupported types
- All existing tests still pass
- New dispatch tests pass
