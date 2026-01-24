# Phase 4: Date and Type Extraction

**Goal:** Extract publication year and document type from markdown.

Date extraction uses priority-based search (explicit markers > copyright > ISO dates > standalone years). Type extraction uses keyword/pattern matching with sensible defaults.

**Reference documentation:**
- `src/local_library/core/CLAUDE.md` - Core domain contracts
- `src/local_library/ingestion/CLAUDE.md` - Ingestion domain contracts

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Write tests for date extraction

**Files:**
- Modify: `tests/unit/test_text_extraction.py`

**Step 1: Add date extraction tests**

Add to `tests/unit/test_text_extraction.py`:

```python
class TestDateExtraction:
    """Tests for publication date extraction from markdown text."""

    def test_extract_date_explicit_published(self) -> None:
        """Date with 'Published:' label should be extracted."""
        from local_library.ingestion.text_extraction import extract_date

        text = """Research Paper

        Published: January 15, 2023

        Abstract...
        """

        result = extract_date(text)

        assert result.value == "2023"
        assert result.confidence >= 0.8

    def test_extract_date_copyright_notice(self) -> None:
        """Copyright year should be extracted."""
        from local_library.ingestion.text_extraction import extract_date

        text = """Technical Report

        © 2022 IEEE

        Abstract...
        """

        result = extract_date(text)

        assert result.value == "2022"
        assert result.confidence >= 0.7

    def test_extract_date_copyright_word(self) -> None:
        """'Copyright 2021' pattern should be detected."""
        from local_library.ingestion.text_extraction import extract_date

        text = """Document Title

        Copyright 2021 ACM

        Introduction...
        """

        result = extract_date(text)

        assert result.value == "2021"

    def test_extract_date_iso_format(self) -> None:
        """ISO date format (2023-05-15) should be extracted."""
        from local_library.ingestion.text_extraction import extract_date

        text = """Report

        Date: 2023-05-15

        Content...
        """

        result = extract_date(text)

        assert result.value == "2023"
        assert result.confidence >= 0.7

    def test_extract_date_standalone_year(self) -> None:
        """Standalone year in header area should be extracted."""
        from local_library.ingestion.text_extraction import extract_date

        text = """Paper Title

        John Smith
        2020

        Abstract...
        """

        result = extract_date(text)

        assert result.value == "2020"
        # Lower confidence for standalone year
        assert result.confidence >= 0.4
        assert result.confidence < 0.8

    def test_extract_date_rejects_future_years(self) -> None:
        """Years in the far future should be rejected or low confidence."""
        from local_library.ingestion.text_extraction import extract_date

        text = """Predictions for 2050

        By 2100, climate change will...
        """

        result = extract_date(text)

        # Should not pick 2050 or 2100 as publication date
        if result.value:
            assert int(result.value) <= 2030 or result.confidence < 0.3

    def test_extract_date_rejects_old_years(self) -> None:
        """Very old years (pre-1900) should be low confidence unless explicit."""
        from local_library.ingestion.text_extraction import extract_date

        text = """Analysis of 1776 Events

        Historical analysis of events in 1776...
        """

        result = extract_date(text)

        # Should not confidently pick 1776 as publication date
        if result.value == "1776":
            assert result.confidence < 0.5

    def test_extract_date_prefers_header_area(self) -> None:
        """Years in header area should be preferred over body."""
        from local_library.ingestion.text_extraction import extract_date

        text = """Paper Title

        Published: 2022

        In 2010, researchers discovered...
        Later in 2015, this was confirmed...
        """

        result = extract_date(text)

        assert result.value == "2022"

    def test_extract_date_multiple_formats(self) -> None:
        """Should handle multiple date formats."""
        from local_library.ingestion.text_extraction import extract_date

        formats = [
            ("January 2023", "2023"),
            ("Jan. 2023", "2023"),
            ("01/2023", "2023"),
            ("2023-01", "2023"),
            ("March 15, 2022", "2022"),
        ]

        for date_str, expected_year in formats:
            text = f"Title\n\nPublished: {date_str}\n\nContent..."
            result = extract_date(text)
            assert result.value == expected_year, f"Failed for format: {date_str}"

    def test_extract_date_empty_text_returns_none(self) -> None:
        """Empty text should return None with zero confidence."""
        from local_library.ingestion.text_extraction import extract_date

        result = extract_date("")

        assert result.value is None
        assert result.confidence == 0.0

    def test_extract_date_no_date_found(self) -> None:
        """Text without dates should return None."""
        from local_library.ingestion.text_extraction import extract_date

        text = """A Document Without Dates

        This paper discusses various topics
        without mentioning any specific years.
        """

        result = extract_date(text)

        assert result.value is None
        assert result.confidence == 0.0

    def test_extract_date_returns_field_extraction(self) -> None:
        """Result should be a proper FieldExtraction."""
        from local_library.ingestion.text_extraction import extract_date

        text = "Title\n\n2023\n\nContent"

        result = extract_date(text)

        assert hasattr(result, "value")
        assert hasattr(result, "confidence")
        assert hasattr(result, "source")
        assert result.source == "heuristic"
```

**Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/unit/test_text_extraction.py::TestDateExtraction -v
```

Expected: FAIL with "cannot import name 'extract_date'"

**Step 3: Commit**

```bash
git add tests/unit/test_text_extraction.py
git commit -m "$(cat <<'EOF'
test(text_extraction): add date extraction test cases

Covers explicit labels, copyright notices, ISO dates, standalone years,
edge cases for future/past years, and format variations.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement date extraction

**Files:**
- Modify: `src/local_library/ingestion/text_extraction.py`

**Step 1: Add date extraction implementation**

Add to `src/local_library/ingestion/text_extraction.py` after author extraction:

```python
# Date extraction constants
_DATE_SEARCH_LINES = 30  # Search first N lines for dates
_CURRENT_YEAR = 2025  # Update as needed
_MIN_VALID_YEAR = 1900
_MAX_VALID_YEAR = _CURRENT_YEAR + 2  # Allow slight future for pre-prints


@dataclass(frozen=True)
class _DateCandidate:
    """Internal candidate for date extraction."""

    year: str
    score: float
    reasoning: str


def _extract_year_from_text(text: str) -> str | None:
    """Extract a 4-digit year from text.

    Handles various formats:
    - ISO: 2023-05-15, 2023-05
    - US: January 15, 2023 / Jan 2023 / 01/15/2023
    - Standalone: 2023

    Returns:
        4-digit year string or None
    """
    # ISO format: 2023-05-15 or 2023-05
    iso_match = re.search(r"\b((?:19|20)\d{2})-\d{1,2}(?:-\d{1,2})?\b", text)
    if iso_match:
        return iso_match.group(1)

    # Month name + year: January 2023, Jan. 2023, Jan 2023
    month_year = re.search(
        r"\b(?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December|Jan\.?|Feb\.?|Mar\.?|Apr\.?|May\.?|Jun\.?|"
        r"Jul\.?|Aug\.?|Sep(?:t)?\.?|Oct\.?|Nov\.?|Dec\.?)\s+\d{1,2}?,?\s*((?:19|20)\d{2})\b",
        text,
        re.IGNORECASE,
    )
    if month_year:
        return month_year.group(1)

    # Month year without day: January 2023
    month_year_simple = re.search(
        r"\b(?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December|Jan\.?|Feb\.?|Mar\.?|Apr\.?|May\.?|Jun\.?|"
        r"Jul\.?|Aug\.?|Sep(?:t)?\.?|Oct\.?|Nov\.?|Dec\.?)\s+((?:19|20)\d{2})\b",
        text,
        re.IGNORECASE,
    )
    if month_year_simple:
        return month_year_simple.group(1)

    # US format: 01/15/2023 or 01/2023
    us_match = re.search(r"\b\d{1,2}/(?:\d{1,2}/)?((?:19|20)\d{2})\b", text)
    if us_match:
        return us_match.group(1)

    # Standalone year
    standalone = re.search(r"\b((?:19|20)\d{2})\b", text)
    if standalone:
        return standalone.group(1)

    return None


def _is_valid_publication_year(year_str: str) -> bool:
    """Check if a year is plausible as a publication date."""
    try:
        year = int(year_str)
        return _MIN_VALID_YEAR <= year <= _MAX_VALID_YEAR
    except ValueError:
        return False


def _find_date_candidates(text: str) -> list[_DateCandidate]:
    """Find publication date candidates in text.

    Priority order:
    1. Explicit labels (Published:, Date:)
    2. Copyright notices (© 2023, Copyright 2023)
    3. ISO dates in header area
    4. Standalone years in header area

    Returns:
        List of candidates sorted by score (highest first)
    """
    candidates: list[_DateCandidate] = []
    lines = text.split("\n")[:_DATE_SEARCH_LINES]

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Priority 1: Explicit date labels
        explicit_patterns = [
            (r"(?:published|date|dated)[\s:]+(.+)", 0.9, "explicit label"),
            (r"(?:received|accepted)[\s:]+(.+)", 0.85, "received/accepted date"),
        ]

        for pattern, base_score, reason in explicit_patterns:
            match = re.search(pattern, stripped, re.IGNORECASE)
            if match:
                year = _extract_year_from_text(match.group(1))
                if year and _is_valid_publication_year(year):
                    candidates.append(_DateCandidate(year, base_score, reason))

        # Priority 2: Copyright notices
        copyright_patterns = [
            (r"[©®]\s*((?:19|20)\d{2})", 0.85, "copyright symbol"),
            (r"copyright\s+((?:19|20)\d{2})", 0.8, "copyright text"),
        ]

        for pattern, base_score, reason in copyright_patterns:
            match = re.search(pattern, stripped, re.IGNORECASE)
            if match:
                year = match.group(1)
                if _is_valid_publication_year(year):
                    candidates.append(_DateCandidate(year, base_score, reason))

        # Priority 3: ISO dates in header area (first 15 lines)
        if i < 15:
            iso_match = re.search(r"\b((?:19|20)\d{2})-\d{1,2}(?:-\d{1,2})?\b", stripped)
            if iso_match:
                year = iso_match.group(1)
                if _is_valid_publication_year(year):
                    score = 0.7 if i < 10 else 0.5
                    candidates.append(_DateCandidate(year, score, "ISO date"))

        # Priority 4: Standalone years in header area (first 10 lines)
        if i < 10:
            # Only match standalone years (not part of larger numbers)
            standalone = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", stripped)
            if standalone:
                year = standalone.group(1)
                if _is_valid_publication_year(year):
                    # Lower score for standalone years
                    score = 0.5 - (i * 0.03)  # Decrease with position
                    candidates.append(_DateCandidate(year, max(0.3, score), "standalone year"))

    # Sort by score descending
    candidates.sort(key=lambda c: c.score, reverse=True)

    return candidates


def extract_date(markdown_text: str) -> FieldExtraction:
    """Extract publication year from markdown text.

    Uses priority-based search:
    1. Explicit markers (Published:, Date:)
    2. Copyright notices (© year, Copyright year)
    3. ISO dates in header area
    4. Standalone years in header area

    Args:
        markdown_text: Marker-produced markdown content

    Returns:
        FieldExtraction with extracted year (as string), confidence, and reasoning
    """
    # Handle empty input
    if not markdown_text or not markdown_text.strip():
        return FieldExtraction(
            value=None,
            confidence=0.0,
            source="heuristic",
            alternatives=(),
            reasoning="no text content",
        )

    # Find candidates
    candidates = _find_date_candidates(markdown_text)

    if not candidates:
        return FieldExtraction(
            value=None,
            confidence=0.0,
            source="heuristic",
            alternatives=(),
            reasoning="no date patterns found",
        )

    # Select best candidate
    best = candidates[0]

    # Calculate confidence with margin bonus
    if len(candidates) >= 2:
        margin = best.score - candidates[1].score
        confidence = best.score * (0.8 + 0.2 * min(margin * 2, 1.0))
    else:
        confidence = best.score * 0.9

    # Alternatives (different years only)
    seen_years = {best.year}
    alternatives = []
    for c in candidates[1:]:
        if c.year not in seen_years:
            alternatives.append(c.year)
            seen_years.add(c.year)
        if len(alternatives) >= 3:
            break

    return FieldExtraction(
        value=best.year,
        confidence=round(confidence, 2),
        source="heuristic",
        alternatives=tuple(alternatives),
        reasoning=best.reasoning,
    )
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/unit/test_text_extraction.py::TestDateExtraction -v
```

Expected: Most tests PASS

**Step 3: Commit**

```bash
git add src/local_library/ingestion/text_extraction.py
git commit -m "$(cat <<'EOF'
feat(text_extraction): implement date extraction with priority search

Detects publication dates via explicit labels, copyright notices,
ISO dates, and standalone years. Priority-based scoring prefers
explicit markers over implicit patterns.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Write tests and implement type extraction

**Files:**
- Modify: `tests/unit/test_text_extraction.py`
- Modify: `src/local_library/ingestion/text_extraction.py`

**Step 1: Add type extraction tests**

Add to `tests/unit/test_text_extraction.py`:

```python
class TestTypeExtraction:
    """Tests for document type extraction from markdown text."""

    def test_extract_type_journal_article(self) -> None:
        """Journal-like documents should return 'article-journal'."""
        from local_library.ingestion.text_extraction import extract_doc_type

        text = """Machine Learning Applications

        Journal of Computer Science, Vol. 42, No. 3

        Abstract: This paper presents...
        """

        result = extract_doc_type(text)

        assert result.value == "article-journal"
        assert result.confidence >= 0.7

    def test_extract_type_conference_paper(self) -> None:
        """Conference papers should return 'paper-conference'."""
        from local_library.ingestion.text_extraction import extract_doc_type

        text = """Novel Algorithm Design

        Proceedings of the International Conference on Machine Learning

        Abstract...
        """

        result = extract_doc_type(text)

        assert result.value == "paper-conference"

    def test_extract_type_book_chapter(self) -> None:
        """Book chapters should return 'chapter'."""
        from local_library.ingestion.text_extraction import extract_doc_type

        text = """Chapter 5: Advanced Topics

        In: Handbook of Machine Learning
        Editors: Smith and Jones

        Introduction...
        """

        result = extract_doc_type(text)

        assert result.value == "chapter"

    def test_extract_type_thesis(self) -> None:
        """Theses should return 'thesis'."""
        from local_library.ingestion.text_extraction import extract_doc_type

        text = """A Dissertation Submitted to the Faculty

        in partial fulfillment of the requirements
        for the degree of Doctor of Philosophy

        By John Smith
        """

        result = extract_doc_type(text)

        assert result.value == "thesis"

    def test_extract_type_report(self) -> None:
        """Technical reports should return 'report'."""
        from local_library.ingestion.text_extraction import extract_doc_type

        text = """Technical Report TR-2023-01

        MIT Computer Science and Artificial Intelligence Laboratory

        Abstract...
        """

        result = extract_doc_type(text)

        assert result.value == "report"

    def test_extract_type_default_article_journal(self) -> None:
        """Unknown document types should default to 'article-journal'."""
        from local_library.ingestion.text_extraction import extract_doc_type

        text = """Some Research

        By Someone

        This discusses various topics...
        """

        result = extract_doc_type(text)

        # Default is article-journal
        assert result.value == "article-journal"
        # But with lower confidence
        assert result.confidence < 0.7

    def test_extract_type_empty_text(self) -> None:
        """Empty text should return default with low confidence."""
        from local_library.ingestion.text_extraction import extract_doc_type

        result = extract_doc_type("")

        assert result.value == "article-journal"  # Default
        assert result.confidence < 0.5

    def test_extract_type_returns_field_extraction(self) -> None:
        """Result should be a proper FieldExtraction."""
        from local_library.ingestion.text_extraction import extract_doc_type

        text = "Some text"

        result = extract_doc_type(text)

        assert hasattr(result, "value")
        assert hasattr(result, "confidence")
        assert hasattr(result, "source")
        assert result.source == "heuristic"

    def test_extract_type_preprint(self) -> None:
        """Preprints/arXiv papers should be detected."""
        from local_library.ingestion.text_extraction import extract_doc_type

        text = """arXiv:2301.12345v1 [cs.LG]

        Deep Learning for Everything

        Abstract...
        """

        result = extract_doc_type(text)

        # Preprints are typically article-journal or article
        assert result.value in ("article-journal", "article")
```

**Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/unit/test_text_extraction.py::TestTypeExtraction -v
```

Expected: FAIL with "cannot import name 'extract_doc_type'"

**Step 3: Implement type extraction**

Add to `src/local_library/ingestion/text_extraction.py`:

```python
# Type extraction patterns (pattern, type, confidence)
_TYPE_PATTERNS: list[tuple[str, str, float]] = [
    # Thesis patterns
    (r"\bdissertation\b", "thesis", 0.9),
    (r"\bthesis\b", "thesis", 0.9),
    (r"\bphd\b.*\b(?:candidate|student)\b", "thesis", 0.8),
    (r"in partial fulfillment", "thesis", 0.85),
    (r"\bmaster'?s?\s+(?:thesis|degree)\b", "thesis", 0.85),

    # Conference patterns
    (r"\bproceedings\b", "paper-conference", 0.85),
    (r"\bconference\b.*\bpaper\b", "paper-conference", 0.8),
    (r"\bworkshop\b.*\bpaper\b", "paper-conference", 0.75),
    (r"\baccepted\s+(?:at|to)\s+\w+\s+\d{4}\b", "paper-conference", 0.7),

    # Chapter patterns
    (r"^chapter\s+\d+", "chapter", 0.9),
    (r"\bin:\s+\w+", "chapter", 0.6),
    (r"\beditors?:\s+", "chapter", 0.5),

    # Report patterns
    (r"\btechnical\s+report\b", "report", 0.9),
    (r"\btr-\d+", "report", 0.8),
    (r"\bworking\s+paper\b", "report", 0.75),
    (r"\bwhite\s+paper\b", "report", 0.7),

    # Book patterns
    (r"\bisbn\b", "book", 0.8),
    (r"\bpublisher:\s+", "book", 0.6),

    # Journal patterns
    (r"\bjournal\s+of\b", "article-journal", 0.8),
    (r"\bvol(?:ume)?\.?\s*\d+", "article-journal", 0.6),
    (r"\bissue\s*\d+", "article-journal", 0.5),
    (r"\bpp\.?\s*\d+", "article-journal", 0.5),
]

# Default type when no patterns match
_DEFAULT_DOC_TYPE = "article-journal"
_DEFAULT_TYPE_CONFIDENCE = 0.4


def extract_doc_type(markdown_text: str) -> FieldExtraction:
    """Extract document type from markdown text.

    Uses keyword and pattern matching to identify document type.
    Defaults to 'article-journal' if no clear signals.

    Valid CSL types returned:
    - article-journal (default)
    - paper-conference
    - chapter
    - thesis
    - report
    - book

    Args:
        markdown_text: Marker-produced markdown content

    Returns:
        FieldExtraction with CSL document type
    """
    # Handle empty input
    if not markdown_text or not markdown_text.strip():
        return FieldExtraction(
            value=_DEFAULT_DOC_TYPE,
            confidence=_DEFAULT_TYPE_CONFIDENCE * 0.5,
            source="heuristic",
            alternatives=(),
            reasoning="no text content, using default",
        )

    # Search first part of document
    search_text = markdown_text[:3000].lower()

    # Find matching patterns
    matches: list[tuple[str, float, str]] = []

    for pattern, doc_type, confidence in _TYPE_PATTERNS:
        if re.search(pattern, search_text, re.IGNORECASE | re.MULTILINE):
            matches.append((doc_type, confidence, pattern))

    if not matches:
        return FieldExtraction(
            value=_DEFAULT_DOC_TYPE,
            confidence=_DEFAULT_TYPE_CONFIDENCE,
            source="heuristic",
            alternatives=(),
            reasoning="no type patterns matched, using default",
        )

    # Sort by confidence and aggregate by type
    matches.sort(key=lambda m: m[1], reverse=True)

    # Group matches by type and sum confidence (with diminishing returns)
    type_scores: dict[str, float] = {}
    type_reasons: dict[str, list[str]] = {}

    for doc_type, conf, pattern in matches:
        if doc_type not in type_scores:
            type_scores[doc_type] = conf
            type_reasons[doc_type] = [pattern]
        else:
            # Diminishing returns for multiple matches of same type
            type_scores[doc_type] = min(0.95, type_scores[doc_type] + conf * 0.2)
            type_reasons[doc_type].append(pattern)

    # Select best type
    best_type = max(type_scores.keys(), key=lambda t: type_scores[t])
    best_score = type_scores[best_type]

    # Build alternatives
    alternatives = [t for t in type_scores.keys() if t != best_type][:3]

    # Build reasoning
    patterns = type_reasons[best_type][:2]  # First two patterns
    reasoning = f"matched: {', '.join(patterns)}"

    return FieldExtraction(
        value=best_type,
        confidence=round(best_score, 2),
        source="heuristic",
        alternatives=tuple(alternatives),
        reasoning=reasoning,
    )
```

**Step 4: Run tests**

Run:
```bash
uv run pytest tests/unit/test_text_extraction.py::TestTypeExtraction -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/local_library/ingestion/text_extraction.py tests/unit/test_text_extraction.py
git commit -m "$(cat <<'EOF'
feat(text_extraction): implement document type extraction

Uses pattern matching to detect thesis, conference paper, chapter,
report, or journal article. Defaults to article-journal when no
clear signals present.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_4 -->
### Task 4: Run full test suite and lint

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

<!-- END_TASK_4 -->

---

## Phase 4 Completion Checklist

- [ ] `extract_date()` function implemented
- [ ] Date priority search working (explicit > copyright > ISO > standalone)
- [ ] `extract_doc_type()` function implemented
- [ ] Type pattern matching with sensible defaults
- [ ] All date extraction tests pass
- [ ] All type extraction tests pass
- [ ] Linting passes
