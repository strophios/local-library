# Phase 3: Citekey Generation

**Goal:** Generate citekeys from CSL-JSON metadata following BetterBibTeX pattern.

**Dependencies:** Phase 1 (error codes), `unidecode` package dependency

**Done when:** Citekeys generated correctly for various inputs (single/multiple authors, missing fields, non-ASCII names), override respected when `citation-key` provided.

---

<!-- START_TASK_1 -->
### Task 1: Add unidecode dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add unidecode to dependencies**

Add `unidecode` to the `[project.dependencies]` section in `pyproject.toml`:

```toml
"unidecode>=1.3.0",
```

**Step 2: Sync dependencies**

Run:
```bash
uv sync
```

Expected: Dependencies install successfully.

**Step 3: Verify installation**

Run:
```bash
uv run python -c "from unidecode import unidecode; print(unidecode('Müller'))"
```

Expected: `Muller`

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add unidecode dependency for diacritic folding

Used for citekey generation from non-ASCII author names.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-4) -->

<!-- START_TASK_2 -->
### Task 2: Implement generate_citekey function

**Files:**
- Modify: `src/local_library/ingestion/metadata.py`

**Step 1: Add imports and stopwords**

Add at the top of `metadata.py` (after existing imports):

```python
import re

from unidecode import unidecode
```

Add after the `_get_validator()` function but before the `MetadataHandler` class:

```python
# English stopwords for title word extraction
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when",
    "at", "by", "for", "with", "about", "against", "between", "into",
    "through", "during", "before", "after", "above", "below", "to", "from",
    "up", "down", "in", "out", "on", "off", "over", "under", "again",
    "further", "then", "once", "here", "there", "where", "why", "how",
    "all", "each", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "can", "will", "just", "should", "now", "of", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "having", "do",
    "does", "did", "doing", "would", "could", "might", "must", "shall",
})


def generate_citekey(csl_json: dict[str, Any]) -> str:
    """Generate a BetterBibTeX-style citekey from CSL-JSON metadata.

    Pattern: AuthorYearTitleword (e.g., "Smith2020Attention")

    Components:
    - Author: First author's family name, diacritics folded
    - Year: Four-digit year from issued.date-parts[0][0]
    - Titleword: First significant word (after stopword filtering)

    Fallback: "unknown-{hash[:8]}" if insufficient data.

    Args:
        csl_json: CSL-JSON metadata dictionary

    Returns:
        Generated citekey string
    """
    author_part = _extract_author_for_citekey(csl_json)
    year_part = _extract_year_for_citekey(csl_json)
    title_part = _extract_titleword_for_citekey(csl_json)

    # If we have at least author or title, build a key
    if author_part or title_part:
        parts = []
        if author_part:
            parts.append(author_part)
        if year_part:
            parts.append(year_part)
        if title_part:
            parts.append(title_part)
        return "".join(parts)

    # Fallback: hash-based key
    import hashlib
    json_str = json.dumps(csl_json, sort_keys=True)
    hash_prefix = hashlib.sha256(json_str.encode()).hexdigest()[:8]
    return f"unknown-{hash_prefix}"


def _extract_author_for_citekey(csl_json: dict[str, Any]) -> str:
    """Extract first author's family name for citekey.

    Handles:
    - Standard author format: {"family": "Smith", "given": "John"}
    - Literal/organizational: {"literal": "World Health Organization"}
    - Non-ASCII names: folded via unidecode

    Returns:
        Cleaned author name or empty string if no author
    """
    # Check author field first, then editor as fallback
    contributors = csl_json.get("author") or csl_json.get("editor") or []

    if not contributors:
        return ""

    first_author = contributors[0]

    if isinstance(first_author, dict):
        # Prefer family name
        if "family" in first_author:
            name = first_author["family"]
        elif "literal" in first_author:
            # For organizations, use first word
            name = first_author["literal"].split()[0] if first_author["literal"] else ""
        else:
            return ""
    elif isinstance(first_author, str):
        name = first_author
    else:
        return ""

    # Clean the name: fold diacritics, remove non-alphanumeric
    name = unidecode(name)
    name = re.sub(r'[^a-zA-Z]', '', name)

    return name


def _extract_year_for_citekey(csl_json: dict[str, Any]) -> str:
    """Extract year from issued date for citekey.

    Returns:
        Four-digit year string or empty string if not available
    """
    issued = csl_json.get("issued")
    if not issued:
        return ""

    date_parts = issued.get("date-parts")
    if not date_parts or not date_parts[0]:
        return ""

    year = date_parts[0][0]
    if year is None:
        return ""

    return str(year)


def _extract_titleword_for_citekey(csl_json: dict[str, Any]) -> str:
    """Extract first significant word from title for citekey.

    Filters out stopwords and returns first remaining word.

    Returns:
        First significant title word or empty string
    """
    title = csl_json.get("title")
    if not title:
        return ""

    # Fold diacritics and extract words
    title = unidecode(title)
    words = re.findall(r'[a-zA-Z]+', title)

    for word in words:
        word_lower = word.lower()
        if word_lower not in _STOPWORDS and len(word) > 2:
            # Return with original capitalization
            return word.capitalize()

    # All words were stopwords or too short
    return ""
```

**Step 2: Update MetadataHandler._generate_citekey()**

Replace the `_generate_citekey` method in `MetadataHandler` class:

```python
    def _generate_citekey(self, csl_json: dict[str, Any]) -> str:
        """Generate a citekey from metadata.

        Delegates to module-level generate_citekey function.
        """
        return generate_citekey(csl_json)
```

**Step 3: Verify module still imports**

Run:
```bash
uv run python -c "from local_library.ingestion.metadata import generate_citekey; print(generate_citekey({'type': 'book', 'title': 'Test Book', 'author': [{'family': 'Smith'}], 'issued': {'date-parts': [[2020]]}}))"
```

Expected: `Smith2020Test`

**Step 4: Commit**

```bash
git add src/local_library/ingestion/metadata.py
git commit -m "feat(ingestion): implement citekey generation with unidecode

BetterBibTeX-style pattern: AuthorYearTitleword
- Author: first author's family name, diacritics folded
- Year: from issued.date-parts
- Titleword: first significant word after stopword filtering
- Fallback: unknown-{hash[:8]} for incomplete data

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Write tests for citekey generation

**Files:**
- Modify: `tests/unit/test_metadata.py`

**Step 1: Add citekey generation tests**

Add to `tests/unit/test_metadata.py`:

```python


class TestCitekeyGeneration:
    """Tests for generate_citekey function."""

    def test_standard_article(self) -> None:
        """Standard article generates AuthorYearTitle key."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "article-journal",
            "title": "Attention Is All You Need",
            "author": [{"family": "Vaswani", "given": "Ashish"}],
            "issued": {"date-parts": [[2017]]},
        }

        result = generate_citekey(csl_json)

        assert result == "Vaswani2017Attention"

    def test_multiple_authors_uses_first(self) -> None:
        """Multiple authors should use only first author."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "article-journal",
            "title": "Deep Learning",
            "author": [
                {"family": "LeCun", "given": "Yann"},
                {"family": "Bengio", "given": "Yoshua"},
                {"family": "Hinton", "given": "Geoffrey"},
            ],
            "issued": {"date-parts": [[2015]]},
        }

        result = generate_citekey(csl_json)

        assert result == "LeCun2015Deep"

    def test_non_ascii_author_folded(self) -> None:
        """Non-ASCII author names should be folded to ASCII."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "article-journal",
            "title": "Zur Kritik der Gewalt",
            "author": [{"family": "Müller", "given": "Hans"}],
            "issued": {"date-parts": [[1990]]},
        }

        result = generate_citekey(csl_json)

        assert result == "Muller1990Kritik"

    def test_accented_title_folded(self) -> None:
        """Non-ASCII title words should be folded to ASCII."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "book",
            "title": "L'Étranger",
            "author": [{"family": "Camus", "given": "Albert"}],
            "issued": {"date-parts": [[1942]]},
        }

        result = generate_citekey(csl_json)

        # "L'" is filtered out, "Étranger" becomes "Etranger"
        assert result == "Camus1942Etranger"

    def test_stopwords_filtered(self) -> None:
        """Title stopwords should be filtered out."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "article-journal",
            "title": "The Role of the Hippocampus",
            "author": [{"family": "Smith", "given": "J."}],
            "issued": {"date-parts": [[2000]]},
        }

        result = generate_citekey(csl_json)

        # "The", "of" are stopwords
        assert result == "Smith2000Role"

    def test_literal_author_organization(self) -> None:
        """Literal/organizational author uses first word."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "report",
            "title": "World Development Report",
            "author": [{"literal": "World Bank Group"}],
            "issued": {"date-parts": [[2023]]},
        }

        result = generate_citekey(csl_json)

        assert result == "World2023Development"

    def test_editor_fallback_when_no_author(self) -> None:
        """Editor used when no author provided."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "book",
            "title": "Collected Essays",
            "editor": [{"family": "Johnson", "given": "Mary"}],
            "issued": {"date-parts": [[2010]]},
        }

        result = generate_citekey(csl_json)

        assert result == "Johnson2010Collected"

    def test_missing_author_still_generates_key(self) -> None:
        """Missing author should still generate key from year and title."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "article-journal",
            "title": "Anonymous Article",
            "issued": {"date-parts": [[2015]]},
        }

        result = generate_citekey(csl_json)

        assert result == "2015Anonymous"

    def test_missing_year_still_generates_key(self) -> None:
        """Missing year should still generate key from author and title."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "manuscript",
            "title": "Undated Manuscript",
            "author": [{"family": "Unknown", "given": "A."}],
        }

        result = generate_citekey(csl_json)

        assert result == "UnknownUndated"

    def test_missing_title_still_generates_key(self) -> None:
        """Missing title should still generate key from author and year."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "article-journal",
            "author": [{"family": "Smith", "given": "J."}],
            "issued": {"date-parts": [[2020]]},
        }

        result = generate_citekey(csl_json)

        assert result == "Smith2020"

    def test_fallback_for_minimal_data(self) -> None:
        """Minimal data should produce hash-based fallback key."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {"type": "document"}

        result = generate_citekey(csl_json)

        assert result.startswith("unknown-")
        assert len(result) == len("unknown-") + 8  # 8 char hash

    def test_different_inputs_produce_different_fallback_hashes(self) -> None:
        """Different inputs should produce different fallback hashes."""
        from local_library.ingestion.metadata import generate_citekey

        result1 = generate_citekey({"type": "document", "id": "1"})
        result2 = generate_citekey({"type": "document", "id": "2"})

        assert result1 != result2

    def test_hyphenated_author_name(self) -> None:
        """Hyphenated author names handled correctly."""
        from local_library.ingestion.metadata import generate_citekey

        csl_json = {
            "type": "article-journal",
            "title": "Test Article",
            "author": [{"family": "García-López", "given": "María"}],
            "issued": {"date-parts": [[2018]]},
        }

        result = generate_citekey(csl_json)

        # Hyphen removed, diacritics folded
        assert result == "GarciaLopez2018Test"
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/unit/test_metadata.py::TestCitekeyGeneration -v
```

Expected: All tests pass.

**Step 3: Commit**

```bash
git add tests/unit/test_metadata.py
git commit -m "test(ingestion): add comprehensive citekey generation tests

Tests for various author formats, non-ASCII handling, stopwords,
edge cases with missing data, and fallback behavior.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update process() tests to verify citekey generation

**Files:**
- Modify: `tests/unit/test_metadata.py`

**Step 1: Update existing process tests**

Update the `test_process_generates_citekey_if_not_provided` test in `TestMetadataHandlerProcess`:

```python
    def test_process_generates_citekey_if_not_provided(self, handler: MetadataHandler) -> None:
        """process() should generate proper citekey if not provided."""
        csl_json = {
            "type": "article-journal",
            "title": "Attention Is All You Need",
            "author": [{"family": "Vaswani", "given": "Ashish"}],
            "issued": {"date-parts": [[2017]]},
        }

        result = handler.process(csl_json)

        assert result.citekey == "Vaswani2017Attention"
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/unit/test_metadata.py::TestMetadataHandlerProcess -v
```

Expected: All tests pass.

**Step 3: Commit**

```bash
git add tests/unit/test_metadata.py
git commit -m "test(ingestion): update process() test to verify proper citekey generation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_5 -->
### Task 5: Run full test suite and verify Phase 3 complete

**Files:** None (verification only)

**Step 1: Run full test suite**

Run:
```bash
uv run pytest -v
```

Expected: All tests pass.

**Step 2: Verify lint passes**

Run:
```bash
uv run ruff check src/local_library/ingestion/metadata.py tests/unit/test_metadata.py
```

Expected: No errors.

**Step 3: Commit phase completion**

```bash
git add -A
git commit -m "chore: Phase 3 complete - citekey generation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_5 -->

---

## Phase 3 Completion Criteria

- [ ] unidecode dependency added and installed
- [ ] generate_citekey() produces BetterBibTeX-style keys (AuthorYearTitle)
- [ ] Non-ASCII characters folded to ASCII via unidecode
- [ ] Stopwords filtered from title
- [ ] Fallback "unknown-{hash}" for minimal data
- [ ] Provided citekey used when given to process()
- [ ] Invalid citekey format raises METADATA_CITEKEY_INVALID
- [ ] All tests pass
