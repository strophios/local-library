# Phase 3: Author Extraction

**Goal:** Extract author names from markdown with best-effort family/given parsing.

This phase implements author extraction, which is more challenging than title extraction due to varied formatting. The design uses multiple detection strategies with fallbacks.

**Note:** The design document mentions "Library author lookup for known names (query existing authors in storage)" as an optional enhancement. This is intentionally deferred for initial implementation per the design's Additional Considerations section, which notes it as a performance consideration for batch imports. It can be added later if needed.

**Reference documentation:**
- `src/local_library/core/CLAUDE.md` - Core domain contracts
- `src/local_library/ingestion/CLAUDE.md` - Ingestion domain contracts

---

<!-- START_TASK_1 -->
### Task 1: Add nameparser dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add nameparser to dependencies**

In `pyproject.toml`, add `nameparser` to the dependencies list. **Note:** Preserve the existing marker-pdf version constraint (currently pinned due to MPS bug):

```toml
dependencies = [
    "jsonschema>=4.20.0",
    "marker-pdf>=1.10.0",  # Keep existing constraint from pyproject.toml
    "nameparser>=1.1.0",   # NEW
    "platformdirs>=4.0.0",
    "rich>=13.0.0",
    "typer>=0.21.0",
    "unidecode>=1.3.0",
]
```

Simply add the `nameparser>=1.1.0` line; do not modify other existing dependencies.

**Step 2: Install the new dependency**

Run:
```bash
uv sync
```

Expected: Installs nameparser without errors

**Step 3: Verify import works**

Run:
```bash
uv run python -c "from nameparser import HumanName; print(HumanName('John Smith'))"
```

Expected: Prints `John Smith`

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "$(cat <<'EOF'
deps: add nameparser for author name parsing

Used by M3b text extraction to split author names into
family/given components for CSL-JSON compatibility.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-4) -->

<!-- START_TASK_2 -->
### Task 2: Write tests for author extraction

**Files:**
- Modify: `tests/unit/test_text_extraction.py`

**Step 1: Add author extraction tests**

Add to `tests/unit/test_text_extraction.py`:

```python
class TestAuthorExtraction:
    """Tests for author extraction from markdown text."""

    def test_extract_authors_single_author(self) -> None:
        """Single author should be extracted correctly."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Machine Learning Fundamentals

        John Smith
        Department of Computer Science

        Abstract: This paper presents...
        """

        result = extract_authors(text)

        assert len(result) == 1
        assert result[0].value is not None
        # Should have family name
        assert "Smith" in result[0].value

    def test_extract_authors_multiple_authors_comma_separated(self) -> None:
        """Multiple comma-separated authors should be extracted."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Research Paper Title

        John Smith, Jane Doe, Bob Wilson
        University Research Lab

        Abstract...
        """

        result = extract_authors(text)

        assert len(result) == 3
        names = [r.value for r in result]
        assert any("Smith" in n for n in names if n)
        assert any("Doe" in n for n in names if n)
        assert any("Wilson" in n for n in names if n)

    def test_extract_authors_with_and_separator(self) -> None:
        """Authors separated by 'and' should be extracted."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Title Here

        John Smith and Jane Doe

        Introduction...
        """

        result = extract_authors(text)

        assert len(result) == 2

    def test_extract_authors_after_by_keyword(self) -> None:
        """Authors prefixed with 'by' should be detected."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Understanding Neural Networks

        by John Smith

        This tutorial explains...
        """

        result = extract_authors(text)

        assert len(result) >= 1
        assert any("Smith" in (r.value or "") for r in result)

    def test_extract_authors_before_abstract(self) -> None:
        """Authors appearing before 'Abstract' should be detected."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Paper Title

        Alice Johnson
        Bob Smith

        Abstract

        This paper discusses...
        """

        result = extract_authors(text)

        assert len(result) >= 2

    def test_extract_authors_with_affiliations_inline(self) -> None:
        """Authors with inline affiliations should have names extracted."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Research Title

        John Smith (MIT), Jane Doe (Stanford)

        Abstract...
        """

        result = extract_authors(text)

        assert len(result) == 2
        # Affiliations should be stripped
        assert "MIT" not in (result[0].value or "")
        assert "Stanford" not in (result[1].value or "")

    def test_extract_authors_with_email(self) -> None:
        """Author lines with emails should extract names only."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Title

        John Smith <john@example.com>

        Content...
        """

        result = extract_authors(text)

        assert len(result) >= 1
        assert "example.com" not in (result[0].value or "")

    def test_extract_authors_empty_text_returns_empty(self) -> None:
        """Empty text should return empty list."""
        from local_library.ingestion.text_extraction import extract_authors

        result = extract_authors("")

        assert result == ()

    def test_extract_authors_no_authors_found(self) -> None:
        """Text without detectable authors should return empty list."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Technical Specification

        1. Introduction
        2. Requirements
        3. Implementation
        """

        result = extract_authors(text)

        # Might return empty or low-confidence results
        assert all(r.confidence < 0.5 for r in result) if result else True

    def test_extract_authors_returns_field_extractions(self) -> None:
        """Each author should be a FieldExtraction with confidence."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Title

        John Smith, Jane Doe

        Content...
        """

        result = extract_authors(text)

        for author in result:
            assert hasattr(author, "value")
            assert hasattr(author, "confidence")
            assert hasattr(author, "source")
            assert author.source == "heuristic"

    def test_extract_authors_handles_initials(self) -> None:
        """Authors with initials should be parsed correctly."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Research Paper

        J. Smith, A.B. Johnson

        Abstract...
        """

        result = extract_authors(text)

        assert len(result) >= 2

    def test_extract_authors_academic_format(self) -> None:
        """Academic format (Last, First) should be handled."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Journal Article

        Smith, John; Doe, Jane; Wilson, Robert

        Abstract...
        """

        result = extract_authors(text)

        assert len(result) == 3

    def test_extract_authors_superscript_affiliations(self) -> None:
        """Superscript affiliation markers should be stripped."""
        from local_library.ingestion.text_extraction import extract_authors

        text = """Paper Title

        John Smith¹, Jane Doe², Bob Wilson¹

        ¹MIT, ²Stanford

        Abstract...
        """

        result = extract_authors(text)

        assert len(result) == 3
        # Superscripts should be removed
        assert "¹" not in (result[0].value or "")
```

**Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/unit/test_text_extraction.py::TestAuthorExtraction -v
```

Expected: FAIL with "cannot import name 'extract_authors'"

**Step 3: Commit**

```bash
git add tests/unit/test_text_extraction.py
git commit -m "$(cat <<'EOF'
test(text_extraction): add author extraction test cases

Covers single/multiple authors, various separators (comma, and, semicolon),
affiliations, emails, superscripts, and edge cases.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Implement author extraction

**Files:**
- Modify: `src/local_library/ingestion/text_extraction.py`

**Step 1: Add author extraction implementation**

Add to `src/local_library/ingestion/text_extraction.py` after the title extraction code:

```python
# Author extraction constants
_AUTHOR_SEARCH_LINES = 50  # Search first N lines for author block
_AUTHOR_MIN_CONFIDENCE = 0.3


@dataclass(frozen=True)
class _AuthorCandidate:
    """Internal candidate for author extraction."""

    name: str
    score: float
    reasoning: str


def _clean_author_name(name: str) -> str:
    """Clean a raw author name string.

    Removes:
    - Superscript affiliation markers (¹²³ etc)
    - Email addresses
    - Parenthetical affiliations
    - Leading/trailing punctuation
    """
    # Remove superscript numbers and symbols
    name = re.sub(r"[¹²³⁴⁵⁶⁷⁸⁹⁰*†‡§]", "", name)

    # Remove email addresses
    name = re.sub(r"<[^>]+>", "", name)
    name = re.sub(r"\S+@\S+\.\S+", "", name)

    # Remove parenthetical content (affiliations)
    name = re.sub(r"\([^)]*\)", "", name)

    # Remove common affiliation patterns
    name = re.sub(r"\b(?:PhD|MD|Prof\.?|Dr\.?)\b", "", name, flags=re.IGNORECASE)

    # Clean up whitespace and punctuation
    name = re.sub(r"\s+", " ", name)
    name = name.strip(" ,;:")

    return name


def _split_author_string(text: str) -> list[str]:
    """Split a string containing multiple authors into individual names.

    Handles:
    - Comma separation: "John Smith, Jane Doe"
    - 'and' separation: "John Smith and Jane Doe"
    - Semicolon separation: "Smith, John; Doe, Jane"
    - Oxford comma: "John, Jane, and Bob"
    """
    # Normalize 'and' to comma (but not when part of name like "Anderson")
    text = re.sub(r"\s+and\s+", ", ", text, flags=re.IGNORECASE)

    # Try semicolon first (often indicates "Last, First" format)
    if ";" in text:
        parts = [p.strip() for p in text.split(";")]
    else:
        parts = [p.strip() for p in text.split(",")]

    # Filter out empty parts and clean each name
    names = []
    for part in parts:
        cleaned = _clean_author_name(part)
        # Skip if too short to be a name or if it looks like a number/date
        if len(cleaned) >= 3 and not cleaned.isdigit():
            names.append(cleaned)

    return names


def _is_likely_author_line(line: str) -> tuple[bool, float, str]:
    """Check if a line likely contains author names.

    Returns:
        Tuple of (is_likely, confidence, reasoning)
    """
    line_lower = line.lower().strip()

    # Skip empty lines
    if not line_lower:
        return False, 0.0, "empty line"

    # Skip if too long (likely paragraph)
    if len(line) > 200:
        return False, 0.0, "too long for author line"

    # Skip if starts with common non-author patterns
    skip_patterns = [
        r"^abstract[\s:.]",
        r"^introduction",
        r"^keywords?[\s:.]",
        r"^\d+\.",  # Numbered list
        r"^#",  # Markdown header
        r"^table\s",
        r"^figure\s",
        r"^acknowledgment",
    ]
    for pattern in skip_patterns:
        if re.match(pattern, line_lower):
            return False, 0.0, f"matches skip pattern: {pattern}"

    # Positive signals
    score = 0.3
    reasons = []

    # "by" prefix is strong signal
    if re.match(r"^by\s+", line_lower):
        score += 0.3
        reasons.append("'by' prefix")

    # Contains "and" between what look like names
    if re.search(r"\b[A-Z][a-z]+\s+and\s+[A-Z][a-z]+", line):
        score += 0.2
        reasons.append("name and name pattern")

    # Contains comma-separated capitalized words (names)
    cap_words = re.findall(r"\b[A-Z][a-z]+", line)
    if len(cap_words) >= 2:
        score += 0.1
        reasons.append(f"{len(cap_words)} capitalized words")

    # Contains email (author line often has emails)
    if "@" in line:
        score += 0.15
        reasons.append("contains email")

    # Superscript markers suggest author affiliations
    if re.search(r"[¹²³⁴⁵⁶⁷⁸⁹⁰*†‡]", line):
        score += 0.15
        reasons.append("affiliation markers")

    # Academic name format: "Last, First"
    if re.search(r"[A-Z][a-z]+,\s*[A-Z]\.", line):
        score += 0.2
        reasons.append("academic format")

    # Negative signals
    # Too many numbers suggests not an author line
    digits = sum(1 for c in line if c.isdigit())
    if digits > 5:
        score -= 0.2

    # Contains date-like patterns
    if re.search(r"\b\d{4}\b", line):
        score -= 0.1

    # Contains volume/issue patterns
    if re.search(r"\bvol|issue|pp\.", line_lower):
        score -= 0.3

    score = max(0.0, min(1.0, score))
    reasoning = "; ".join(reasons) if reasons else "base heuristics"

    return score >= 0.3, score, reasoning


def _find_author_block(text: str) -> tuple[list[str], float, str]:
    """Find the author block in document text.

    Strategies (in order):
    1. Look for "by" prefix
    2. Look for lines between title and "Abstract"
    3. Look for lines with author-like patterns

    Returns:
        Tuple of (author_lines, confidence, reasoning)
    """
    lines = text.split("\n")[:_AUTHOR_SEARCH_LINES]

    # Strategy 1: Look for "by" prefix
    for i, line in enumerate(lines):
        if re.match(r"^\s*by\s+", line, re.IGNORECASE):
            # Extract the rest of the line and possibly next line
            author_text = re.sub(r"^\s*by\s+", "", line, flags=re.IGNORECASE)
            # Check if continues to next line
            if i + 1 < len(lines) and not lines[i + 1].strip().startswith(
                ("Abstract", "Introduction", "#")
            ):
                next_line = lines[i + 1].strip()
                if next_line and not _is_likely_author_line(next_line)[0]:
                    pass  # Don't extend
                elif next_line:
                    author_text += ", " + next_line
            return [author_text], 0.8, "'by' prefix detected"

    # Strategy 2: Look for lines between title and Abstract
    abstract_idx = None
    title_end_idx = 0

    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if stripped.startswith("abstract"):
            abstract_idx = i
            break
        # Track where title might end (first blank line after content)
        if i > 0 and not stripped and lines[i - 1].strip():
            if title_end_idx == 0:
                title_end_idx = i

    if abstract_idx and title_end_idx > 0 and abstract_idx > title_end_idx:
        # Lines between title and abstract
        potential_lines = []
        for i in range(title_end_idx, abstract_idx):
            line = lines[i].strip()
            if line:
                is_likely, score, _ = _is_likely_author_line(line)
                if is_likely or score > 0.2:
                    potential_lines.append(line)
        if potential_lines:
            return potential_lines, 0.6, "between title and abstract"

    # Strategy 3: Look for author-like patterns in first lines
    author_lines = []
    best_score = 0.0

    for line in lines[1:15]:  # Skip first line (likely title)
        stripped = line.strip()
        if not stripped:
            continue

        is_likely, score, reasoning = _is_likely_author_line(stripped)
        if is_likely:
            author_lines.append(stripped)
            best_score = max(best_score, score)

    if author_lines:
        return author_lines, best_score * 0.8, "author-like patterns"

    return [], 0.0, "no author block found"


def _parse_author_name(name: str) -> str:
    """Parse an author name into normalized format.

    Uses nameparser library for robust name parsing.
    Returns format: "Family, Given" for CSL-JSON compatibility.
    """
    from nameparser import HumanName

    # Clean the name first
    name = _clean_author_name(name)

    if not name:
        return ""

    # Use nameparser for robust parsing
    parsed = HumanName(name)

    # Build normalized format
    if parsed.last:
        if parsed.first:
            return f"{parsed.last}, {parsed.first}"
        return parsed.last
    elif parsed.first:
        return parsed.first

    # Fallback: return cleaned original
    return name


def extract_authors(markdown_text: str) -> tuple[FieldExtraction, ...]:
    """Extract author names from markdown text.

    Detects author block using multiple strategies:
    1. "by" keyword prefix
    2. Lines between title and Abstract
    3. Lines with author-like patterns (names, emails, affiliations)

    Args:
        markdown_text: Marker-produced markdown content

    Returns:
        Tuple of FieldExtraction objects, one per detected author
    """
    # Handle empty input
    if not markdown_text or not markdown_text.strip():
        return ()

    # Find author block
    author_lines, block_confidence, block_reasoning = _find_author_block(markdown_text)

    if not author_lines:
        return ()

    # Extract individual authors from the block
    authors: list[FieldExtraction] = []

    for line in author_lines:
        names = _split_author_string(line)

        for name in names:
            parsed = _parse_author_name(name)
            if parsed and len(parsed) >= 3:
                # Confidence combines block confidence and name quality
                name_confidence = block_confidence

                # Boost confidence for well-formed names
                if "," in parsed:  # Has family, given format
                    name_confidence = min(1.0, name_confidence + 0.1)

                authors.append(
                    FieldExtraction(
                        value=parsed,
                        confidence=round(name_confidence, 2),
                        source="heuristic",
                        alternatives=(),
                        reasoning=block_reasoning,
                    )
                )

    return tuple(authors)
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/unit/test_text_extraction.py::TestAuthorExtraction -v
```

Expected: Most tests PASS. Adjust edge cases as needed.

**Step 3: Commit**

```bash
git add src/local_library/ingestion/text_extraction.py
git commit -m "$(cat <<'EOF'
feat(text_extraction): implement author extraction with nameparser

Uses multiple detection strategies: 'by' prefix, pre-Abstract block,
and pattern matching. Names parsed via nameparser library for
family/given splitting.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Run full test suite and lint

**Files:**
- All modified files

**Step 1: Run all unit tests**

Run:
```bash
uv run pytest tests/unit/ -v
```

Expected: All tests PASS

**Step 2: Run linting**

Run:
```bash
uv run ruff check src/local_library/ingestion/text_extraction.py
uv run ruff format src/local_library/ingestion/text_extraction.py
```

Expected: No errors (or auto-fixed)

**Step 3: Commit any fixes**

```bash
git add src/local_library/ingestion/text_extraction.py tests/unit/test_text_extraction.py
git commit -m "$(cat <<'EOF'
style(text_extraction): apply ruff formatting

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_A -->

---

## Phase 3 Completion Checklist

- [ ] `nameparser` dependency added
- [ ] `extract_authors()` function implemented
- [ ] Author block detection working (by, pre-Abstract, patterns)
- [ ] Name parsing with family/given split
- [ ] All author extraction tests pass
- [ ] Linting passes
