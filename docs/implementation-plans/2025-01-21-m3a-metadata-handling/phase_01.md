# M3a Metadata Handling Implementation Plan

**Goal:** Add metadata handling to the document ingestion pipeline with CSL-JSON validation, citekey generation, and indexed field extraction.

**Architecture:** MetadataHandler follows the existing handler pattern (stateless, pure transformation). It receives CSL-JSON input, validates against the official schema, generates citekeys, and extracts indexed fields. The handler slots between content extraction and storage in the Library.add() pipeline.

**Tech Stack:** Python 3.12, jsonschema (4.x), unidecode, pytest, SQLite

**Scope:** 6 phases from original design (phases 1-6)

**Codebase verified:** 2025-01-22

---

## Phase 1: Core Types and Error Codes

**Goal:** Add MetadataResult dataclass and metadata-related error codes.

**Testing approach:** This project uses pytest with real SQLite databases (not mocked). Tests follow Arrange-Act-Assert pattern with descriptive docstrings. Follow patterns in `tests/unit/test_models.py` and `tests/unit/test_errors.py`.

**Reference files:**
- `src/local_library/core/CLAUDE.md` - Core domain contracts
- `tests/unit/test_models.py` - Model testing patterns
- `tests/unit/test_errors.py` - Error testing patterns

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add metadata error codes to ErrorCode enum

**Files:**
- Modify: `src/local_library/core/errors.py:36-37` (after AMBIGUOUS_MATCH)

**Step 1: Add error codes**

Add these three error codes after line 37 (after `AMBIGUOUS_MATCH`):

```python
    # Metadata errors
    METADATA_INVALID_SCHEMA = "METADATA_INVALID_SCHEMA"
    METADATA_INVALID_TYPE = "METADATA_INVALID_TYPE"
    METADATA_CITEKEY_INVALID = "METADATA_CITEKEY_INVALID"
```

**Step 2: Verify import works**

Run:
```bash
uv run python -c "from local_library.core.errors import ErrorCode; print(ErrorCode.METADATA_INVALID_SCHEMA)"
```

Expected: `METADATA_INVALID_SCHEMA`

**Step 3: Commit**

```bash
git add src/local_library/core/errors.py
git commit -m "feat(core): add metadata error codes to ErrorCode enum

Add METADATA_INVALID_SCHEMA, METADATA_INVALID_TYPE, and
METADATA_CITEKEY_INVALID for M3a metadata handling.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add MetadataError exception class

**Files:**
- Modify: `src/local_library/core/errors.py:84` (after LookupError class)

**Step 1: Add MetadataError class**

Add after the `LookupError` class (after line 84):

```python


class MetadataError(LocalLibraryError):
    """Error during metadata validation or processing."""

    pass
```

**Step 2: Update __init__.py exports**

Check if `src/local_library/core/__init__.py` exists and update exports. If it exists, add `MetadataError` to the exports.

Run to verify:
```bash
uv run python -c "from local_library.core.errors import MetadataError; print(MetadataError.__bases__)"
```

Expected: `(<class 'local_library.core.errors.LocalLibraryError'>,)`

**Step 3: Commit**

```bash
git add src/local_library/core/errors.py
git commit -m "feat(core): add MetadataError exception class

Follows existing exception hierarchy pattern for metadata validation failures.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add tests for metadata error codes and MetadataError

**Files:**
- Modify: `tests/unit/test_errors.py` (add new test class at end)

**Step 1: Add test class**

Add at the end of `tests/unit/test_errors.py`:

```python


class TestMetadataErrorCodes:
    """Tests for metadata-related error codes."""

    def test_metadata_invalid_schema_is_string(self) -> None:
        """METADATA_INVALID_SCHEMA should have string value."""
        assert ErrorCode.METADATA_INVALID_SCHEMA == "METADATA_INVALID_SCHEMA"
        assert isinstance(ErrorCode.METADATA_INVALID_SCHEMA, str)

    def test_metadata_invalid_type_is_string(self) -> None:
        """METADATA_INVALID_TYPE should have string value."""
        assert ErrorCode.METADATA_INVALID_TYPE == "METADATA_INVALID_TYPE"
        assert isinstance(ErrorCode.METADATA_INVALID_TYPE, str)

    def test_metadata_citekey_invalid_is_string(self) -> None:
        """METADATA_CITEKEY_INVALID should have string value."""
        assert ErrorCode.METADATA_CITEKEY_INVALID == "METADATA_CITEKEY_INVALID"
        assert isinstance(ErrorCode.METADATA_CITEKEY_INVALID, str)


class TestMetadataError:
    """Tests for MetadataError exception class."""

    def test_metadata_error_inherits_from_base(self) -> None:
        """MetadataError should inherit from LocalLibraryError."""
        from local_library.core.errors import MetadataError

        error = MetadataError("invalid schema", ErrorCode.METADATA_INVALID_SCHEMA)

        assert isinstance(error, LocalLibraryError)
        assert isinstance(error, MetadataError)

    def test_metadata_error_stores_message_and_code(self) -> None:
        """MetadataError should store message and code."""
        from local_library.core.errors import MetadataError

        error = MetadataError(
            "missing type field",
            ErrorCode.METADATA_INVALID_TYPE,
            details={"field": "type"},
        )

        assert error.message == "missing type field"
        assert error.code == ErrorCode.METADATA_INVALID_TYPE
        assert error.details == {"field": "type"}

    def test_can_catch_metadata_error_as_base(self) -> None:
        """Should be able to catch MetadataError as LocalLibraryError."""
        from local_library.core.errors import MetadataError

        with pytest.raises(LocalLibraryError):
            raise MetadataError("test", ErrorCode.METADATA_INVALID_SCHEMA)
```

**Step 2: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/unit/test_errors.py -v
```

Expected: All tests pass, including the new `TestMetadataErrorCodes` and `TestMetadataError` classes.

**Step 3: Commit**

```bash
git add tests/unit/test_errors.py
git commit -m "test(core): add tests for metadata error codes and MetadataError

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-6) -->

<!-- START_TASK_4 -->
### Task 4: Add MetadataResult dataclass

**Files:**
- Modify: `src/local_library/core/models.py:142` (after AddResult class)

**Step 1: Add MetadataResult dataclass**

Add after the `AddResult` class (after line 142):

```python


@dataclass(frozen=True)
class MetadataResult:
    """Result of processing metadata through MetadataHandler.

    Contains validated CSL-JSON, generated citekey, extracted indexed fields,
    and any validation warnings for non-fatal issues.
    """

    csl_json: dict[str, Any]  # Validated CSL-JSON metadata
    citekey: str  # Generated or provided citation key
    title: str | None = None  # Extracted title for indexing
    authors: str | None = None  # Formatted author string for indexing
    issued_date: str | None = None  # ISO date or year for indexing
    validation_warnings: tuple[str, ...] = ()  # Non-fatal validation issues

    # Structured data for future use (e.g., normalized authors table)
    author_list: tuple[str, ...] = ()  # Individual author names

    @classmethod
    def create(
        cls,
        csl_json: dict[str, Any],
        citekey: str,
        title: str | None = None,
        authors: str | None = None,
        issued_date: str | None = None,
        validation_warnings: list[str] | None = None,
        author_list: list[str] | None = None,
    ) -> "MetadataResult":
        """Create a MetadataResult with proper tuple conversion."""
        return cls(
            csl_json=csl_json,
            citekey=citekey,
            title=title,
            authors=authors,
            issued_date=issued_date,
            validation_warnings=tuple(validation_warnings or []),
            author_list=tuple(author_list or []),
        )
```

**Step 2: Verify import works**

Run:
```bash
uv run python -c "from local_library.core.models import MetadataResult; print(MetadataResult.__dataclass_fields__.keys())"
```

Expected: `dict_keys(['csl_json', 'citekey', 'title', 'authors', 'issued_date', 'validation_warnings', 'author_list'])`

**Step 3: Commit**

```bash
git add src/local_library/core/models.py
git commit -m "feat(core): add MetadataResult dataclass

Frozen dataclass holding processed metadata: validated CSL-JSON,
generated citekey, extracted indexed fields, and validation warnings.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Add tests for MetadataResult

**Files:**
- Modify: `tests/unit/test_models.py` (add new test class at end)

**Step 1: Add import**

Update the imports at the top of `tests/unit/test_models.py` to include `MetadataResult`:

```python
from local_library.core.models import (
    AcquisitionResult,
    AddResult,
    Document,
    DocumentStatus,
    ExtractionResult,
    MetadataResult,
)
```

**Step 2: Add test class**

Add at the end of `tests/unit/test_models.py`:

```python


class TestMetadataResult:
    """Tests for MetadataResult dataclass."""

    def test_stores_required_fields(self) -> None:
        """MetadataResult should store csl_json and citekey."""
        csl = {"type": "article-journal", "title": "Test Article"}
        result = MetadataResult(csl_json=csl, citekey="Smith2020Test")

        assert result.csl_json == csl
        assert result.citekey == "Smith2020Test"

    def test_optional_fields_have_defaults(self) -> None:
        """Optional fields should default to None or empty tuples."""
        csl = {"type": "book", "title": "Test Book"}
        result = MetadataResult(csl_json=csl, citekey="Author2021")

        assert result.title is None
        assert result.authors is None
        assert result.issued_date is None
        assert result.validation_warnings == ()
        assert result.author_list == ()

    def test_metadata_result_is_frozen(self) -> None:
        """MetadataResult should be immutable."""
        csl = {"type": "article", "title": "Test"}
        result = MetadataResult(csl_json=csl, citekey="Test2020")

        with pytest.raises(AttributeError):
            result.citekey = "NewKey"  # type: ignore[misc]

    def test_create_factory_converts_lists_to_tuples(self) -> None:
        """create() factory should convert lists to tuples for immutability."""
        csl = {"type": "article-journal", "title": "Test"}
        result = MetadataResult.create(
            csl_json=csl,
            citekey="Smith2020",
            title="Test Article",
            authors="Smith, J.",
            validation_warnings=["missing abstract"],
            author_list=["Smith, John"],
        )

        assert isinstance(result.validation_warnings, tuple)
        assert result.validation_warnings == ("missing abstract",)
        assert isinstance(result.author_list, tuple)
        assert result.author_list == ("Smith, John",)

    def test_create_factory_handles_none_lists(self) -> None:
        """create() factory should handle None for list parameters."""
        csl = {"type": "book"}
        result = MetadataResult.create(csl_json=csl, citekey="Test2020")

        assert result.validation_warnings == ()
        assert result.author_list == ()

    def test_stores_extracted_fields(self) -> None:
        """MetadataResult should store all extracted indexed fields."""
        csl = {
            "type": "article-journal",
            "title": "Attention Is All You Need",
            "author": [{"family": "Vaswani", "given": "A."}],
            "issued": {"date-parts": [[2017]]},
        }
        result = MetadataResult.create(
            csl_json=csl,
            citekey="Vaswani2017Attention",
            title="Attention Is All You Need",
            authors="Vaswani, A.",
            issued_date="2017",
            author_list=["Vaswani, A."],
        )

        assert result.title == "Attention Is All You Need"
        assert result.authors == "Vaswani, A."
        assert result.issued_date == "2017"
        assert result.author_list == ("Vaswani, A.",)
```

**Step 2: Run tests to verify they pass**

Run:
```bash
uv run pytest tests/unit/test_models.py::TestMetadataResult -v
```

Expected: All 6 tests pass.

**Step 3: Commit**

```bash
git add tests/unit/test_models.py
git commit -m "test(core): add tests for MetadataResult dataclass

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Run full test suite and verify Phase 1 complete

**Files:** None (verification only)

**Step 1: Run full test suite**

Run:
```bash
uv run pytest -v
```

Expected: All tests pass (existing + new tests for error codes, MetadataError, MetadataResult).

**Step 2: Verify lint passes**

Run:
```bash
uv run ruff check src/local_library/core/errors.py src/local_library/core/models.py tests/unit/test_errors.py tests/unit/test_models.py
```

Expected: No errors.

**Step 3: Commit phase completion marker (optional)**

If any lint or formatting issues were fixed, commit them:

```bash
git add -A
git commit -m "chore: Phase 1 complete - core types and error codes

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_6 -->

<!-- END_SUBCOMPONENT_B -->

---

## Phase 1 Completion Criteria

- [ ] ErrorCode enum includes METADATA_INVALID_SCHEMA, METADATA_INVALID_TYPE, METADATA_CITEKEY_INVALID
- [ ] MetadataError exception class exists and inherits from LocalLibraryError
- [ ] MetadataResult frozen dataclass exists with csl_json, citekey, and indexed fields
- [ ] MetadataResult.create() factory method converts lists to tuples
- [ ] All unit tests pass
- [ ] Lint passes
