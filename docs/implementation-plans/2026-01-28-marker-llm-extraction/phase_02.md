## Phase 2: Library Configuration Passthrough

This phase adds the `pdf_llm_enabled` parameter to the Library constructor and passes it to PdfExtractor when creating the default extractors list.

**Pattern followed:** Mirrors the existing `text_extraction_llm_enabled` pattern already in Library.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add pdf_llm_enabled parameter to Library constructor

**Files:**
- Modify: `src/local_library/core/library.py:60-84` (constructor signature and docstring)

**Step 1: Update the constructor signature**

Open `src/local_library/core/library.py` and add the `pdf_llm_enabled` parameter to the `__init__` method. Insert it after `text_extraction_confidence_threshold`:

```python
def __init__(
    self,
    db_path: Path | None = None,
    storage_dir: Path | None = None,
    extracted_dir: Path | None = None,
    acquirers: list[ContentAcquirer] | None = None,
    extractors: list[ContentExtractor] | None = None,
    text_extraction_enabled: bool = True,
    text_extraction_llm_enabled: bool = False,
    text_extraction_llm_model: str = "gemini/gemini-2.0-flash",
    text_extraction_confidence_threshold: float = 0.7,
    pdf_llm_enabled: bool = False,
) -> None:
    """Initialize the library.

    Args:
        db_path: Path to SQLite database (default: platformdirs user data)
        storage_dir: Directory for content-addressable storage (default: platformdirs)
        extracted_dir: Directory for extracted markdown (default: platformdirs)
        acquirers: List of content acquirers (default: [FileAcquirer()])
        extractors: List of content extractors (default: [PdfExtractor(lazy_load=True)])
        text_extraction_enabled: Whether to extract metadata from text (default: True)
        text_extraction_llm_enabled: Whether to use LLM fallback (default: False)
        text_extraction_llm_model: LLM model for fallback (default: "gemini-2.0-flash")
        text_extraction_confidence_threshold: Confidence threshold (default: 0.7)
        pdf_llm_enabled: Whether to use Marker's LLM-enhanced PDF extraction (default: False).
                        Enables better table, math, and image handling. Requires GEMINI_API_KEY.
    """
```

**Step 2: Verify syntax is correct**

Run: `uv run python -c "from local_library.core.library import Library; print('OK')"`

Expected: `OK`

**Step 3: Commit**

```bash
git add src/local_library/core/library.py
git commit -m "$(cat <<'EOF'
feat(library): add pdf_llm_enabled parameter to constructor

Preparation for passing PDF LLM extraction config to PdfExtractor.
Parameter accepted but not yet used.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Pass pdf_llm_enabled to PdfExtractor in default extractors

**Files:**
- Modify: `src/local_library/core/library.py:94-96` (default extractors initialization)

**Step 1: Update the default extractors initialization**

Find the line that creates the default extractors list (around line 94-96):

```python
self._extractors: list[ContentExtractor] = (
    extractors if extractors is not None else [PdfExtractor(lazy_load=True)]
)
```

Replace it with:

```python
self._extractors: list[ContentExtractor] = (
    extractors
    if extractors is not None
    else [PdfExtractor(lazy_load=True, llm_enabled=pdf_llm_enabled)]
)
```

**Step 2: Verify syntax and import**

Run: `uv run python -c "from local_library.core.library import Library; Library(pdf_llm_enabled=True); print('OK')"`

Expected: `OK`

**Step 3: Commit**

```bash
git add src/local_library/core/library.py
git commit -m "$(cat <<'EOF'
feat(library): pass pdf_llm_enabled to PdfExtractor

When using default extractors, pdf_llm_enabled is now passed through
to PdfExtractor. Custom extractors (passed via constructor) are
unaffected.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add tests for Library pdf_llm_enabled passthrough

**Files:**
- Modify: `tests/unit/test_library.py`

**Step 1: Add test class for PDF LLM configuration**

Add the following test class at the end of the file (after `TestLibraryDelete`):

```python
class TestLibraryPdfLLMConfiguration:
    """Tests for Library PDF LLM extraction configuration."""

    def test_pdf_llm_enabled_default_false(self, temp_dir: Path) -> None:
        """Library should default to pdf_llm_enabled=False."""
        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
        ) as lib:
            # Check the default PdfExtractor was created with llm_enabled=False
            assert len(lib._extractors) == 1
            assert isinstance(lib._extractors[0], PdfExtractor)
            assert lib._extractors[0]._llm_enabled is False

    def test_pdf_llm_enabled_passed_to_extractor(self, temp_dir: Path) -> None:
        """Library should pass pdf_llm_enabled=True to PdfExtractor."""
        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            pdf_llm_enabled=True,
        ) as lib:
            # Check the PdfExtractor was created with llm_enabled=True
            assert len(lib._extractors) == 1
            assert isinstance(lib._extractors[0], PdfExtractor)
            assert lib._extractors[0]._llm_enabled is True

    def test_custom_extractors_not_affected_by_pdf_llm_enabled(
        self, temp_dir: Path
    ) -> None:
        """Custom extractors should not be affected by pdf_llm_enabled."""
        # Create a custom extractor with llm_enabled=False
        custom_extractor = PdfExtractor(lazy_load=True, llm_enabled=False)

        with Library(
            db_path=temp_dir / "test.db",
            storage_dir=temp_dir / "storage",
            extracted_dir=temp_dir / "extracted",
            extractors=[custom_extractor],
            pdf_llm_enabled=True,  # Should be ignored
        ) as lib:
            # Custom extractor should be used as-is
            assert lib._extractors == [custom_extractor]
            assert lib._extractors[0]._llm_enabled is False
```

**Step 2: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_library.py::TestLibraryPdfLLMConfiguration -v`

Expected: All 3 tests pass

**Step 3: Commit**

```bash
git add tests/unit/test_library.py
git commit -m "$(cat <<'EOF'
test(library): add tests for pdf_llm_enabled passthrough

Tests verify:
- pdf_llm_enabled defaults to False
- pdf_llm_enabled=True passed to default PdfExtractor
- Custom extractors not affected by pdf_llm_enabled

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_4 -->
### Task 4: Run full test suite and verify no regressions

**Files:**
- None (verification only)

**Step 1: Run ruff check**

Run: `uv run ruff check src/local_library/core/library.py tests/unit/test_library.py`

Expected: No linting errors

**Step 2: Run ruff format check**

Run: `uv run ruff format --check src/local_library/core/library.py tests/unit/test_library.py`

Expected: No formatting issues (or run `uv run ruff format` to fix)

**Step 3: Run the full unit test suite**

Run: `uv run pytest tests/unit/ -v`

Expected: All tests pass

**Step 4: Commit any formatting fixes if needed**

If ruff format made changes:

```bash
git add -A
git commit -m "$(cat <<'EOF'
style: apply ruff formatting

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```
<!-- END_TASK_4 -->

---

## Phase 2 Completion Checklist

- [ ] Library constructor accepts `pdf_llm_enabled` parameter
- [ ] Default PdfExtractor created with `llm_enabled=pdf_llm_enabled`
- [ ] Custom extractors (passed via constructor) are not affected
- [ ] All new tests pass
- [ ] No regressions in existing tests
- [ ] Code passes ruff check and format
