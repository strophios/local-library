# Phase 3: Extraction Quality Tests

**Goal:** Validate Marker extraction produces usable output for each golden set PDF.

**Codebase verification findings:**
- ✓ `PdfExtractor.extract()` returns `ExtractionResult` with `text`, `character_count`, `printable_ratio`
- ✓ Quality thresholds in codebase: `min_length=100`, `min_printable_ratio=0.8`
- ✓ Test patterns use class-based organization with descriptive docstrings
- ✓ Parametrized tests not yet used in codebase but pytest supports them

---

<!-- START_TASK_1 -->
### Task 1: Create extraction quality test file

**Files:**
- Create: `tests/extraction/test_extraction_quality.py`

**Step 1: Create the test file with imports and constants**

Create `tests/extraction/test_extraction_quality.py`:

```python
# pattern: Imperative Shell
"""Tests for PDF extraction quality validation.

Validates that Marker extraction produces usable output for each document
in the golden set. Quality is measured by:
- Character count: minimum 100 characters
- Printable ratio: minimum 80% printable characters

These are M2 validation tests ensuring the extraction pipeline works
correctly before M3b metadata extraction can be attempted.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from local_library.ingestion.pdf import ExtractionResult, PdfExtractor

# Quality thresholds matching production defaults
MIN_CHARACTER_COUNT = 100
MIN_PRINTABLE_RATIO = 0.8
```

**Step 2: Verify the file is syntactically correct**

Run: `uv run python -c "import tests.extraction.test_extraction_quality; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add tests/extraction/test_extraction_quality.py
git commit -m "feat(tests): create extraction quality test file"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add parametrized test for character count

**Files:**
- Modify: `tests/extraction/test_extraction_quality.py`

**Step 1: Add the TestExtractionQuality class with character count test**

Append to `tests/extraction/test_extraction_quality.py`:

```python


@pytest.mark.extraction
class TestExtractionQuality:
    """Tests validating extraction produces usable output.

    Each test runs against all PDFs in the golden set via parametrization.
    Tests are marked with @pytest.mark.extraction for selective running.
    """

    @pytest.fixture(autouse=True)
    def _setup_extraction_cache(
        self,
        golden_set_pdfs: list[tuple[Path, str]],
        pdf_extractor: PdfExtractor,
        request: pytest.FixtureRequest,
    ) -> None:
        """Cache extraction results to avoid re-extracting for each test.

        Stores results in the class for access by individual tests.
        Uses session-scoped pdf_extractor for efficiency.
        """
        # Use request.node to access the specific PDF being tested
        # The cache is built lazily per-PDF to avoid extracting all at once
        if not hasattr(request.cls, "_extraction_cache"):
            request.cls._extraction_cache: dict[str, ExtractionResult] = {}

    def _get_extraction(
        self,
        pdf_path: Path,
        citekey: str,
        pdf_extractor: PdfExtractor,
    ) -> ExtractionResult:
        """Get cached extraction result or extract if not cached."""
        if citekey not in self._extraction_cache:
            self._extraction_cache[citekey] = pdf_extractor.extract(pdf_path)
        return self._extraction_cache[citekey]

    @pytest.mark.parametrize(
        "pdf_path,citekey",
        [],  # Will be populated by pytest_generate_tests
        indirect=False,
    )
    def test_extraction_character_count(
        self,
        pdf_path: Path,
        citekey: str,
        pdf_extractor: PdfExtractor,
    ) -> None:
        """Extraction should produce at least MIN_CHARACTER_COUNT characters.

        This validates that the PDF was successfully parsed and contains
        meaningful content, not just whitespace or extraction artifacts.
        """
        result = self._get_extraction(pdf_path, citekey, pdf_extractor)

        assert result.character_count >= MIN_CHARACTER_COUNT, (
            f"Extraction for {citekey} produced only {result.character_count} "
            f"characters (minimum: {MIN_CHARACTER_COUNT})"
        )
```

**Step 2: Add conftest hook for parametrization**

We need to add a `pytest_generate_tests` hook to conftest.py to populate the parametrize values. Add to `tests/extraction/conftest.py`:

```python


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Generate test parameters from golden set PDFs.

    Populates parametrized tests with (pdf_path, citekey) tuples from
    the golden set directory. This allows individual test reports per PDF.
    """
    if "pdf_path" in metafunc.fixturenames and "citekey" in metafunc.fixturenames:
        # Discover PDFs directly (can't use fixture in hook)
        if not GOLDEN_SET_DIR.exists():
            return

        pdfs = sorted(GOLDEN_SET_DIR.glob("*.pdf"))
        params = [(pdf, _extract_citekey_from_filename(pdf.name)) for pdf in pdfs]

        # Use citekey as test ID for readable output
        metafunc.parametrize(
            ("pdf_path", "citekey"),
            params,
            ids=[citekey for _, citekey in params],
        )
```

**Step 3: Verify test is discovered with parametrization**

Run: `uv run pytest tests/extraction/test_extraction_quality.py --collect-only 2>&1 | head -30`
Expected: Shows multiple test instances like `test_extraction_character_count[Benjamin1996]`, `test_extraction_character_count[Chalkidis2020]`, etc.

**Step 4: Commit**

```bash
git add tests/extraction/test_extraction_quality.py tests/extraction/conftest.py
git commit -m "feat(tests): add parametrized character count quality test"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add printable ratio test

**Files:**
- Modify: `tests/extraction/test_extraction_quality.py`

**Step 1: Add the printable ratio test method**

Add to the `TestExtractionQuality` class in `tests/extraction/test_extraction_quality.py`:

```python

    @pytest.mark.parametrize(
        "pdf_path,citekey",
        [],  # Will be populated by pytest_generate_tests
        indirect=False,
    )
    def test_extraction_printable_ratio(
        self,
        pdf_path: Path,
        citekey: str,
        pdf_extractor: PdfExtractor,
    ) -> None:
        """Extraction should have at least MIN_PRINTABLE_RATIO printable characters.

        This validates that the extracted text is readable content, not
        binary garbage or encoding errors. A high printable ratio indicates
        successful text extraction.
        """
        result = self._get_extraction(pdf_path, citekey, pdf_extractor)

        assert result.printable_ratio >= MIN_PRINTABLE_RATIO, (
            f"Extraction for {citekey} has printable ratio {result.printable_ratio:.2%} "
            f"(minimum: {MIN_PRINTABLE_RATIO:.0%})"
        )
```

**Step 2: Verify both tests are discovered**

Run: `uv run pytest tests/extraction/test_extraction_quality.py --collect-only 2>&1 | grep "test_extraction" | head -10`
Expected: Shows both `test_extraction_character_count` and `test_extraction_printable_ratio` tests

**Step 3: Commit**

```bash
git add tests/extraction/test_extraction_quality.py
git commit -m "feat(tests): add printable ratio quality test"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add combined quality summary test

**Files:**
- Modify: `tests/extraction/test_extraction_quality.py`

**Step 1: Add a summary test that reports overall quality**

Add to the `TestExtractionQuality` class:

```python

    def test_extraction_quality_summary(
        self,
        golden_set_pdfs: list[tuple[Path, str]],
        pdf_extractor: PdfExtractor,
    ) -> None:
        """Summary test reporting overall extraction quality across golden set.

        This test always passes but prints diagnostic information about
        extraction quality across all documents. Useful for monitoring
        overall health of the extraction pipeline.
        """
        results: list[tuple[str, int, float]] = []
        failures: list[tuple[str, str]] = []

        for pdf_path, citekey in golden_set_pdfs:
            try:
                result = pdf_extractor.extract(pdf_path)
                results.append((citekey, result.character_count, result.printable_ratio))

                # Track quality failures
                if result.character_count < MIN_CHARACTER_COUNT:
                    failures.append((citekey, f"character_count={result.character_count}"))
                if result.printable_ratio < MIN_PRINTABLE_RATIO:
                    failures.append((citekey, f"printable_ratio={result.printable_ratio:.2%}"))

            except Exception as e:
                failures.append((citekey, f"extraction_error: {e}"))

        # Print summary (visible with -v flag)
        total = len(golden_set_pdfs)
        passed = total - len(set(f[0] for f in failures))

        print(f"\n{'='*60}")
        print(f"Extraction Quality Summary: {passed}/{total} documents passed")
        print(f"{'='*60}")

        if failures:
            print("\nFailures:")
            for citekey, reason in failures:
                print(f"  - {citekey}: {reason}")

        if results:
            avg_chars = sum(r[1] for r in results) / len(results)
            avg_ratio = sum(r[2] for r in results) / len(results)
            print(f"\nAverages:")
            print(f"  - Character count: {avg_chars:.0f}")
            print(f"  - Printable ratio: {avg_ratio:.2%}")

        # This test always passes - it's for diagnostic output only
        # Individual parametrized tests handle actual pass/fail
```

**Step 2: Verify the summary test is discovered**

Run: `uv run pytest tests/extraction/test_extraction_quality.py --collect-only 2>&1 | grep "summary"`
Expected: Shows `test_extraction_quality_summary`

**Step 3: Commit**

```bash
git add tests/extraction/test_extraction_quality.py
git commit -m "feat(tests): add extraction quality summary test"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Verify Phase 3 completion

**Files:**
- None (verification only)

**Step 1: Verify all tests are discoverable**

Run: `uv run pytest tests/extraction/test_extraction_quality.py --collect-only`
Expected: Shows collection of parametrized tests for each PDF plus the summary test

**Step 2: Run ruff to check code quality**

Run: `uv run ruff check tests/extraction/`
Expected: No errors

Run: `uv run ruff format tests/extraction/`
Expected: Files formatted

**Step 3: Verify test file structure**

Run: `grep -E "^(class|def test_)" tests/extraction/test_extraction_quality.py`
Expected:
```
class TestExtractionQuality:
def test_extraction_character_count(
def test_extraction_printable_ratio(
def test_extraction_quality_summary(
```

**Step 4: Commit any formatting changes**

```bash
git add tests/extraction/
git commit -m "style: apply ruff formatting to extraction tests" --allow-empty
```

**Phase 3 complete when:**
- `test_extraction_quality.py` exists with `TestExtractionQuality` class
- Parametrized tests for character count and printable ratio are discoverable
- Summary test provides diagnostic output
- All code passes ruff check
<!-- END_TASK_5 -->
