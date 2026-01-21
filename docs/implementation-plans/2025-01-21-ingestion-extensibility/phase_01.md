# Ingestion Layer Extensibility Implementation Plan

**Goal:** Refactor the ingestion layer to support multiple content types through a registry-based dispatch mechanism.

**Architecture:** Library holds lists of registered handlers (acquirers, extractors) and iterates through them calling `can_handle()` until one returns `True`. Handler lists are injected at construction time with sensible defaults.

**Tech Stack:** Python 3.10+, pytest, SQLite

**Scope:** 6 phases from original design (all phases)

**Codebase verified:** 2025-01-21

---

## Phase 1: Add New Error Codes

**Goal:** Extend error hierarchy for dispatch failures.

**Codebase verification findings:**
- ✓ `src/local_library/core/errors.py` exists with ErrorCode enum (lines 9-34)
- ✓ ErrorCode enum is `(str, Enum)` for string values
- ✗ Missing: `ACQUISITION_UNSUPPORTED_SOURCE` and `EXTRACTION_UNSUPPORTED_FORMAT`

---

<!-- START_TASK_1 -->
### Task 1: Add ACQUISITION_UNSUPPORTED_SOURCE error code

**Files:**
- Modify: `src/local_library/core/errors.py:16` (after ACQUISITION_COPY_FAILED)

**Step 1: Add the new error code**

In `src/local_library/core/errors.py`, add a new line after line 16 (`ACQUISITION_COPY_FAILED`):

```python
    ACQUISITION_UNSUPPORTED_SOURCE = "ACQUISITION_UNSUPPORTED_SOURCE"
```

The acquisition errors section should now read:

```python
    # Acquisition errors
    ACQUISITION_FILE_NOT_FOUND = "ACQUISITION_FILE_NOT_FOUND"
    ACQUISITION_FILE_NOT_READABLE = "ACQUISITION_FILE_NOT_READABLE"
    ACQUISITION_INVALID_FORMAT = "ACQUISITION_INVALID_FORMAT"
    ACQUISITION_COPY_FAILED = "ACQUISITION_COPY_FAILED"
    ACQUISITION_UNSUPPORTED_SOURCE = "ACQUISITION_UNSUPPORTED_SOURCE"
```

**Step 2: Verify the code imports correctly**

Run:
```bash
uv run python -c "from local_library.core.errors import ErrorCode; print(ErrorCode.ACQUISITION_UNSUPPORTED_SOURCE)"
```

Expected output:
```
ACQUISITION_UNSUPPORTED_SOURCE
```

**Step 3: Commit**

```bash
git add src/local_library/core/errors.py
git commit -m "feat(errors): add ACQUISITION_UNSUPPORTED_SOURCE error code

For dispatch failures when no acquirer can handle the source."
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add EXTRACTION_UNSUPPORTED_FORMAT error code

**Files:**
- Modify: `src/local_library/core/errors.py:21` (after EXTRACTION_EMPTY_OUTPUT)

**Step 1: Add the new error code**

In `src/local_library/core/errors.py`, add a new line after line 21 (`EXTRACTION_EMPTY_OUTPUT`):

```python
    EXTRACTION_UNSUPPORTED_FORMAT = "EXTRACTION_UNSUPPORTED_FORMAT"
```

The extraction errors section should now read:

```python
    # Extraction errors
    EXTRACTION_MARKER_CRASH = "EXTRACTION_MARKER_CRASH"
    EXTRACTION_TIMEOUT = "EXTRACTION_TIMEOUT"
    EXTRACTION_EMPTY_OUTPUT = "EXTRACTION_EMPTY_OUTPUT"
    EXTRACTION_UNSUPPORTED_FORMAT = "EXTRACTION_UNSUPPORTED_FORMAT"
```

**Step 2: Verify the code imports correctly**

Run:
```bash
uv run python -c "from local_library.core.errors import ErrorCode; print(ErrorCode.EXTRACTION_UNSUPPORTED_FORMAT)"
```

Expected output:
```
EXTRACTION_UNSUPPORTED_FORMAT
```

**Step 3: Run existing tests to ensure no regressions**

Run:
```bash
uv run pytest tests/unit/test_errors.py -v
```

Expected: All tests pass.

**Step 4: Commit**

```bash
git add src/local_library/core/errors.py
git commit -m "feat(errors): add EXTRACTION_UNSUPPORTED_FORMAT error code

For dispatch failures when no extractor can handle the acquired content."
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add unit tests for new error codes

**Files:**
- Modify: `tests/unit/test_errors.py`

**Step 1: Write tests for the new error codes**

Add the following test methods to the `TestErrorCode` class in `tests/unit/test_errors.py`:

```python
    def test_acquisition_unsupported_source_is_string(self) -> None:
        """ACQUISITION_UNSUPPORTED_SOURCE should have string value."""
        assert ErrorCode.ACQUISITION_UNSUPPORTED_SOURCE == "ACQUISITION_UNSUPPORTED_SOURCE"
        assert isinstance(ErrorCode.ACQUISITION_UNSUPPORTED_SOURCE, str)

    def test_extraction_unsupported_format_is_string(self) -> None:
        """EXTRACTION_UNSUPPORTED_FORMAT should have string value."""
        assert ErrorCode.EXTRACTION_UNSUPPORTED_FORMAT == "EXTRACTION_UNSUPPORTED_FORMAT"
        assert isinstance(ErrorCode.EXTRACTION_UNSUPPORTED_FORMAT, str)
```

**Step 2: Run the new tests**

Run:
```bash
uv run pytest tests/unit/test_errors.py -v -k "unsupported"
```

Expected: Both new tests pass.

**Step 3: Run all error tests**

Run:
```bash
uv run pytest tests/unit/test_errors.py -v
```

Expected: All tests pass.

**Step 4: Commit**

```bash
git add tests/unit/test_errors.py
git commit -m "test(errors): add tests for new dispatch error codes"
```
<!-- END_TASK_3 -->

---

**Phase 1 complete when:**
- New error codes exist and can be imported
- All existing tests pass
- New error codes have unit tests
