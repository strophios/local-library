# Phase 4: Indexed Field Extraction

**Goal:** Extract title, authors, date for indexed storage with proper formatting.

**Dependencies:** Phase 1 (MetadataResult)

**Done when:** Indexed fields extracted correctly, missing fields result in None, formatted strings suitable for display and basic search.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Implement comprehensive author extraction

**Files:**
- Modify: `src/local_library/ingestion/metadata.py`

**Step 1: Replace _extract_authors method**

Replace the `_extract_authors` method in `MetadataHandler` class with this comprehensive implementation:

```python
    def _extract_authors(self, csl_json: dict[str, Any]) -> tuple[str | None, list[str]]:
        """Extract authors for indexing.

        Returns:
            Tuple of (formatted_string, list_of_names)
            Formatted string like "Smith, J.; Jones, M.A."
            List contains individual formatted names.

        Author formatting rules:
        - Personal: "Family, G." where G. is abbreviated given names
        - Literal/org: Used as-is
        - Multiple authors: separated by "; "
        """
        # Check author field first, then editor as fallback
        contributors = csl_json.get("author") or csl_json.get("editor") or []

        if not contributors:
            return None, []

        author_list: list[str] = []
        for contributor in contributors:
            if not isinstance(contributor, dict):
                continue

            formatted = self._format_contributor(contributor)
            if formatted:
                author_list.append(formatted)

        authors_str = "; ".join(author_list) if author_list else None
        return authors_str, author_list

    def _format_contributor(self, contributor: dict[str, Any]) -> str | None:
        """Format a single contributor for display.

        Args:
            contributor: CSL-JSON contributor object

        Returns:
            Formatted name string or None
        """
        if "literal" in contributor:
            # Organizational/literal author - use as-is
            return contributor["literal"]

        if "family" not in contributor:
            return None

        family = contributor["family"]

        # Handle particles (von, de, etc.)
        if "non-dropping-particle" in contributor:
            family = f"{contributor['non-dropping-particle']} {family}"

        if "given" not in contributor:
            return family

        # Abbreviate given names to initials
        given = contributor["given"]
        initials = self._abbreviate_given_name(given)

        if initials:
            return f"{family}, {initials}"
        return family

    def _abbreviate_given_name(self, given: str) -> str:
        """Abbreviate given name to initials.

        "John" -> "J."
        "John Robert" -> "J.R."
        "J." -> "J."
        "J.R." -> "J.R."
        "Jean-Pierre" -> "J.-P."

        Args:
            given: Full given name(s)

        Returns:
            Abbreviated initials string
        """
        if not given:
            return ""

        parts: list[str] = []

        # Split on spaces first
        for part in given.split():
            if not part:
                continue

            # Handle hyphenated names (Jean-Pierre -> J.-P.)
            if "-" in part:
                hyphen_parts = []
                for hp in part.split("-"):
                    if hp:
                        # Already initial or needs abbreviation
                        if len(hp) == 1 or (len(hp) == 2 and hp.endswith(".")):
                            hyphen_parts.append(hp if hp.endswith(".") else f"{hp}.")
                        else:
                            hyphen_parts.append(f"{hp[0].upper()}.")
                if hyphen_parts:
                    parts.append("-".join(hyphen_parts))
            else:
                # Regular name part
                if len(part) == 1 or (len(part) == 2 and part.endswith(".")):
                    parts.append(part if part.endswith(".") else f"{part}.")
                else:
                    parts.append(f"{part[0].upper()}.")

        return "".join(parts)
```

**Step 2: Verify the method works**

Run:
```bash
uv run python -c "
from local_library.ingestion.metadata import MetadataHandler
h = MetadataHandler()

# Test standard author
csl = {'author': [{'family': 'Smith', 'given': 'John Robert'}]}
authors, lst = h._extract_authors(csl)
print(f'Standard: {authors}')

# Test with particle
csl = {'author': [{'family': 'Beethoven', 'given': 'Ludwig', 'non-dropping-particle': 'van'}]}
authors, lst = h._extract_authors(csl)
print(f'Particle: {authors}')

# Test multiple
csl = {'author': [
    {'family': 'Smith', 'given': 'John'},
    {'family': 'Jones', 'given': 'Mary Ann'}
]}
authors, lst = h._extract_authors(csl)
print(f'Multiple: {authors}')
"
```

Expected:
```
Standard: Smith, J.R.
Particle: van Beethoven, L.
Multiple: Smith, J.; Jones, M.A.
```

**Step 3: Commit**

```bash
git add src/local_library/ingestion/metadata.py
git commit -m "feat(ingestion): implement comprehensive author extraction

Handles personal names with initials, particles (von, de),
hyphenated given names, and organizational authors.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement comprehensive date extraction

**Files:**
- Modify: `src/local_library/ingestion/metadata.py`

**Step 1: Update _extract_issued_date method**

The existing implementation is already comprehensive. Verify it handles these cases:

1. Full date: `{"date-parts": [[2020, 6, 15]]}` -> `"2020-06-15"`
2. Year-month: `{"date-parts": [[2020, 6]]}` -> `"2020-06"`
3. Year only: `{"date-parts": [[2020]]}` -> `"2020"`
4. Missing date: `{}` -> `None`

The current implementation should already handle these. If not, update to:

```python
    def _extract_issued_date(self, csl_json: dict[str, Any]) -> str | None:
        """Extract issued date for indexing.

        Returns ISO date format:
        - Full date: YYYY-MM-DD
        - Year-month: YYYY-MM
        - Year only: YYYY

        Args:
            csl_json: CSL-JSON metadata

        Returns:
            Formatted date string or None if not available
        """
        issued = csl_json.get("issued")
        if not issued:
            return None

        date_parts = issued.get("date-parts")
        if not date_parts or not date_parts[0]:
            return None

        parts = date_parts[0]

        # Handle None values in date parts
        if not parts or parts[0] is None:
            return None

        year = parts[0]

        if len(parts) >= 3 and parts[1] is not None and parts[2] is not None:
            # Full date: YYYY-MM-DD
            return f"{int(year):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
        elif len(parts) >= 2 and parts[1] is not None:
            # Year-month: YYYY-MM
            return f"{int(year):04d}-{int(parts[1]):02d}"
        else:
            # Year only
            return str(int(year))
```

**Step 2: Verify the method works**

Run:
```bash
uv run python -c "
from local_library.ingestion.metadata import MetadataHandler
h = MetadataHandler()

tests = [
    {'issued': {'date-parts': [[2020, 6, 15]]}},  # Full date
    {'issued': {'date-parts': [[2020, 6]]}},       # Year-month
    {'issued': {'date-parts': [[2020]]}},          # Year only
    {},                                             # Missing
]

for csl in tests:
    result = h._extract_issued_date(csl)
    print(f'{csl.get(\"issued\", \"missing\")} -> {result}')
"
```

Expected:
```
{'date-parts': [[2020, 6, 15]]} -> 2020-06-15
{'date-parts': [[2020, 6]]} -> 2020-06
{'date-parts': [[2020]]} -> 2020
missing -> None
```

**Step 3: Commit (if changes made)**

```bash
git add src/local_library/ingestion/metadata.py
git commit -m "feat(ingestion): ensure comprehensive date extraction

Handles full dates, year-month, year-only, and missing dates.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Write tests for indexed field extraction

**Files:**
- Modify: `tests/unit/test_metadata.py`

**Step 1: Add comprehensive extraction tests**

Add to `tests/unit/test_metadata.py`:

```python


class TestIndexedFieldExtraction:
    """Tests for indexed field extraction methods."""

    @pytest.fixture
    def handler(self) -> MetadataHandler:
        """Provide a MetadataHandler instance."""
        return MetadataHandler()

    # --- Author extraction tests ---

    def test_extract_authors_standard_format(self, handler: MetadataHandler) -> None:
        """Standard author with family and given names."""
        csl_json = {
            "type": "article-journal",
            "author": [{"family": "Smith", "given": "John Robert"}],
        }

        result = handler.process(csl_json)

        assert result.authors == "Smith, J.R."
        assert result.author_list == ("Smith, J.R.",)

    def test_extract_authors_single_initial(self, handler: MetadataHandler) -> None:
        """Author with already-initialized given name."""
        csl_json = {
            "type": "article-journal",
            "author": [{"family": "Smith", "given": "J."}],
        }

        result = handler.process(csl_json)

        assert result.authors == "Smith, J."

    def test_extract_authors_hyphenated_given(self, handler: MetadataHandler) -> None:
        """Author with hyphenated given name."""
        csl_json = {
            "type": "article-journal",
            "author": [{"family": "Dupont", "given": "Jean-Pierre"}],
        }

        result = handler.process(csl_json)

        assert result.authors == "Dupont, J.-P."

    def test_extract_authors_with_particle(self, handler: MetadataHandler) -> None:
        """Author with non-dropping particle (von, de, etc.)."""
        csl_json = {
            "type": "book",
            "author": [
                {
                    "family": "Beethoven",
                    "given": "Ludwig",
                    "non-dropping-particle": "van",
                }
            ],
        }

        result = handler.process(csl_json)

        assert result.authors == "van Beethoven, L."

    def test_extract_authors_multiple(self, handler: MetadataHandler) -> None:
        """Multiple authors separated by semicolon."""
        csl_json = {
            "type": "article-journal",
            "author": [
                {"family": "Smith", "given": "John"},
                {"family": "Jones", "given": "Mary Ann"},
                {"family": "Brown", "given": "Robert"},
            ],
        }

        result = handler.process(csl_json)

        assert result.authors == "Smith, J.; Jones, M.A.; Brown, R."
        assert len(result.author_list) == 3

    def test_extract_authors_literal(self, handler: MetadataHandler) -> None:
        """Organizational/literal author."""
        csl_json = {
            "type": "report",
            "author": [{"literal": "World Health Organization"}],
        }

        result = handler.process(csl_json)

        assert result.authors == "World Health Organization"
        assert result.author_list == ("World Health Organization",)

    def test_extract_authors_family_only(self, handler: MetadataHandler) -> None:
        """Author with only family name (no given name)."""
        csl_json = {
            "type": "article-journal",
            "author": [{"family": "Aristotle"}],
        }

        result = handler.process(csl_json)

        assert result.authors == "Aristotle"

    def test_extract_authors_editor_fallback(self, handler: MetadataHandler) -> None:
        """Editor used when no author present."""
        csl_json = {
            "type": "book",
            "editor": [{"family": "Johnson", "given": "Mary"}],
        }

        result = handler.process(csl_json)

        assert result.authors == "Johnson, M."

    def test_extract_authors_missing(self, handler: MetadataHandler) -> None:
        """Missing author returns None."""
        csl_json = {"type": "article-journal", "title": "Anonymous Work"}

        result = handler.process(csl_json)

        assert result.authors is None
        assert result.author_list == ()

    # --- Date extraction tests ---

    def test_extract_date_full(self, handler: MetadataHandler) -> None:
        """Full date with year, month, day."""
        csl_json = {
            "type": "article-journal",
            "issued": {"date-parts": [[2020, 6, 15]]},
        }

        result = handler.process(csl_json)

        assert result.issued_date == "2020-06-15"

    def test_extract_date_year_month(self, handler: MetadataHandler) -> None:
        """Date with year and month only."""
        csl_json = {
            "type": "article-journal",
            "issued": {"date-parts": [[2020, 6]]},
        }

        result = handler.process(csl_json)

        assert result.issued_date == "2020-06"

    def test_extract_date_year_only(self, handler: MetadataHandler) -> None:
        """Date with year only."""
        csl_json = {
            "type": "book",
            "issued": {"date-parts": [[1984]]},
        }

        result = handler.process(csl_json)

        assert result.issued_date == "1984"

    def test_extract_date_missing(self, handler: MetadataHandler) -> None:
        """Missing date returns None."""
        csl_json = {"type": "manuscript"}

        result = handler.process(csl_json)

        assert result.issued_date is None

    def test_extract_date_empty_parts(self, handler: MetadataHandler) -> None:
        """Empty date-parts returns None."""
        csl_json = {
            "type": "article-journal",
            "issued": {"date-parts": [[]]},
        }

        result = handler.process(csl_json)

        assert result.issued_date is None

    def test_extract_date_pads_month_day(self, handler: MetadataHandler) -> None:
        """Month and day should be zero-padded."""
        csl_json = {
            "type": "article-journal",
            "issued": {"date-parts": [[2020, 1, 5]]},
        }

        result = handler.process(csl_json)

        assert result.issued_date == "2020-01-05"

    # --- Title extraction tests ---

    def test_extract_title(self, handler: MetadataHandler) -> None:
        """Title extracted as-is."""
        csl_json = {
            "type": "book",
            "title": "The Art of Computer Programming",
        }

        result = handler.process(csl_json)

        assert result.title == "The Art of Computer Programming"

    def test_extract_title_missing(self, handler: MetadataHandler) -> None:
        """Missing title returns None."""
        csl_json = {"type": "article-journal"}

        result = handler.process(csl_json)

        assert result.title is None
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/unit/test_metadata.py::TestIndexedFieldExtraction -v
```

Expected: All tests pass.

**Step 3: Commit**

```bash
git add tests/unit/test_metadata.py
git commit -m "test(ingestion): add comprehensive indexed field extraction tests

Tests for author formatting (initials, particles, literals),
date extraction (full/partial/missing), and title extraction.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_4 -->
### Task 4: Run full test suite and verify Phase 4 complete

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
git commit -m "chore: Phase 4 complete - indexed field extraction

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_4 -->

---

## Phase 4 Completion Criteria

- [ ] Authors extracted with proper formatting ("Family, G.")
- [ ] Author particles (von, de) included in family name
- [ ] Hyphenated given names properly abbreviated (J.-P.)
- [ ] Multiple authors separated by "; "
- [ ] Organizational/literal authors used as-is
- [ ] Editor used as fallback when no author
- [ ] Dates formatted as ISO (YYYY-MM-DD, YYYY-MM, or YYYY)
- [ ] Missing fields return None
- [ ] All tests pass
