# Phase 3: Refactor Library Constructor for Handler Injection

**Goal:** Allow handler lists to be injected while maintaining backward compatibility.

**Codebase verification findings:**
- ✓ Library.__init__() at lines 49-76 accepts db_path, storage_dir, extracted_dir
- ✓ Currently creates single instances: `_acquirer = FileAcquirer()` (line 68)
- ✓ Currently creates single instances: `_extractor = PdfExtractor(lazy_load=True)` (line 69)
- ✓ Dispatch methods from Phase 2 use `self._acquirer` and `self._extractor`

**Key change:** Convert `_acquirer` and `_extractor` to `_acquirers` and `_extractors` (lists), update dispatch methods to iterate, maintain backward-compatible defaults.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Add handler list parameters to Library.__init__()

**Files:**
- Modify: `src/local_library/core/library.py`

**Step 1: Update __init__ signature and docstring**

Replace the current `__init__` method (lines 49-76) with:

```python
    def __init__(
        self,
        db_path: Path | None = None,
        storage_dir: Path | None = None,
        extracted_dir: Path | None = None,
        acquirers: list[ContentAcquirer] | None = None,
        extractors: list[ContentExtractor] | None = None,
    ) -> None:
        """Initialize the library.

        Args:
            db_path: Path to SQLite database (default: platformdirs user data)
            storage_dir: Directory for content-addressable storage (default: platformdirs)
            extracted_dir: Directory for extracted markdown (default: platformdirs)
            acquirers: List of content acquirers (default: [FileAcquirer()])
            extractors: List of content extractors (default: [PdfExtractor(lazy_load=True)])
        """
        # Use defaults from config if not specified
        self._db_path = db_path or get_database_path()
        self._storage_dir = storage_dir or get_storage_dir()
        self._extracted_dir = extracted_dir or get_extracted_dir()

        # Initialize handler lists with defaults
        self._acquirers: list[ContentAcquirer] = (
            acquirers if acquirers is not None else [FileAcquirer()]
        )
        self._extractors: list[ContentExtractor] = (
            extractors if extractors is not None else [PdfExtractor(lazy_load=True)]
        )

        # Ensure directories exist
        ensure_directories()

        # Initialize database
        self._conn = get_connection(self._db_path)
        init_schema(self._conn)
```

**Step 2: Verify syntax is correct**

Run:
```bash
uv run python -c "from local_library.core.library import Library; print('OK')"
```

Expected output: `OK`

**Step 3: Commit**

```bash
git add src/local_library/core/library.py
git commit -m "feat(library): add acquirers/extractors list parameters to __init__

Allows handler injection while maintaining backward-compatible defaults.
- acquirers defaults to [FileAcquirer()]
- extractors defaults to [PdfExtractor(lazy_load=True)]"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update dispatch methods to iterate over lists

**Files:**
- Modify: `src/local_library/core/library.py`

**Step 1: Update `_find_acquirer()` to iterate over list**

Replace the `_find_acquirer` method with:

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
        for acquirer in self._acquirers:
            if acquirer.can_handle(source):
                return acquirer

        raise AcquisitionError(
            f"no acquirer can handle source: {source}",
            ErrorCode.ACQUISITION_UNSUPPORTED_SOURCE,
            details={"source": source},
        )
```

**Step 2: Update `_find_extractor()` to iterate over list**

Replace the `_find_extractor` method with:

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
        for extractor in self._extractors:
            if extractor.can_handle(file_path):
                return extractor

        raise ExtractionError(
            f"no extractor can handle file: {file_path}",
            ErrorCode.EXTRACTION_UNSUPPORTED_FORMAT,
            details={"file_path": str(file_path)},
        )
```

**Step 3: Verify the code works**

Run:
```bash
uv run python -c "from local_library.core.library import Library; print('OK')"
```

Expected output: `OK`

**Step 4: Commit**

```bash
git add src/local_library/core/library.py
git commit -m "refactor(library): update dispatch methods to iterate over handler lists

_find_acquirer and _find_extractor now iterate through their
respective lists instead of checking a single handler."
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add tests for handler injection

**Files:**
- Modify: `tests/unit/test_library.py`

**Step 1: Add imports for protocols**

Add these imports at the top of the test file:

```python
from local_library.ingestion.base import ContentAcquirer, ContentExtractor
from local_library.ingestion.file import FileAcquirer
from local_library.ingestion.pdf import PdfExtractor
```

**Step 2: Add tests to TestLibraryInit class**

Add these tests to the `TestLibraryInit` class:

```python
    def test_default_acquirers_includes_file_acquirer(self, temp_dir: Path) -> None:
        """Library should have FileAcquirer in default acquirers list."""
        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
        ) as lib:
            assert len(lib._acquirers) == 1
            assert isinstance(lib._acquirers[0], FileAcquirer)

    def test_default_extractors_includes_pdf_extractor(self, temp_dir: Path) -> None:
        """Library should have PdfExtractor in default extractors list."""
        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
        ) as lib:
            assert len(lib._extractors) == 1
            assert isinstance(lib._extractors[0], PdfExtractor)

    def test_custom_acquirers_override_defaults(self, temp_dir: Path) -> None:
        """Library should use custom acquirers when provided."""
        custom_acquirer = FileAcquirer()  # Could be any ContentAcquirer

        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            acquirers=[custom_acquirer],
        ) as lib:
            assert lib._acquirers == [custom_acquirer]

    def test_custom_extractors_override_defaults(self, temp_dir: Path) -> None:
        """Library should use custom extractors when provided."""
        custom_extractor = PdfExtractor(lazy_load=True)  # Could be any ContentExtractor

        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            extractors=[custom_extractor],
        ) as lib:
            assert lib._extractors == [custom_extractor]

    def test_empty_acquirers_list_is_valid(self, temp_dir: Path) -> None:
        """Library should accept empty acquirers list (all sources will fail)."""
        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            acquirers=[],
        ) as lib:
            assert lib._acquirers == []

    def test_empty_extractors_list_is_valid(self, temp_dir: Path) -> None:
        """Library should accept empty extractors list (all extractions will fail)."""
        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            extractors=[],
        ) as lib:
            assert lib._extractors == []
```

**Step 3: Run the new tests**

Run:
```bash
uv run pytest tests/unit/test_library.py::TestLibraryInit -v
```

Expected: All tests pass (8 total in TestLibraryInit now).

**Step 4: Run all library tests**

Run:
```bash
uv run pytest tests/unit/test_library.py -v
```

Expected: All tests pass.

**Step 5: Commit**

```bash
git add tests/unit/test_library.py
git commit -m "test(library): add tests for handler injection

Tests verify:
- Default acquirers/extractors are FileAcquirer/PdfExtractor
- Custom handlers override defaults
- Empty handler lists are valid"
```
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

---

**Phase 3 complete when:**
- Library accepts `acquirers` and `extractors` parameters
- Default behavior is identical to current implementation
- Dispatch methods iterate over lists
- Injection tests pass
- All existing tests still pass
