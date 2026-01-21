# Phase 5: Wire Dispatch into Library.add()

**Goal:** Replace hardcoded handler usage with dispatch in Library.add().

**Codebase verification findings:**
- ✓ `Library.add()` at lines 97-216
- ✓ Currently uses `self._acquirer.can_handle()` at line 123
- ✓ Currently uses `self._acquirer.validate()` at line 132
- ✓ Currently uses `self._acquirer.acquire()` at line 154
- ✓ Currently uses `self._extractor.extract_and_validate()` at line 185
- ✓ Dispatch methods `_find_acquirer()` and `_find_extractor()` added in Phase 2
- ✓ Handler lists `_acquirers` and `_extractors` added in Phase 3

**Key changes:**
1. Use `_find_acquirer()` instead of direct `_acquirer` access
2. Use `_find_extractor()` after acquisition to validate extraction is possible
3. Handle "no extractor" case by marking record FAILED (preserving acquired file)

---

<!-- START_TASK_1 -->
### Task 1: Update add() to use _find_acquirer()

**Files:**
- Modify: `src/local_library/core/library.py`

**Step 1: Replace acquirer access with dispatch**

In the `add()` method, replace the section that checks can_handle and validates (lines 122-137) with dispatch-based approach:

Find this code block:
```python
        # Check if we can handle this source
        if not self._acquirer.can_handle(source):
            raise AcquisitionError(
                f"unsupported source type: {source}",
                ErrorCode.ACQUISITION_INVALID_FORMAT,
                details={"source": source},
            )

        # Validate source (unless force mode)
        try:
            self._acquirer.validate(source)
```

Replace with:
```python
        # Find an acquirer that can handle this source
        acquirer = self._find_acquirer(source)

        # Validate source (unless force mode)
        try:
            acquirer.validate(source)
```

**Step 2: Update the acquire() call**

Find the line that calls acquire (around line 154):
```python
            acquisition = self._acquirer.acquire(source, temp_path)
```

Replace with:
```python
            acquisition = acquirer.acquire(source, temp_path)
```

**Step 3: Verify syntax is correct**

Run:
```bash
uv run python -c "from local_library.core.library import Library; print('OK')"
```

Expected output: `OK`

**Step 4: Commit**

```bash
git add src/local_library/core/library.py
git commit -m "refactor(library): use _find_acquirer dispatch in add()

Replaces direct _acquirer access with dispatch-based handler selection.
Error code changes from ACQUISITION_INVALID_FORMAT to ACQUISITION_UNSUPPORTED_SOURCE
when no handler can process the source."
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add extractor validation after acquisition

**Files:**
- Modify: `src/local_library/core/library.py`

**Step 1: Add extractor lookup after acquisition, before storage move**

After the duplicate-by-hash check and before moving to storage, add extractor validation. Find this section:

```python
            # Check for duplicate by content hash
            existing = get_document_by_hash(self._conn, acquisition.content_hash)
            if existing:
                return AddResult(
                    document=existing,
                    is_duplicate=True,
                    duplicate_reason="hash",
                )

            # Compute storage path and move file
```

Insert between them:
```python
            # Validate that an extractor can handle this content type
            # This is done early to fail fast before committing to storage
            try:
                extractor = self._find_extractor(Path(acquisition.temp_path))
            except ExtractionError:
                # No extractor available - we'll handle this after creating the record
                extractor = None

            # Compute storage path and move file
```

**Step 2: Update the extraction section to handle no-extractor case**

Find the extraction section that starts with:
```python
        # Extract text content
        try:
            result = self._extractor.extract_and_validate(storage_path)
```

Replace the entire extraction block (from `# Extract text content` to the end of the try/except) with:

```python
        # Extract text content (if extractor available)
        if extractor is None:
            # No extractor for this content type - mark as failed but preserve file
            doc = update_document_status(
                self._conn,
                doc.id,
                DocumentStatus.FAILED,
                error_message=f"no extractor can handle file type: {storage_path.suffix}",
                error_code=ErrorCode.EXTRACTION_UNSUPPORTED_FORMAT.value,
            )
            raise ExtractionError(
                f"no extractor can handle file: {storage_path}",
                ErrorCode.EXTRACTION_UNSUPPORTED_FORMAT,
                details={"file_path": str(storage_path)},
            )

        try:
            result = extractor.extract_and_validate(storage_path)

            # Write extracted markdown
            extracted_path = compute_storage_path(
                doc.content_hash,
                ".md",
                self._extracted_dir,
            )
            extracted_path.parent.mkdir(parents=True, exist_ok=True)
            extracted_path.write_text(result.text, encoding="utf-8")

            # Update record to ready
            doc = update_document_status(
                self._conn,
                doc.id,
                DocumentStatus.READY,
                extracted_path=str(extracted_path),
            )

        except (ExtractionError, QualityError) as e:
            # Update record to failed
            doc = update_document_status(
                self._conn,
                doc.id,
                DocumentStatus.FAILED,
                error_message=e.message,
                error_code=e.code.value,
            )
            # Re-raise so caller knows extraction failed
            raise

        return AddResult(document=doc)
```

**Step 3: Verify syntax is correct**

Run:
```bash
uv run python -c "from local_library.core.library import Library; print('OK')"
```

Expected output: `OK`

**Step 4: Commit**

```bash
git add src/local_library/core/library.py
git commit -m "refactor(library): use _find_extractor dispatch and handle no-extractor case

- Validates extractor availability after acquisition
- Creates FAILED record when no extractor matches (file preserved)
- Raises ExtractionError with EXTRACTION_UNSUPPORTED_FORMAT"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add tests for dispatch-based add() behavior

**Files:**
- Modify: `tests/unit/test_library.py`

**Step 1: Add test for unsupported source in TestLibraryAdd**

Update the existing `test_add_unsupported_format_raises` test in `TestLibraryAdd` to verify the new error code:

```python
    def test_add_unsupported_source_raises(self, library: Library) -> None:
        """add() should raise for sources no acquirer can handle."""
        # URL is not handled by FileAcquirer
        with pytest.raises(AcquisitionError) as exc_info:
            library.add("https://example.com/doc.pdf")

        assert exc_info.value.code == ErrorCode.ACQUISITION_UNSUPPORTED_SOURCE
```

**Step 2: Add test for no-extractor case**

Add a new test to `TestLibraryAdd`:

```python
    def test_add_unsupported_content_type_creates_failed_record(
        self, temp_dir: Path
    ) -> None:
        """add() should create failed record when no extractor can handle content."""
        # Create library with empty extractors list
        library = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            extractors=[],  # No extractors - nothing can be extracted
        )

        # Create a file that can be acquired but not extracted
        txt_file = temp_dir / "test.txt"
        txt_file.write_text("test content")

        with pytest.raises(ExtractionError) as exc_info:
            library.add(str(txt_file))

        assert exc_info.value.code == ErrorCode.EXTRACTION_UNSUPPORTED_FORMAT

        # Verify a failed record was created
        docs = library.list(status=DocumentStatus.FAILED)
        assert len(docs) == 1
        assert docs[0].error_code == ErrorCode.EXTRACTION_UNSUPPORTED_FORMAT.value

        # Verify the storage file was preserved
        storage_path = Path(docs[0].storage_path)
        assert storage_path.exists()

        library.close()
```

**Step 3: Add test verifying file preserved on extractor failure**

Add another test:

```python
    def test_add_preserves_file_when_no_extractor_available(
        self, temp_dir: Path
    ) -> None:
        """add() should preserve acquired file even when extraction fails."""
        # Create library with no extractors
        library = Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            extractors=[],
        )

        # Create file
        pdf_file = temp_dir / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 content")

        try:
            library.add(str(pdf_file))
        except ExtractionError:
            pass  # Expected

        # File should exist in storage
        docs = library.list()
        assert len(docs) == 1
        storage_file = Path(docs[0].storage_path)
        assert storage_file.exists()
        assert storage_file.read_bytes() == b"%PDF-1.4 content"

        library.close()
```

**Step 4: Run the new tests**

Run:
```bash
uv run pytest tests/unit/test_library.py::TestLibraryAdd -v -k "unsupported"
```

Expected: Tests pass.

**Step 5: Run all library tests**

Run:
```bash
uv run pytest tests/unit/test_library.py -v
```

Expected: All tests pass.

**Step 6: Commit**

```bash
git add tests/unit/test_library.py
git commit -m "test(library): add tests for dispatch-based add() behavior

- Test ACQUISITION_UNSUPPORTED_SOURCE for unhandled sources
- Test EXTRACTION_UNSUPPORTED_FORMAT creates failed record
- Test file preservation when no extractor available"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Run full test suite and fix any regressions

**Files:**
- Potentially multiple files if regressions found

**Step 1: Run unit tests**

Run:
```bash
uv run pytest tests/unit/ -v
```

Expected: All tests pass.

**Step 2: Run integration tests**

Run:
```bash
uv run pytest tests/integration/ -v
```

Expected: All tests pass.

**Step 3: Run full test suite**

Run:
```bash
uv run pytest -v
```

Expected: All tests pass.

**Step 4: If any tests fail, investigate and fix**

Common issues to watch for:
- Tests that expected `ACQUISITION_INVALID_FORMAT` may now get `ACQUISITION_UNSUPPORTED_SOURCE`
- Tests that patch `library._extractor` need updating (Phase 6 will address this)

**Step 5: Commit any fixes**

If fixes were needed:
```bash
git add -A
git commit -m "fix: address test regressions from dispatch refactoring"
```

If no fixes needed, skip this commit.
<!-- END_TASK_4 -->

---

**Phase 5 complete when:**
- Library.add() uses `_find_acquirer()` instead of `_acquirer`
- Library.add() validates extractor availability after acquisition
- No-extractor case creates FAILED record with file preserved
- All unit and integration tests pass
