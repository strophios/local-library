# M3b Text-Based Metadata Extraction Implementation Plan

**Goal:** Implement automatic metadata extraction from PDF text for documents without explicit bibliographic information

**Architecture:** Hybrid extraction with heuristic-first processing and LLM fallback. Per-field confidence scoring enables graceful degradation via NEEDS_REVIEW status.

**Tech Stack:** Python 3.10+, nameparser, litellm, existing jsonschema/unidecode

**Scope:** 8 phases from original design (phases 1-8)

**Codebase verified:** 2025-01-24

---

## Phase 1: Data Types and Status Extension

**Goal:** Add new types for extraction results and extend DocumentStatus with NEEDS_REVIEW.

This phase establishes the foundational data types that all subsequent phases depend on. The types follow the project's established frozen dataclass pattern.

**Reference documentation:**
- `src/local_library/core/CLAUDE.md` - Core domain contracts
- `src/local_library/ingestion/CLAUDE.md` - Ingestion domain contracts

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add NEEDS_REVIEW to DocumentStatus enum

**Files:**
- Modify: `src/local_library/core/models.py:13-18`

**Step 1: Add NEEDS_REVIEW status**

In `src/local_library/core/models.py`, locate the `DocumentStatus` enum (lines 13-18) and add the new status:

```python
class DocumentStatus(str, Enum):
    """Lifecycle status of a document record."""

    PENDING = "pending"  # Created, not yet processed
    READY = "ready"  # Extraction complete, searchable
    FAILED = "failed"  # Extraction failed, needs retry or manual intervention
    NEEDS_REVIEW = "needs_review"  # Extraction succeeded but confidence is low
```

**Step 2: Verify existing tests still pass**

Run:
```bash
uv run pytest tests/unit/test_models.py -v
```

Expected: All existing tests pass (the new status doesn't break existing code).

**Step 3: Commit**

```bash
git add src/local_library/core/models.py
git commit -m "$(cat <<'EOF'
feat(models): add NEEDS_REVIEW status for low-confidence extractions

Part of M3b text-based metadata extraction. Documents with extracted
metadata below confidence threshold will use this status.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add FieldExtraction and TextExtractionResult types

**Files:**
- Modify: `src/local_library/core/models.py` (append after MetadataResult class, around line 186)
- Test: `tests/unit/test_models.py`

**Step 1: Write test for FieldExtraction**

Add to `tests/unit/test_models.py`:

```python
class TestFieldExtraction:
    """Tests for FieldExtraction dataclass."""

    def test_field_extraction_is_frozen(self) -> None:
        """FieldExtraction should be immutable."""
        from local_library.core.models import FieldExtraction

        field = FieldExtraction(
            value="Test Title",
            confidence=0.85,
            source="heuristic",
            alternatives=("Alt Title",),
            reasoning="First line of document",
        )

        with pytest.raises(AttributeError):
            field.value = "Changed"  # type: ignore[misc]

    def test_field_extraction_with_none_value(self) -> None:
        """FieldExtraction should allow None value for missing fields."""
        from local_library.core.models import FieldExtraction

        field = FieldExtraction(
            value=None,
            confidence=0.0,
            source="heuristic",
            alternatives=(),
            reasoning="No candidates found",
        )

        assert field.value is None
        assert field.confidence == 0.0

    def test_field_extraction_confidence_bounds(self) -> None:
        """FieldExtraction confidence should be between 0.0 and 1.0."""
        from local_library.core.models import FieldExtraction

        # Valid bounds
        low = FieldExtraction(
            value="x", confidence=0.0, source="heuristic", alternatives=(), reasoning=""
        )
        high = FieldExtraction(
            value="x", confidence=1.0, source="heuristic", alternatives=(), reasoning=""
        )

        assert low.confidence == 0.0
        assert high.confidence == 1.0
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/unit/test_models.py::TestFieldExtraction -v
```

Expected: FAIL with "cannot import name 'FieldExtraction'"

**Step 3: Implement FieldExtraction**

Add to `src/local_library/core/models.py` after the `MetadataResult` class (around line 186):

```python
@dataclass(frozen=True)
class FieldExtraction:
    """Result of extracting a single metadata field.

    Captures the extracted value along with confidence scoring and provenance
    information. Used by TextMetadataExtractor for per-field extraction results.

    Attributes:
        value: Extracted value, or None if field could not be extracted
        confidence: Confidence score from 0.0 to 1.0 (heuristic confidence,
                   preserved even if LLM provided the value)
        source: Origin of the value - "heuristic" or "llm"
        alternatives: Other candidates that were considered
        reasoning: Explanation of why this value was chosen
    """

    value: str | None
    confidence: float
    source: str  # "heuristic" | "llm"
    alternatives: tuple[str, ...]
    reasoning: str
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/unit/test_models.py::TestFieldExtraction -v
```

Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/local_library/core/models.py tests/unit/test_models.py
git commit -m "$(cat <<'EOF'
feat(models): add FieldExtraction dataclass for per-field extraction results

Captures extracted value, confidence score, source provenance, alternatives
considered, and reasoning. Foundation for M3b metadata extraction.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add TextExtractionResult type

**Files:**
- Modify: `src/local_library/core/models.py` (append after FieldExtraction)
- Test: `tests/unit/test_models.py`

**Step 1: Write test for TextExtractionResult**

Add to `tests/unit/test_models.py`:

```python
class TestTextExtractionResult:
    """Tests for TextExtractionResult dataclass."""

    def test_text_extraction_result_is_frozen(self) -> None:
        """TextExtractionResult should be immutable."""
        from local_library.core.models import FieldExtraction, TextExtractionResult

        title = FieldExtraction(
            value="Test", confidence=0.9, source="heuristic", alternatives=(), reasoning=""
        )
        date = FieldExtraction(
            value="2023", confidence=0.8, source="heuristic", alternatives=(), reasoning=""
        )
        doc_type = FieldExtraction(
            value="article-journal",
            confidence=0.7,
            source="heuristic",
            alternatives=(),
            reasoning="",
        )

        result = TextExtractionResult(
            title=title,
            authors=(),
            date=date,
            doc_type=doc_type,
            overall_confidence=0.7,
            needs_review=False,
            review_reasons=(),
        )

        with pytest.raises(AttributeError):
            result.title = title  # type: ignore[misc]

    def test_text_extraction_result_overall_confidence_from_minimum(self) -> None:
        """overall_confidence should be the minimum of field confidences."""
        from local_library.core.models import FieldExtraction, TextExtractionResult

        title = FieldExtraction(
            value="Test", confidence=0.9, source="heuristic", alternatives=(), reasoning=""
        )
        author = FieldExtraction(
            value="Smith", confidence=0.6, source="heuristic", alternatives=(), reasoning=""
        )
        date = FieldExtraction(
            value="2023", confidence=0.8, source="heuristic", alternatives=(), reasoning=""
        )
        doc_type = FieldExtraction(
            value="article-journal",
            confidence=0.95,
            source="heuristic",
            alternatives=(),
            reasoning="",
        )

        result = TextExtractionResult(
            title=title,
            authors=(author,),
            date=date,
            doc_type=doc_type,
            overall_confidence=0.6,  # min of 0.9, 0.6, 0.8, 0.95
            needs_review=True,
            review_reasons=("authors confidence below threshold",),
        )

        assert result.overall_confidence == 0.6

    def test_text_extraction_result_needs_review_with_reasons(self) -> None:
        """needs_review should have corresponding review_reasons."""
        from local_library.core.models import FieldExtraction, TextExtractionResult

        title = FieldExtraction(
            value="Test", confidence=0.5, source="heuristic", alternatives=(), reasoning=""
        )
        date = FieldExtraction(
            value=None, confidence=0.0, source="heuristic", alternatives=(), reasoning=""
        )
        doc_type = FieldExtraction(
            value="article-journal",
            confidence=0.7,
            source="heuristic",
            alternatives=(),
            reasoning="",
        )

        result = TextExtractionResult(
            title=title,
            authors=(),
            date=date,
            doc_type=doc_type,
            overall_confidence=0.0,
            needs_review=True,
            review_reasons=(
                "title confidence 0.50 below threshold 0.70",
                "date could not be extracted",
            ),
        )

        assert result.needs_review is True
        assert len(result.review_reasons) == 2

    def test_text_extraction_result_empty_authors_allowed(self) -> None:
        """TextExtractionResult should allow empty authors tuple."""
        from local_library.core.models import FieldExtraction, TextExtractionResult

        title = FieldExtraction(
            value="Test", confidence=0.9, source="heuristic", alternatives=(), reasoning=""
        )
        date = FieldExtraction(
            value="2023", confidence=0.8, source="heuristic", alternatives=(), reasoning=""
        )
        doc_type = FieldExtraction(
            value="article-journal",
            confidence=0.7,
            source="heuristic",
            alternatives=(),
            reasoning="",
        )

        result = TextExtractionResult(
            title=title,
            authors=(),
            date=date,
            doc_type=doc_type,
            overall_confidence=0.7,
            needs_review=True,
            review_reasons=("no authors found",),
        )

        assert result.authors == ()
```

**Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/unit/test_models.py::TestTextExtractionResult -v
```

Expected: FAIL with "cannot import name 'TextExtractionResult'"

**Step 3: Implement TextExtractionResult**

Add to `src/local_library/core/models.py` after the `FieldExtraction` class:

```python
@dataclass(frozen=True)
class TextExtractionResult:
    """Complete metadata extraction result from document text.

    Aggregates per-field extractions with overall confidence and review status.
    Used by TextMetadataExtractor as the return type for extract().

    Attributes:
        title: Extracted title field
        authors: Tuple of extracted author fields (one per author)
        date: Extracted publication date field
        doc_type: Extracted document type field
        overall_confidence: Minimum of all field confidences
        needs_review: True if any field confidence is below threshold
        review_reasons: Explanations for why review is needed
    """

    title: FieldExtraction
    authors: tuple[FieldExtraction, ...]
    date: FieldExtraction
    doc_type: FieldExtraction
    overall_confidence: float
    needs_review: bool
    review_reasons: tuple[str, ...]
```

**Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/unit/test_models.py::TestTextExtractionResult -v
```

Expected: All 4 tests PASS

**Step 5: Run all model tests**

Run:
```bash
uv run pytest tests/unit/test_models.py -v
```

Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/local_library/core/models.py tests/unit/test_models.py
git commit -m "$(cat <<'EOF'
feat(models): add TextExtractionResult for complete extraction output

Aggregates per-field FieldExtraction results with overall confidence
and review status. Forms the return type for TextMetadataExtractor.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_4 -->
### Task 4: Verify storage layer handles NEEDS_REVIEW status

**Files:**
- Test: `tests/unit/test_storage.py`

The SQLite storage layer stores DocumentStatus as a string value. Since NEEDS_REVIEW follows the same `str, Enum` pattern, it should work automatically. This task verifies that assumption.

**Step 1: Write test for NEEDS_REVIEW storage round-trip**

Add to `tests/unit/test_storage.py`:

```python
def test_document_status_needs_review_round_trip(temp_dir: Path) -> None:
    """NEEDS_REVIEW status should persist and retrieve correctly."""
    from local_library.core.models import DocumentStatus
    from local_library.core.storage import (
        create_document,
        get_connection,
        get_document_by_id,
        init_schema,
        update_document_status,
    )

    db_path = temp_dir / "test.db"
    conn = get_connection(db_path)
    init_schema(conn)

    # Create a document
    doc = create_document(
        conn,
        original_path="/test/file.pdf",
        content_hash="abc123",
        storage_path="/storage/ab/c1/abc123.pdf",
    )

    # Update to NEEDS_REVIEW status
    updated = update_document_status(
        conn,
        doc.id,
        DocumentStatus.NEEDS_REVIEW,
        extracted_path="/extracted/ab/c1/abc123.md",
    )

    assert updated.status == DocumentStatus.NEEDS_REVIEW

    # Verify retrieval
    retrieved = get_document_by_id(conn, doc.id)
    assert retrieved is not None
    assert retrieved.status == DocumentStatus.NEEDS_REVIEW

    conn.close()
```

**Step 2: Run test to verify it passes**

Run:
```bash
uv run pytest tests/unit/test_storage.py::test_document_status_needs_review_round_trip -v
```

Expected: PASS (the enum string storage pattern already handles this)

**Step 3: Commit**

```bash
git add tests/unit/test_storage.py
git commit -m "$(cat <<'EOF'
test(storage): verify NEEDS_REVIEW status storage round-trip

Confirms that the new DocumentStatus.NEEDS_REVIEW value persists
correctly through SQLite storage.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Update models __all__ export and run full test suite

**Files:**
- Modify: `src/local_library/core/models.py` (if `__all__` exists, add new types)

**Step 1: Check if models.py has __all__ export**

Look at the top of `src/local_library/core/models.py`. If there's an `__all__` list, add the new types. If not, skip this step (Python exports all public names by default).

If `__all__` exists, add:
```python
__all__ = [
    # ... existing exports ...
    "FieldExtraction",
    "TextExtractionResult",
]
```

**Step 2: Run the full test suite**

Run:
```bash
uv run pytest tests/unit/ -v
```

Expected: All tests PASS

**Step 3: Run linting**

Run:
```bash
uv run ruff check src/local_library/core/models.py
uv run ruff format src/local_library/core/models.py
```

Expected: No errors (or auto-fixed)

**Step 4: Final commit for Phase 1**

If any formatting changes were made:
```bash
git add src/local_library/core/models.py
git commit -m "$(cat <<'EOF'
style(models): format after adding extraction types

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_5 -->

---

## Phase 1 Completion Checklist

- [ ] `DocumentStatus.NEEDS_REVIEW` added to enum
- [ ] `FieldExtraction` dataclass added and tested
- [ ] `TextExtractionResult` dataclass added and tested
- [ ] Storage layer handles NEEDS_REVIEW (verified by test)
- [ ] All unit tests pass
- [ ] Linting passes
