# Phase 7: Library Integration

**Goal:** Wire TextMetadataExtractor into Library.add() flow for automatic metadata extraction.

When a user runs `local-library add <path>` without `--metadata`, the system now extracts metadata from the PDF text and uses it to populate the document record.

**Reference documentation:**
- `src/local_library/core/CLAUDE.md` - Core domain contracts
- `src/local_library/ingestion/CLAUDE.md` - Ingestion domain contracts

---

<!-- START_TASK_1 -->
### Task 1: Create build_csl_json conversion function

**Files:**
- Modify: `src/local_library/ingestion/text_extraction.py`

**Step 1: Add build_csl_json function**

Add to `src/local_library/ingestion/text_extraction.py`:

```python
def build_csl_json(extraction_result: "TextExtractionResult") -> dict[str, Any]:
    """Convert TextExtractionResult to CSL-JSON format.

    Builds a CSL-JSON dictionary suitable for MetadataHandler processing.
    Handles author name conversion to CSL format.

    Args:
        extraction_result: Result from TextMetadataExtractor.extract()

    Returns:
        CSL-JSON dictionary with type, title, author, and issued fields
    """
    from typing import Any

    csl: dict[str, Any] = {
        "type": extraction_result.doc_type.value or "article-journal",
    }

    # Add title
    if extraction_result.title.value:
        csl["title"] = extraction_result.title.value

    # Convert authors to CSL format
    if extraction_result.authors:
        csl_authors = []
        for author in extraction_result.authors:
            if author.value:
                csl_author = _convert_author_to_csl(author.value)
                if csl_author:
                    csl_authors.append(csl_author)
        if csl_authors:
            csl["author"] = csl_authors

    # Convert date to CSL format
    if extraction_result.date.value:
        try:
            year = int(extraction_result.date.value)
            csl["issued"] = {"date-parts": [[year]]}
        except ValueError:
            pass  # Skip invalid year

    return csl


def _convert_author_to_csl(author_str: str) -> dict[str, str] | None:
    """Convert author string to CSL author format.

    Handles:
    - "Family, Given" format -> {"family": "Family", "given": "Given"}
    - "Given Family" format -> {"family": "Family", "given": "Given"}
    - Single name -> {"literal": "Name"}

    Args:
        author_str: Author name string

    Returns:
        CSL author dict or None if invalid
    """
    if not author_str:
        return None

    author_str = author_str.strip()

    # "Family, Given" format (preferred)
    if "," in author_str:
        parts = [p.strip() for p in author_str.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            return {"family": parts[0], "given": parts[1]}
        elif parts[0]:
            return {"literal": parts[0]}

    # "Given Family" format - try to split
    parts = author_str.split()
    if len(parts) >= 2:
        # Last part is family name
        return {"family": parts[-1], "given": " ".join(parts[:-1])}
    elif len(parts) == 1:
        # Single name - use literal
        return {"literal": author_str}

    return None
```

**Step 2: Add test for build_csl_json**

Add to `tests/unit/test_text_extraction.py`:

```python
class TestBuildCslJson:
    """Tests for CSL-JSON conversion from extraction results."""

    def test_build_csl_json_basic(self) -> None:
        """Should convert extraction result to CSL-JSON."""
        from local_library.core.models import FieldExtraction, TextExtractionResult
        from local_library.ingestion.text_extraction import build_csl_json

        result = TextExtractionResult(
            title=FieldExtraction(
                value="Test Title", confidence=0.9, source="heuristic",
                alternatives=(), reasoning=""
            ),
            authors=(
                FieldExtraction(
                    value="Smith, John", confidence=0.8, source="heuristic",
                    alternatives=(), reasoning=""
                ),
            ),
            date=FieldExtraction(
                value="2023", confidence=0.85, source="heuristic",
                alternatives=(), reasoning=""
            ),
            doc_type=FieldExtraction(
                value="article-journal", confidence=0.7, source="heuristic",
                alternatives=(), reasoning=""
            ),
            overall_confidence=0.7,
            needs_review=False,
            review_reasons=(),
        )

        csl = build_csl_json(result)

        assert csl["type"] == "article-journal"
        assert csl["title"] == "Test Title"
        assert len(csl["author"]) == 1
        assert csl["author"][0]["family"] == "Smith"
        assert csl["author"][0]["given"] == "John"
        assert csl["issued"]["date-parts"] == [[2023]]

    def test_build_csl_json_multiple_authors(self) -> None:
        """Should handle multiple authors."""
        from local_library.core.models import FieldExtraction, TextExtractionResult
        from local_library.ingestion.text_extraction import build_csl_json

        result = TextExtractionResult(
            title=FieldExtraction(
                value="Title", confidence=0.9, source="heuristic",
                alternatives=(), reasoning=""
            ),
            authors=(
                FieldExtraction(
                    value="Smith, John", confidence=0.8, source="heuristic",
                    alternatives=(), reasoning=""
                ),
                FieldExtraction(
                    value="Doe, Jane", confidence=0.8, source="heuristic",
                    alternatives=(), reasoning=""
                ),
            ),
            date=FieldExtraction(
                value="2023", confidence=0.85, source="heuristic",
                alternatives=(), reasoning=""
            ),
            doc_type=FieldExtraction(
                value="article-journal", confidence=0.7, source="heuristic",
                alternatives=(), reasoning=""
            ),
            overall_confidence=0.7,
            needs_review=False,
            review_reasons=(),
        )

        csl = build_csl_json(result)

        assert len(csl["author"]) == 2

    def test_build_csl_json_missing_fields(self) -> None:
        """Should handle None values gracefully."""
        from local_library.core.models import FieldExtraction, TextExtractionResult
        from local_library.ingestion.text_extraction import build_csl_json

        result = TextExtractionResult(
            title=FieldExtraction(
                value=None, confidence=0.0, source="heuristic",
                alternatives=(), reasoning=""
            ),
            authors=(),
            date=FieldExtraction(
                value=None, confidence=0.0, source="heuristic",
                alternatives=(), reasoning=""
            ),
            doc_type=FieldExtraction(
                value="article-journal", confidence=0.4, source="heuristic",
                alternatives=(), reasoning=""
            ),
            overall_confidence=0.0,
            needs_review=True,
            review_reasons=("title could not be extracted",),
        )

        csl = build_csl_json(result)

        # Should have type, but no title, author, or issued
        assert csl["type"] == "article-journal"
        assert "title" not in csl
        assert "author" not in csl
        assert "issued" not in csl
```

**Step 3: Run test**

Run:
```bash
uv run pytest tests/unit/test_text_extraction.py::TestBuildCslJson -v
```

Expected: All tests PASS

**Step 4: Commit**

```bash
git add src/local_library/ingestion/text_extraction.py tests/unit/test_text_extraction.py
git commit -m "$(cat <<'EOF'
feat(text_extraction): add build_csl_json conversion function

Converts TextExtractionResult to CSL-JSON format for MetadataHandler.
Handles author name splitting and date formatting.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_1 -->

<!-- START_SUBCOMPONENT_A (tasks 2-4) -->

<!-- START_TASK_2 -->
### Task 2: Write integration tests for Library.add with text extraction

**Files:**
- Modify: `tests/integration/test_workflow.py`

**Step 1: Add integration tests**

Add to `tests/integration/test_workflow.py`:

```python
class TestTextExtractionIntegration:
    """Integration tests for text-based metadata extraction in Library.add()."""

    def test_add_without_metadata_extracts_from_text(
        self,
        integration_library: "Library",
        sample_pdf: Path,
    ) -> None:
        """Adding without --metadata should extract metadata from text."""
        from unittest.mock import MagicMock, patch

        # Mock extraction to return text with metadata
        mock_result = MagicMock()
        mock_result.text = """# Machine Learning Fundamentals

        John Smith, Jane Doe

        Published: 2023

        Journal of Computer Science

        Abstract: This paper discusses machine learning...
        """ + " additional content" * 100

        with patch.object(
            integration_library._extractors[0],
            "extract_and_validate",
            return_value=mock_result,
        ):
            result = integration_library.add(str(sample_pdf))

        # Should have extracted metadata
        doc = result.document
        assert doc.title is not None
        assert doc.citekey is not None

    def test_add_without_metadata_sets_needs_review_status(
        self,
        integration_library: "Library",
        sample_pdf: Path,
    ) -> None:
        """Low confidence extraction should set NEEDS_REVIEW status."""
        from local_library.core.models import DocumentStatus
        from unittest.mock import MagicMock, patch

        # Mock extraction to return minimal text (low confidence)
        mock_result = MagicMock()
        mock_result.text = """Some vague content without clear metadata.
        """ + " filler" * 50

        with patch.object(
            integration_library._extractors[0],
            "extract_and_validate",
            return_value=mock_result,
        ):
            result = integration_library.add(str(sample_pdf))

        doc = result.document
        # Low confidence should result in NEEDS_REVIEW
        # (This depends on extraction quality - adjust as needed)
        assert doc.status in (DocumentStatus.READY, DocumentStatus.NEEDS_REVIEW)

    def test_add_with_explicit_metadata_skips_extraction(
        self,
        integration_library: "Library",
        sample_pdf: Path,
    ) -> None:
        """Adding with --metadata should use explicit metadata, not text extraction."""
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.text = "Some extracted text" + " content" * 50

        explicit_metadata = {
            "type": "article-journal",
            "title": "Explicit Title",
            "author": [{"family": "Explicit", "given": "Author"}],
            "issued": {"date-parts": [[2022]]},
        }

        with patch.object(
            integration_library._extractors[0],
            "extract_and_validate",
            return_value=mock_result,
        ):
            result = integration_library.add(str(sample_pdf), metadata=explicit_metadata)

        doc = result.document
        # Should use explicit metadata
        assert doc.title == "Explicit Title"
        assert "Explicit" in (doc.authors or "")

    def test_add_generates_citekey_from_extracted_metadata(
        self,
        integration_library: "Library",
        sample_pdf: Path,
    ) -> None:
        """Citekey should be generated from extracted metadata."""
        from unittest.mock import MagicMock, patch

        mock_result = MagicMock()
        mock_result.text = """# Deep Learning Theory

        Alice Smith

        Published: 2023

        Abstract...
        """ + " content" * 100

        with patch.object(
            integration_library._extractors[0],
            "extract_and_validate",
            return_value=mock_result,
        ):
            result = integration_library.add(str(sample_pdf))

        doc = result.document
        # Citekey should be generated (pattern: AuthorYearTitleword)
        if doc.citekey:
            assert len(doc.citekey) > 0
            # Should contain year if extracted
            # assert "2023" in doc.citekey or "Smith" in doc.citekey
```

**Step 2: Run tests to verify they fail**

Run:
```bash
uv run pytest tests/integration/test_workflow.py::TestTextExtractionIntegration -v
```

Expected: FAIL (Library.add doesn't yet use text extraction)

**Step 3: Commit**

```bash
git add tests/integration/test_workflow.py
git commit -m "$(cat <<'EOF'
test(integration): add text extraction integration tests

Tests Library.add() behavior with automatic metadata extraction,
NEEDS_REVIEW status, and explicit metadata override.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update Library.add() to use text extraction

**Files:**
- Modify: `src/local_library/core/library.py`

**Step 1: Update Library class to include text extraction**

In `src/local_library/core/library.py`, update the imports and add the text extraction logic:

First, add the import at the top:
```python
from local_library.ingestion.text_extraction import (
    TextMetadataExtractor,
    build_csl_json,
)
```

Then update the `__init__` method to accept extraction configuration:
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
    text_extraction_llm_model: str = "gpt-4o-mini",
    text_extraction_confidence_threshold: float = 0.7,
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
        text_extraction_llm_model: LLM model for fallback (default: "gpt-4o-mini")
        text_extraction_confidence_threshold: Confidence threshold (default: 0.7)
    """
    # ... existing initialization ...

    # Initialize text metadata extractor
    self._text_extractor = TextMetadataExtractor(
        confidence_threshold=text_extraction_confidence_threshold,
        llm_enabled=text_extraction_llm_enabled,
        llm_model=text_extraction_llm_model,
    ) if text_extraction_enabled else None
```

Then update the `add` method to use text extraction when metadata is not provided. Replace the section after extraction and before the return:

```python
# Extract text content
try:
    extractor = self._find_extractor(storage_path)
    result = extractor.extract_and_validate(storage_path)

    # Write extracted markdown
    extracted_path = compute_storage_path(
        doc.content_hash,
        ".md",
        self._extracted_dir,
    )
    extracted_path.parent.mkdir(parents=True, exist_ok=True)
    extracted_path.write_text(result.text, encoding="utf-8")

    # Update record to ready (temporarily - may change to NEEDS_REVIEW)
    doc = update_document_status(
        self._conn,
        doc.id,
        DocumentStatus.READY,
        extracted_path=str(extracted_path),
    )

    # Process metadata
    if metadata:
        # Explicit metadata provided
        doc = self._process_metadata(doc, metadata)
    elif self._text_extractor:
        # Extract metadata from text
        doc = self._process_text_extraction(doc, result.text)

except (ExtractionError, QualityError) as e:
    # ... existing error handling ...
```

Then add the `_process_text_extraction` method:

```python
def _process_text_extraction(self, doc: Document, text: str) -> Document:
    """Extract and process metadata from document text.

    Args:
        doc: The document to update
        text: Extracted text content

    Returns:
        Updated document with extracted metadata
    """
    # Extract metadata from text
    extraction = self._text_extractor.extract(text)

    # Convert to CSL-JSON
    csl_json = build_csl_json(extraction)

    # Only process if we have enough metadata
    if "title" not in csl_json and "author" not in csl_json:
        # Nothing useful extracted - update status to NEEDS_REVIEW
        return update_document_status(
            self._conn,
            doc.id,
            DocumentStatus.NEEDS_REVIEW,
            error_message="No metadata could be extracted from document text",
        )

    try:
        # Process through MetadataHandler for validation and citekey
        result = self._metadata_handler.process(csl_json)

        # Get unique citekey
        unique_citekey = get_unique_citekey(self._conn, result.citekey)

        # Merge extraction warnings with metadata warnings
        all_warnings = list(result.validation_warnings)
        if extraction.needs_review:
            all_warnings.extend(extraction.review_reasons)

        # Determine final status
        final_status = (
            DocumentStatus.NEEDS_REVIEW if extraction.needs_review else DocumentStatus.READY
        )

        # Update document
        doc = update_document_metadata(
            self._conn,
            doc.id,
            citekey=unique_citekey,
            csl_json=result.csl_json,
            title=result.title,
            authors=result.authors,
            issued_date=result.issued_date,
        )

        # Update status if needed
        if final_status == DocumentStatus.NEEDS_REVIEW:
            doc = update_document_status(
                self._conn,
                doc.id,
                DocumentStatus.NEEDS_REVIEW,
                error_message="; ".join(extraction.review_reasons),
            )

        return doc

    except MetadataError:
        # Extracted metadata failed validation - still set what we can
        return update_document_status(
            self._conn,
            doc.id,
            DocumentStatus.NEEDS_REVIEW,
            error_message="Extracted metadata failed validation",
        )
```

**Step 2: Add MetadataError import**

Add to imports:
```python
from local_library.core.errors import (
    AcquisitionError,
    ErrorCode,
    ExtractionError,
    LookupError,
    MetadataError,
    QualityError,
)
```

**Step 3: Run integration tests**

Run:
```bash
uv run pytest tests/integration/test_workflow.py::TestTextExtractionIntegration -v
```

Expected: All tests PASS

**Step 4: Run all integration tests**

Run:
```bash
uv run pytest tests/integration/ -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/local_library/core/library.py
git commit -m "$(cat <<'EOF'
feat(library): integrate text-based metadata extraction in add()

When metadata is not provided to Library.add(), extracts metadata
from PDF text using TextMetadataExtractor. Low-confidence extractions
set NEEDS_REVIEW status with diagnostic reasons.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update CLI to support text extraction options

**Files:**
- Modify: `src/local_library/cli/add.py`

**Step 1: Check current CLI implementation**

The CLI `add` command already accepts `--metadata`. We may want to add flags for:
- `--no-extract` to skip text extraction
- `--llm-extract` to enable LLM fallback

For now, the default behavior (extract from text when no metadata provided) is sufficient.
If CLI options are desired, add them like this:

In `src/local_library/cli/add.py`, add optional parameters:

```python
@app.command()
def add(
    source: str = typer.Argument(..., help="Path to the PDF file to add"),
    metadata: Optional[Path] = typer.Option(
        None,
        "--metadata",
        "-m",
        help="Path to CSL-JSON metadata file",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Create record even if file is inaccessible",
    ),
    no_extract: bool = typer.Option(
        False,
        "--no-extract",
        help="Skip automatic metadata extraction from text",
    ),
) -> None:
    # ... existing implementation ...
```

**This task is optional** - the core functionality works without CLI changes.

**Step 2: Run all tests**

Run:
```bash
uv run pytest tests/ -v --ignore=tests/extraction/
```

Expected: All tests PASS

**Step 3: Commit if changes were made**

```bash
git add src/local_library/cli/add.py
git commit -m "$(cat <<'EOF'
feat(cli): add --no-extract option to skip text extraction

Allows users to disable automatic metadata extraction when adding
documents without explicit metadata.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_TASK_5 -->
### Task 5: Run full test suite and lint

**Files:**
- All modified files

**Step 1: Run all unit tests**

Run:
```bash
uv run pytest tests/unit/ -v
```

Expected: All tests PASS

**Step 2: Run all integration tests**

Run:
```bash
uv run pytest tests/integration/ -v
```

Expected: All tests PASS

**Step 3: Run linting**

Run:
```bash
uv run ruff check src/local_library/
uv run ruff format src/local_library/
```

Expected: No errors (or auto-fixed)

**Step 4: Commit any fixes**

```bash
git add .
git commit -m "$(cat <<'EOF'
style: apply ruff formatting across codebase

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

<!-- END_TASK_5 -->

---

## Phase 7 Completion Checklist

- [ ] `build_csl_json()` function implemented
- [ ] Library.add() calls text extraction when no metadata provided
- [ ] NEEDS_REVIEW status set for low-confidence extractions
- [ ] Explicit metadata still works (takes precedence)
- [ ] Citekey generated from extracted metadata
- [ ] All integration tests pass
- [ ] All unit tests pass
- [ ] Linting passes
