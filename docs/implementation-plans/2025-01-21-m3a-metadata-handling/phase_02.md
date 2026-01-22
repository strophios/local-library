# Phase 2: Schema Validation

**Goal:** CSL-JSON validation using jsonschema library.

**Dependencies:** Phase 1 (error codes), `jsonschema` package dependency

**Done when:** Valid CSL-JSON passes, invalid CSL-JSON raises MetadataError with descriptive message, warnings collected for missing optional fields.

---

<!-- START_TASK_1 -->
### Task 1: Add jsonschema dependency

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add jsonschema to dependencies**

Add `jsonschema` to the `[project.dependencies]` section in `pyproject.toml`:

```toml
"jsonschema>=4.20.0",
```

Note: The exact location depends on the existing dependencies. Add it alphabetically among the existing dependencies.

**Step 2: Sync dependencies**

Run:
```bash
uv sync
```

Expected: Dependencies install successfully.

**Step 3: Verify installation**

Run:
```bash
uv run python -c "import jsonschema; print(jsonschema.__version__)"
```

Expected: Version 4.x.x printed (e.g., `4.26.0`)

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add jsonschema dependency for CSL-JSON validation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Download and cache CSL-JSON schema

**Files:**
- Create: `src/local_library/ingestion/schemas/csl-data.json`

**Step 1: Create schemas directory**

```bash
mkdir -p src/local_library/ingestion/schemas
```

**Step 2: Download CSL-JSON schema**

Download the official CSL-JSON schema from the citation-style-language/schema repository:

```bash
curl -o src/local_library/ingestion/schemas/csl-data.json \
  "https://raw.githubusercontent.com/citation-style-language/schema/v1.0.2/schemas/input/csl-data.json"
```

**Step 3: Verify schema downloaded**

Run:
```bash
uv run python -c "import json; schema = json.load(open('src/local_library/ingestion/schemas/csl-data.json')); print(schema.get('description', 'No description')[:50])"
```

Expected: Should print part of the schema description.

**Step 4: Create __init__.py for schemas package (optional, for consistency)**

```bash
touch src/local_library/ingestion/schemas/__init__.py
```

**Step 5: Commit**

```bash
git add src/local_library/ingestion/schemas/
git commit -m "chore: add CSL-JSON schema v1.0.2 for validation

Official schema from citation-style-language/schema repository.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_2 -->

<!-- START_SUBCOMPONENT_A (tasks 3-6) -->

<!-- START_TASK_3 -->
### Task 3: Create MetadataHandler with schema loading

**Files:**
- Create: `src/local_library/ingestion/metadata.py`

**Step 1: Create metadata.py with schema loading**

Create `src/local_library/ingestion/metadata.py`:

```python
"""Metadata processing handler for CSL-JSON validation and enrichment."""

# pattern: Functional Core

import json
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft7Validator

from local_library.core.errors import ErrorCode, MetadataError
from local_library.core.models import MetadataResult


# Load schema once at module level
_SCHEMA_PATH = Path(__file__).parent / "schemas" / "csl-data.json"


def _load_schema() -> dict[str, Any]:
    """Load the CSL-JSON schema from disk."""
    with open(_SCHEMA_PATH) as f:
        return json.load(f)


# Cache the validator for reuse
_CSL_SCHEMA: dict[str, Any] | None = None
_CSL_VALIDATOR: Draft7Validator | None = None


def _get_validator() -> Draft7Validator:
    """Get or create the cached CSL-JSON validator."""
    global _CSL_SCHEMA, _CSL_VALIDATOR
    if _CSL_VALIDATOR is None:
        _CSL_SCHEMA = _load_schema()
        _CSL_VALIDATOR = Draft7Validator(_CSL_SCHEMA)
    return _CSL_VALIDATOR


class MetadataHandler:
    """Validates CSL-JSON metadata and extracts indexed fields.

    Stateless handler that processes CSL-JSON input:
    1. Validates against CSL-JSON schema
    2. Generates citekey if not provided
    3. Extracts indexed fields (title, authors, date)

    The handler is source-agnostic - metadata can come from CLI input,
    PDF extraction, Zotero import, or CrossRef API.
    """

    # Valid CSL item types (subset - full list in schema)
    VALID_TYPES = frozenset({
        "article",
        "article-journal",
        "article-magazine",
        "article-newspaper",
        "bill",
        "book",
        "broadcast",
        "chapter",
        "classic",
        "collection",
        "dataset",
        "document",
        "entry",
        "entry-dictionary",
        "entry-encyclopedia",
        "event",
        "figure",
        "graphic",
        "hearing",
        "interview",
        "legal_case",
        "legislation",
        "manuscript",
        "map",
        "motion_picture",
        "musical_score",
        "pamphlet",
        "paper-conference",
        "patent",
        "performance",
        "periodical",
        "personal_communication",
        "post",
        "post-weblog",
        "regulation",
        "report",
        "review",
        "review-book",
        "software",
        "song",
        "speech",
        "standard",
        "thesis",
        "treaty",
        "webpage",
    })

    def __init__(self) -> None:
        """Initialize the handler with cached validator."""
        self._validator = _get_validator()

    def validate(self, csl_json: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate CSL-JSON against schema.

        Returns:
            Tuple of (is_valid, list of issues).
            Issues may be errors (validation fails) or warnings (validation passes
            but data is incomplete).

        Validation strategy (lenient):
        - Fatal: missing/invalid 'type' field
        - Fatal: wrong field types (string where object expected, etc.)
        - Warning: missing optional fields (abstract, DOI, etc.)
        """
        issues: list[str] = []

        # Check 'type' field explicitly (fatal if missing or invalid)
        if "type" not in csl_json:
            return False, ["missing required field: type"]

        item_type = csl_json["type"]
        if not isinstance(item_type, str):
            return False, [f"field 'type' must be string, got {type(item_type).__name__}"]

        if item_type not in self.VALID_TYPES:
            return False, [f"invalid item type: {item_type}"]

        # Run JSON Schema validation for structural issues
        errors = list(self._validator.iter_errors(csl_json))

        # Classify errors as fatal or warnings
        fatal_errors: list[str] = []
        for error in errors:
            # Type errors are fatal
            if error.validator == "type":
                path = ".".join(str(p) for p in error.path) if error.path else "root"
                fatal_errors.append(f"type error at {path}: {error.message}")
            # Required field errors depend on context
            elif error.validator == "required":
                # 'type' already checked above; other required fields are fatal
                fatal_errors.append(f"missing required field: {error.message}")
            # Additional properties errors are warnings (lenient)
            elif error.validator == "additionalProperties":
                issues.append(f"warning: {error.message}")
            else:
                # Other schema violations are fatal
                path = ".".join(str(p) for p in error.path) if error.path else "root"
                fatal_errors.append(f"schema error at {path}: {error.message}")

        if fatal_errors:
            return False, fatal_errors

        # Check for recommended but missing fields (warnings only)
        if "title" not in csl_json:
            issues.append("warning: missing recommended field 'title'")
        if "author" not in csl_json and "editor" not in csl_json:
            issues.append("warning: missing author or editor")
        if "issued" not in csl_json:
            issues.append("warning: missing publication date (issued)")

        return True, issues

    def process(self, csl_json: dict[str, Any], citekey: str | None = None) -> MetadataResult:
        """Process CSL-JSON metadata.

        Args:
            csl_json: CSL-JSON metadata dictionary
            citekey: Optional override for citation key. If not provided,
                     will be generated from metadata.

        Returns:
            MetadataResult with validated metadata and extracted fields

        Raises:
            MetadataError: If validation fails
        """
        # Validate
        is_valid, issues = self.validate(csl_json)
        if not is_valid:
            raise MetadataError(
                f"invalid CSL-JSON: {'; '.join(issues)}",
                ErrorCode.METADATA_INVALID_SCHEMA,
                details={"issues": issues},
            )

        # Separate warnings from errors
        warnings = [i for i in issues if i.startswith("warning:")]

        # Generate or validate citekey
        if citekey is None:
            # Citekey generation will be implemented in Phase 3
            # For now, use a placeholder
            citekey = self._generate_citekey(csl_json)
        else:
            # Validate provided citekey format
            if not self._is_valid_citekey(citekey):
                raise MetadataError(
                    f"invalid citekey format: {citekey}",
                    ErrorCode.METADATA_CITEKEY_INVALID,
                    details={"citekey": citekey},
                )

        # Extract indexed fields (will be fully implemented in Phase 4)
        title = self._extract_title(csl_json)
        authors, author_list = self._extract_authors(csl_json)
        issued_date = self._extract_issued_date(csl_json)

        return MetadataResult.create(
            csl_json=csl_json,
            citekey=citekey,
            title=title,
            authors=authors,
            issued_date=issued_date,
            validation_warnings=warnings,
            author_list=author_list,
        )

    def _generate_citekey(self, csl_json: dict[str, Any]) -> str:
        """Generate a citekey from metadata.

        Full implementation in Phase 3. This is a placeholder.
        """
        # Placeholder: will be replaced in Phase 3
        import hashlib
        json_str = json.dumps(csl_json, sort_keys=True)
        hash_prefix = hashlib.sha256(json_str.encode()).hexdigest()[:8]
        return f"unknown-{hash_prefix}"

    def _is_valid_citekey(self, citekey: str) -> bool:
        """Check if a citekey has valid format.

        Valid citekeys:
        - Non-empty
        - No whitespace
        - Alphanumeric with optional hyphens and underscores
        """
        if not citekey or not citekey.strip():
            return False
        # Allow alphanumeric, hyphens, underscores
        import re
        return bool(re.match(r'^[\w-]+$', citekey))

    def _extract_title(self, csl_json: dict[str, Any]) -> str | None:
        """Extract title for indexing."""
        return csl_json.get("title")

    def _extract_authors(self, csl_json: dict[str, Any]) -> tuple[str | None, list[str]]:
        """Extract authors for indexing.

        Returns:
            Tuple of (formatted_string, list_of_names)
            Formatted string like "Smith, J.; Jones, M."
        """
        # Placeholder: full implementation in Phase 4
        authors = csl_json.get("author", [])
        if not authors:
            return None, []

        author_list: list[str] = []
        for author in authors:
            if isinstance(author, dict):
                if "literal" in author:
                    author_list.append(author["literal"])
                elif "family" in author:
                    name = author["family"]
                    if "given" in author:
                        # Abbreviate given name
                        given = author["given"]
                        initials = "".join(g[0] + "." for g in given.split() if g)
                        name = f"{name}, {initials}"
                    author_list.append(name)

        authors_str = "; ".join(author_list) if author_list else None
        return authors_str, author_list

    def _extract_issued_date(self, csl_json: dict[str, Any]) -> str | None:
        """Extract issued date for indexing.

        Returns ISO date (YYYY-MM-DD) or year only (YYYY).
        """
        issued = csl_json.get("issued")
        if not issued:
            return None

        date_parts = issued.get("date-parts")
        if not date_parts or not date_parts[0]:
            return None

        parts = date_parts[0]
        if len(parts) >= 3:
            return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"
        elif len(parts) >= 2:
            return f"{parts[0]:04d}-{parts[1]:02d}"
        elif len(parts) >= 1:
            return str(parts[0])

        return None
```

**Step 2: Verify module imports**

Run:
```bash
uv run python -c "from local_library.ingestion.metadata import MetadataHandler; h = MetadataHandler(); print('Handler created')"
```

Expected: `Handler created`

**Step 3: Commit**

```bash
git add src/local_library/ingestion/metadata.py
git commit -m "feat(ingestion): add MetadataHandler with schema validation

Validates CSL-JSON against official schema with lenient strategy:
- Fatal: missing/invalid type, wrong field types
- Warning: missing optional fields

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Write tests for schema validation - valid input

**Files:**
- Create: `tests/unit/test_metadata.py`

**Step 1: Create test file with valid input tests**

Create `tests/unit/test_metadata.py`:

```python
"""Unit tests for metadata processing."""

from typing import Any

import pytest

from local_library.core.errors import ErrorCode, MetadataError
from local_library.core.models import MetadataResult
from local_library.ingestion.metadata import MetadataHandler


class TestMetadataHandlerValidation:
    """Tests for MetadataHandler.validate()."""

    @pytest.fixture
    def handler(self) -> MetadataHandler:
        """Provide a MetadataHandler instance."""
        return MetadataHandler()

    def test_valid_minimal_article(self, handler: MetadataHandler) -> None:
        """Minimal valid CSL-JSON should pass validation."""
        csl_json = {"type": "article-journal", "title": "Test Article"}

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is True
        # May have warnings for missing optional fields
        assert not any(i for i in issues if not i.startswith("warning:"))

    def test_valid_complete_article(self, handler: MetadataHandler) -> None:
        """Complete article with all common fields should pass."""
        csl_json = {
            "type": "article-journal",
            "title": "Attention Is All You Need",
            "author": [
                {"family": "Vaswani", "given": "Ashish"},
                {"family": "Shazeer", "given": "Noam"},
            ],
            "issued": {"date-parts": [[2017]]},
            "container-title": "Advances in Neural Information Processing Systems",
            "volume": "30",
            "DOI": "10.48550/arXiv.1706.03762",
        }

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is True

    def test_valid_book(self, handler: MetadataHandler) -> None:
        """Valid book entry should pass."""
        csl_json = {
            "type": "book",
            "title": "The Art of Computer Programming",
            "author": [{"family": "Knuth", "given": "Donald E."}],
            "issued": {"date-parts": [[1968]]},
            "publisher": "Addison-Wesley",
            "ISBN": "978-0-201-89683-1",
        }

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is True

    def test_valid_chapter(self, handler: MetadataHandler) -> None:
        """Valid chapter entry should pass."""
        csl_json = {
            "type": "chapter",
            "title": "A Chapter Title",
            "author": [{"family": "Author", "given": "Test"}],
            "container-title": "Book Title",
            "editor": [{"family": "Editor", "given": "An"}],
            "issued": {"date-parts": [[2020]]},
        }

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is True

    def test_valid_webpage(self, handler: MetadataHandler) -> None:
        """Valid webpage entry should pass."""
        csl_json = {
            "type": "webpage",
            "title": "Example Webpage",
            "URL": "https://example.com/page",
            "accessed": {"date-parts": [[2024, 1, 15]]},
        }

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is True

    def test_valid_with_literal_author(self, handler: MetadataHandler) -> None:
        """Author with literal name (organization) should pass."""
        csl_json = {
            "type": "report",
            "title": "Annual Report 2023",
            "author": [{"literal": "World Health Organization"}],
            "issued": {"date-parts": [[2023]]},
        }

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is True


class TestMetadataHandlerValidationFailures:
    """Tests for MetadataHandler validation failures."""

    @pytest.fixture
    def handler(self) -> MetadataHandler:
        """Provide a MetadataHandler instance."""
        return MetadataHandler()

    def test_missing_type_is_fatal(self, handler: MetadataHandler) -> None:
        """Missing 'type' field should fail validation."""
        csl_json = {"title": "Test Article"}

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is False
        assert any("type" in i for i in issues)

    def test_invalid_type_value_is_fatal(self, handler: MetadataHandler) -> None:
        """Invalid 'type' value should fail validation."""
        csl_json = {"type": "not-a-valid-type", "title": "Test"}

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is False
        assert any("invalid item type" in i for i in issues)

    def test_type_not_string_is_fatal(self, handler: MetadataHandler) -> None:
        """Non-string 'type' should fail validation."""
        csl_json: dict[str, Any] = {"type": 123, "title": "Test"}

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is False
        assert any("must be string" in i for i in issues)


class TestMetadataHandlerWarnings:
    """Tests for validation warnings (non-fatal issues)."""

    @pytest.fixture
    def handler(self) -> MetadataHandler:
        """Provide a MetadataHandler instance."""
        return MetadataHandler()

    def test_missing_title_is_warning(self, handler: MetadataHandler) -> None:
        """Missing title should produce warning but pass validation."""
        csl_json = {"type": "article-journal"}

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is True
        assert any("title" in i and "warning" in i for i in issues)

    def test_missing_author_is_warning(self, handler: MetadataHandler) -> None:
        """Missing author should produce warning but pass validation."""
        csl_json = {"type": "article-journal", "title": "Test"}

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is True
        assert any("author" in i and "warning" in i for i in issues)

    def test_missing_issued_is_warning(self, handler: MetadataHandler) -> None:
        """Missing issued date should produce warning but pass validation."""
        csl_json = {
            "type": "article-journal",
            "title": "Test",
            "author": [{"family": "Test", "given": "A."}],
        }

        is_valid, issues = handler.validate(csl_json)

        assert is_valid is True
        assert any("issued" in i and "warning" in i for i in issues)
```

**Step 2: Run tests**

Run:
```bash
uv run pytest tests/unit/test_metadata.py -v
```

Expected: All tests pass.

**Step 3: Commit**

```bash
git add tests/unit/test_metadata.py
git commit -m "test(ingestion): add schema validation tests for MetadataHandler

Tests valid input, validation failures, and warning cases.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Write tests for MetadataHandler.process()

**Files:**
- Modify: `tests/unit/test_metadata.py` (add new test class)

**Step 1: Add process() tests**

Add to `tests/unit/test_metadata.py`:

```python


class TestMetadataHandlerProcess:
    """Tests for MetadataHandler.process()."""

    @pytest.fixture
    def handler(self) -> MetadataHandler:
        """Provide a MetadataHandler instance."""
        return MetadataHandler()

    def test_process_returns_metadata_result(self, handler: MetadataHandler) -> None:
        """process() should return MetadataResult."""
        csl_json = {"type": "article-journal", "title": "Test Article"}

        result = handler.process(csl_json)

        assert isinstance(result, MetadataResult)
        assert result.csl_json == csl_json

    def test_process_extracts_title(self, handler: MetadataHandler) -> None:
        """process() should extract title for indexing."""
        csl_json = {"type": "book", "title": "The Great Book"}

        result = handler.process(csl_json)

        assert result.title == "The Great Book"

    def test_process_extracts_authors(self, handler: MetadataHandler) -> None:
        """process() should extract and format authors."""
        csl_json = {
            "type": "article-journal",
            "title": "Test",
            "author": [
                {"family": "Smith", "given": "John"},
                {"family": "Jones", "given": "Mary Ann"},
            ],
        }

        result = handler.process(csl_json)

        assert result.authors is not None
        assert "Smith" in result.authors
        assert "Jones" in result.authors
        assert len(result.author_list) == 2

    def test_process_extracts_literal_author(self, handler: MetadataHandler) -> None:
        """process() should handle literal/organizational authors."""
        csl_json = {
            "type": "report",
            "title": "Report",
            "author": [{"literal": "United Nations"}],
        }

        result = handler.process(csl_json)

        assert result.authors == "United Nations"
        assert result.author_list == ("United Nations",)

    def test_process_extracts_issued_year(self, handler: MetadataHandler) -> None:
        """process() should extract year-only date."""
        csl_json = {
            "type": "book",
            "title": "Test",
            "issued": {"date-parts": [[2020]]},
        }

        result = handler.process(csl_json)

        assert result.issued_date == "2020"

    def test_process_extracts_issued_full_date(self, handler: MetadataHandler) -> None:
        """process() should extract full date as ISO format."""
        csl_json = {
            "type": "article-journal",
            "title": "Test",
            "issued": {"date-parts": [[2020, 6, 15]]},
        }

        result = handler.process(csl_json)

        assert result.issued_date == "2020-06-15"

    def test_process_uses_provided_citekey(self, handler: MetadataHandler) -> None:
        """process() should use provided citekey if given."""
        csl_json = {"type": "article-journal", "title": "Test"}

        result = handler.process(csl_json, citekey="CustomKey2020")

        assert result.citekey == "CustomKey2020"

    def test_process_generates_citekey_if_not_provided(self, handler: MetadataHandler) -> None:
        """process() should generate citekey if not provided."""
        csl_json = {"type": "article-journal", "title": "Test"}

        result = handler.process(csl_json)

        assert result.citekey is not None
        assert len(result.citekey) > 0

    def test_process_raises_for_invalid_csl(self, handler: MetadataHandler) -> None:
        """process() should raise MetadataError for invalid CSL-JSON."""
        csl_json = {"title": "No type field"}  # Missing required 'type'

        with pytest.raises(MetadataError) as exc_info:
            handler.process(csl_json)

        assert exc_info.value.code == ErrorCode.METADATA_INVALID_SCHEMA

    def test_process_raises_for_invalid_citekey(self, handler: MetadataHandler) -> None:
        """process() should raise MetadataError for invalid citekey format."""
        csl_json = {"type": "article-journal", "title": "Test"}

        with pytest.raises(MetadataError) as exc_info:
            handler.process(csl_json, citekey="invalid key with spaces")

        assert exc_info.value.code == ErrorCode.METADATA_CITEKEY_INVALID

    def test_process_collects_warnings(self, handler: MetadataHandler) -> None:
        """process() should collect validation warnings in result."""
        csl_json = {"type": "article-journal"}  # Missing title, author, issued

        result = handler.process(csl_json)

        assert len(result.validation_warnings) > 0
        assert any("title" in w for w in result.validation_warnings)
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
git commit -m "test(ingestion): add process() tests for MetadataHandler

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Run full test suite and verify Phase 2 complete

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
git commit -m "chore: Phase 2 complete - schema validation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```
<!-- END_TASK_6 -->

<!-- END_SUBCOMPONENT_A -->

---

## Phase 2 Completion Criteria

- [ ] jsonschema dependency added and installed
- [ ] CSL-JSON schema v1.0.2 cached locally
- [ ] MetadataHandler validates CSL-JSON against schema
- [ ] Valid CSL-JSON passes validation
- [ ] Invalid CSL-JSON raises MetadataError with METADATA_INVALID_SCHEMA
- [ ] Missing optional fields produce warnings (not errors)
- [ ] MetadataHandler.process() returns MetadataResult
- [ ] All tests pass
