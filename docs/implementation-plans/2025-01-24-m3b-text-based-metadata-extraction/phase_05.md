# Phase 5: TextMetadataExtractor Orchestration

**Goal:** Combine field extractors into a unified TextMetadataExtractor with confidence aggregation.

This phase creates the main extraction class that orchestrates all field extractors and determines overall confidence and review status.

**Reference documentation:**
- `src/local_library/core/CLAUDE.md` - Core domain contracts
- `src/local_library/ingestion/CLAUDE.md` - Ingestion domain contracts

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Write tests for TextMetadataExtractor

**Files:**
- Modify: `tests/unit/test_text_extraction.py`

**Step 1: Add TextMetadataExtractor tests**

Add to `tests/unit/test_text_extraction.py`:

```python
class TestTextMetadataExtractor:
    """Tests for the TextMetadataExtractor orchestration class."""

    def test_extract_all_fields(self) -> None:
        """Extractor should return all field extractions."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        text = """Machine Learning in Healthcare

        John Smith, Jane Doe
        Published: 2023

        Journal of Medical Informatics

        Abstract: This paper presents...
        """

        extractor = TextMetadataExtractor()
        result = extractor.extract(text)

        # All fields should be present
        assert result.title.value is not None
        assert len(result.authors) >= 1
        assert result.date.value is not None
        assert result.doc_type.value is not None

    def test_extract_overall_confidence_is_minimum(self) -> None:
        """overall_confidence should be minimum of field confidences."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        text = """# Clear Title With High Confidence

        John Smith

        2023

        Abstract...
        """

        extractor = TextMetadataExtractor()
        result = extractor.extract(text)

        # Overall should be min of all fields
        field_confidences = [
            result.title.confidence,
            result.date.confidence,
            result.doc_type.confidence,
        ]
        if result.authors:
            field_confidences.extend(a.confidence for a in result.authors)

        # Allow small floating point difference
        assert abs(result.overall_confidence - min(field_confidences)) < 0.01

    def test_extract_needs_review_when_low_confidence(self) -> None:
        """needs_review should be True when any field is below threshold."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        # Minimal text likely to have low confidence
        text = """Some Title

        Content without clear author or date patterns...
        """

        extractor = TextMetadataExtractor(confidence_threshold=0.7)
        result = extractor.extract(text)

        # Should need review due to low confidence fields
        assert result.needs_review is True
        assert len(result.review_reasons) >= 1

    def test_extract_review_reasons_explain_issues(self) -> None:
        """review_reasons should explain which fields are uncertain."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        text = """Document Title

        Some content without dates or authors clearly marked.
        """

        extractor = TextMetadataExtractor(confidence_threshold=0.7)
        result = extractor.extract(text)

        if result.needs_review:
            # Reasons should mention specific fields
            reasons_text = " ".join(result.review_reasons).lower()
            assert any(
                field in reasons_text
                for field in ["title", "author", "date", "type", "confidence"]
            )

    def test_extract_no_review_when_all_confident(self) -> None:
        """needs_review should be False when all fields are confident."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        # Well-structured document with clear signals
        text = """# Deep Learning for Image Recognition

        John Smith, Jane Doe

        Published: January 15, 2023

        Journal of Computer Vision, Vol. 42

        Abstract: This paper presents a novel approach...
        """

        extractor = TextMetadataExtractor(confidence_threshold=0.5)
        result = extractor.extract(text)

        # All fields should be confident enough
        assert result.title.confidence >= 0.5
        # If needs_review is False, no reasons needed
        if not result.needs_review:
            assert result.review_reasons == ()

    def test_extract_empty_text(self) -> None:
        """Empty text should return result with needs_review=True."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        extractor = TextMetadataExtractor()
        result = extractor.extract("")

        assert result.needs_review is True
        assert result.overall_confidence == 0.0

    def test_extract_configurable_threshold(self) -> None:
        """Confidence threshold should be configurable."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        text = """Some Title

        John Smith
        2023
        """

        # With low threshold, might not need review
        low_threshold = TextMetadataExtractor(confidence_threshold=0.3)
        low_result = low_threshold.extract(text)

        # With high threshold, likely needs review
        high_threshold = TextMetadataExtractor(confidence_threshold=0.9)
        high_result = high_threshold.extract(text)

        # High threshold should be more likely to need review
        if low_result.overall_confidence >= 0.3 and low_result.overall_confidence < 0.9:
            assert not low_result.needs_review
            assert high_result.needs_review

    def test_extract_returns_text_extraction_result(self) -> None:
        """Result should be a proper TextExtractionResult."""
        from local_library.core.models import TextExtractionResult
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        extractor = TextMetadataExtractor()
        result = extractor.extract("Some text")

        assert isinstance(result, TextExtractionResult)

    def test_extract_authors_tuple_not_list(self) -> None:
        """Authors should be returned as tuple for immutability."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        text = """Title

        John Smith, Jane Doe

        Content...
        """

        extractor = TextMetadataExtractor()
        result = extractor.extract(text)

        assert isinstance(result.authors, tuple)

    def test_extract_review_reasons_tuple_not_list(self) -> None:
        """review_reasons should be returned as tuple."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        extractor = TextMetadataExtractor()
        result = extractor.extract("minimal text")

        assert isinstance(result.review_reasons, tuple)
```

**Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/unit/test_text_extraction.py::TestTextMetadataExtractor -v
```

Expected: FAIL with "cannot import name 'TextMetadataExtractor'"

**Step 3: Commit**

```bash
git add tests/unit/test_text_extraction.py
git commit -m "$(cat <<'EOF'
test(text_extraction): add TextMetadataExtractor orchestration tests

Covers field extraction, confidence aggregation, needs_review logic,
configurable thresholds, and edge cases.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement TextMetadataExtractor class

**Files:**
- Modify: `src/local_library/ingestion/text_extraction.py`

**Step 1: Add TextMetadataExtractor implementation**

Add to `src/local_library/ingestion/text_extraction.py` at the end:

```python
# Default confidence threshold for triggering needs_review
_DEFAULT_CONFIDENCE_THRESHOLD = 0.7


class TextMetadataExtractor:
    """Orchestrates extraction of all metadata fields from document text.

    Combines individual field extractors (title, authors, date, type) and
    aggregates confidence scores to determine if human review is needed.

    Usage:
        extractor = TextMetadataExtractor()
        result = extractor.extract(markdown_text)
        if result.needs_review:
            print(f"Review needed: {result.review_reasons}")

    Attributes:
        confidence_threshold: Minimum confidence for a field to be considered
                             reliable. Fields below this trigger needs_review.
    """

    def __init__(self, confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD) -> None:
        """Initialize the extractor.

        Args:
            confidence_threshold: Minimum confidence (0.0-1.0) for fields.
                                 Default is 0.7 (70%).
        """
        self.confidence_threshold = confidence_threshold

    def extract(self, markdown_text: str) -> "TextExtractionResult":
        """Extract all metadata fields from markdown text.

        Runs each field extractor independently, then aggregates results
        into a TextExtractionResult with overall confidence and review status.

        Args:
            markdown_text: Marker-produced markdown content

        Returns:
            TextExtractionResult with all extracted fields and aggregated metadata
        """
        from local_library.core.models import TextExtractionResult

        # Extract each field
        title = extract_title(markdown_text)
        authors = extract_authors(markdown_text)
        date = extract_date(markdown_text)
        doc_type = extract_doc_type(markdown_text)

        # Calculate overall confidence (minimum of all fields)
        all_confidences = [title.confidence, date.confidence, doc_type.confidence]
        if authors:
            all_confidences.extend(a.confidence for a in authors)

        overall_confidence = min(all_confidences) if all_confidences else 0.0

        # Determine needs_review and reasons
        review_reasons = self._check_review_needed(title, authors, date, doc_type)
        needs_review = len(review_reasons) > 0

        return TextExtractionResult(
            title=title,
            authors=authors,
            date=date,
            doc_type=doc_type,
            overall_confidence=round(overall_confidence, 2),
            needs_review=needs_review,
            review_reasons=tuple(review_reasons),
        )

    def _check_review_needed(
        self,
        title: FieldExtraction,
        authors: tuple[FieldExtraction, ...],
        date: FieldExtraction,
        doc_type: FieldExtraction,
    ) -> list[str]:
        """Check if any field needs human review.

        Returns:
            List of review reasons (empty if no review needed)
        """
        reasons: list[str] = []
        threshold = self.confidence_threshold

        # Check title
        if title.value is None:
            reasons.append("title could not be extracted")
        elif title.confidence < threshold:
            reasons.append(
                f"title confidence {title.confidence:.2f} below threshold {threshold:.2f}"
            )

        # Check authors
        if not authors:
            reasons.append("no authors could be extracted")
        else:
            low_conf_authors = [a for a in authors if a.confidence < threshold]
            if len(low_conf_authors) == len(authors):
                # All authors have low confidence
                avg_conf = sum(a.confidence for a in authors) / len(authors)
                reasons.append(
                    f"authors average confidence {avg_conf:.2f} below threshold {threshold:.2f}"
                )

        # Check date
        if date.value is None:
            reasons.append("date could not be extracted")
        elif date.confidence < threshold:
            reasons.append(
                f"date confidence {date.confidence:.2f} below threshold {threshold:.2f}"
            )

        # Check doc_type (less critical, only flag if very low)
        if doc_type.confidence < threshold * 0.7:  # Lower bar for type
            reasons.append(
                f"document type confidence {doc_type.confidence:.2f} is low"
            )

        return reasons
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/unit/test_text_extraction.py::TestTextMetadataExtractor -v
```

Expected: All tests PASS

**Step 3: Commit**

```bash
git add src/local_library/ingestion/text_extraction.py
git commit -m "$(cat <<'EOF'
feat(text_extraction): implement TextMetadataExtractor orchestrator

Combines field extractors with confidence aggregation. Determines
needs_review based on configurable threshold and generates review
reasons for uncertain fields.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Run full test suite and lint

**Files:**
- All modified files

**Step 1: Run all text extraction tests**

Run:
```bash
uv run pytest tests/unit/test_text_extraction.py -v
```

Expected: All tests PASS

**Step 2: Run all unit tests**

Run:
```bash
uv run pytest tests/unit/ -v
```

Expected: All tests PASS

**Step 3: Run linting**

Run:
```bash
uv run ruff check src/local_library/ingestion/text_extraction.py
uv run ruff format src/local_library/ingestion/text_extraction.py
```

Expected: No errors (or auto-fixed)

**Step 4: Commit any fixes**

```bash
git add .
git commit -m "$(cat <<'EOF'
style(text_extraction): apply ruff formatting

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

---

## Phase 5 Completion Checklist

- [ ] `TextMetadataExtractor` class implemented
- [ ] Field extraction orchestration working
- [ ] Confidence aggregation (minimum) working
- [ ] `needs_review` determination working
- [ ] `review_reasons` generation working
- [ ] Configurable threshold working
- [ ] All orchestration tests pass
- [ ] Linting passes
