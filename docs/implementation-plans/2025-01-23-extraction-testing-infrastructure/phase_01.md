# Extraction Testing Infrastructure Implementation Plan

**Goal:** Establish pytest-based testing infrastructure to validate PDF extraction quality and metadata extraction accuracy using a golden set of ~20 PDFs with Zotero as ground-truth source.

**Architecture:** Pytest parametrization over real PDFs from `tests/extraction/golden_set/`, loading corresponding metadata from the user's Zotero library via ZoteroReader. Tests compare Marker extraction output against ground truth using normalized string similarity for titles, set-based matching for authors, and exact matching for publication years.

**Tech Stack:** pytest 8.0+, ZoteroReader (existing), PdfExtractor (existing), difflib (stdlib), dataclasses

**Scope:** 7 phases from original design (phases 1-7)

**Codebase verified:** 2025-01-23

---

## Phase 1: Directory Structure and Core Fixtures

**Goal:** Establish test directory, move golden set PDFs, create foundational fixtures.

**Codebase verification findings:**
- ✓ `pdf_test_set/` exists with 18 PDFs using citekey naming convention
- ✓ `tests/conftest.py` provides `temp_dir` fixture pattern to follow
- ✓ `tests/integration/conftest.py` provides session-scoped fixture patterns
- ✓ ZoteroReader at `src/local_library/ingestion/zotero.py` with `get_item(citekey)` method
- ✓ PdfExtractor at `src/local_library/ingestion/pdf.py` with `lazy_load=True` support
- ✗ `tests/extraction/` does not exist (expected - we're creating it)

---

<!-- START_TASK_1 -->
### Task 1: Create extraction test directory structure

**Files:**
- Create: `tests/extraction/__init__.py`
- Create: `tests/extraction/conftest.py`

**Step 1: Create the directory and __init__.py**

```bash
mkdir -p tests/extraction
touch tests/extraction/__init__.py
```

**Step 2: Create initial conftest.py with header**

Create `tests/extraction/conftest.py`:

```python
# pattern: Imperative Shell
"""
Fixtures for extraction testing infrastructure.

Provides:
- golden_set_pdfs: Discovers PDFs in golden_set/ directory
- zotero_reader: Session-scoped ZoteroReader for ground truth
- pdf_extractor: Session-scoped PdfExtractor with lazy loading
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

# Golden set directory relative to this file
GOLDEN_SET_DIR = Path(__file__).parent / "golden_set"
```

**Step 3: Verify the file was created correctly**

Run: `cat tests/extraction/conftest.py`
Expected: File contents match the code above

**Step 4: Commit**

```bash
git add tests/extraction/__init__.py tests/extraction/conftest.py
git commit -m "chore: create extraction test directory structure"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Move golden set PDFs to test directory

**Files:**
- Move: `pdf_test_set/*.pdf` → `tests/extraction/golden_set/`

**Step 1: Verify pdf_test_set exists and has PDFs**

Run: `ls pdf_test_set/*.pdf | head -3`
Expected: Lists PDF files. If directory doesn't exist or is empty, the golden set PDFs need to be obtained first.

**Step 2: Create golden_set directory and move PDFs**

```bash
mkdir -p tests/extraction/golden_set
mv pdf_test_set/*.pdf tests/extraction/golden_set/
```

**Step 3: Verify PDFs were moved**

Run: `ls tests/extraction/golden_set/ | head -5`
Expected: Lists PDF files (e.g., `Benjamin1996.pdf`, `Chalkidis2020.pdf`, etc.)

Run: `ls pdf_test_set/`
Expected: Empty or directory does not exist

**Step 4: Remove empty pdf_test_set directory if present**

```bash
rmdir pdf_test_set 2>/dev/null || true
```

**Step 5: Commit**

```bash
git add tests/extraction/golden_set/
git add -u pdf_test_set/  # Stage deletions
git commit -m "chore: move golden set PDFs to tests/extraction/golden_set"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Add golden_set_pdfs fixture

**Files:**
- Modify: `tests/extraction/conftest.py`

**Step 1: Add the golden_set_pdfs fixture**

Append to `tests/extraction/conftest.py`:

```python


def _extract_citekey_from_filename(filename: str) -> str:
    """Extract citekey from PDF filename.

    Assumes filenames follow BetterBibTeX citekey convention:
    - Author2023.pdf -> Author2023
    - AuthorYear_Title.pdf -> AuthorYear_Title

    Simply strips the .pdf extension.
    """
    return Path(filename).stem


@pytest.fixture(scope="session")
def golden_set_pdfs() -> list[tuple[Path, str]]:
    """Discover all PDFs in golden_set directory with their citekeys.

    Returns:
        List of (pdf_path, citekey) tuples sorted by citekey for deterministic
        test ordering.

    Raises:
        FileNotFoundError: If golden_set directory doesn't exist.
        ValueError: If no PDFs found in golden_set directory.
    """
    if not GOLDEN_SET_DIR.exists():
        msg = f"Golden set directory not found: {GOLDEN_SET_DIR}"
        raise FileNotFoundError(msg)

    pdfs = sorted(GOLDEN_SET_DIR.glob("*.pdf"))

    if not pdfs:
        msg = f"No PDFs found in golden set directory: {GOLDEN_SET_DIR}"
        raise ValueError(msg)

    return [(pdf, _extract_citekey_from_filename(pdf.name)) for pdf in pdfs]
```

**Step 2: Verify fixture is discoverable**

Run: `uv run pytest tests/extraction/ --collect-only 2>&1 | head -20`
Expected: Shows fixture collection without errors (may show "no tests collected" which is OK at this stage)

**Step 3: Commit**

```bash
git add tests/extraction/conftest.py
git commit -m "feat(tests): add golden_set_pdfs fixture for PDF discovery"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Add zotero_reader fixture

**Files:**
- Modify: `tests/extraction/conftest.py`

**Step 1: Add imports for ZoteroReader**

Add to the imports section at the top of `tests/extraction/conftest.py`, after the existing imports:

```python
from local_library.ingestion.zotero import ZoteroReader
```

**Step 2: Add the zotero_reader fixture**

Append to `tests/extraction/conftest.py`:

```python


# Default Zotero library location (user's home directory)
DEFAULT_ZOTERO_DIR = Path.home() / "Zotero"


@pytest.fixture(scope="session")
def zotero_reader() -> Iterator[ZoteroReader]:
    """Session-scoped ZoteroReader for loading ground truth metadata.

    Uses the user's Zotero library at ~/Zotero. Tests will be skipped
    if Zotero is not available.

    Yields:
        Configured ZoteroReader instance.
    """
    if not DEFAULT_ZOTERO_DIR.exists():
        pytest.skip(f"Zotero not found at {DEFAULT_ZOTERO_DIR}")

    library_json = DEFAULT_ZOTERO_DIR / "library.json"
    if not library_json.exists():
        pytest.skip(
            f"BetterBibTeX library.json not found at {library_json}. "
            "Export your Zotero library using BetterBibTeX."
        )

    with ZoteroReader(zotero_dir=DEFAULT_ZOTERO_DIR) as reader:
        yield reader
```

**Step 3: Verify fixture loads without error**

Run: `uv run python -c "from tests.extraction.conftest import *; print('Imports OK')"`
Expected: `Imports OK`

**Step 4: Commit**

```bash
git add tests/extraction/conftest.py
git commit -m "feat(tests): add zotero_reader fixture for ground truth loading"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Add pdf_extractor fixture

**Files:**
- Modify: `tests/extraction/conftest.py`

**Step 1: Add import for PdfExtractor**

Add to the imports section at the top of `tests/extraction/conftest.py`:

```python
from local_library.ingestion.pdf import PdfExtractor
```

**Step 2: Add the pdf_extractor fixture**

Append to `tests/extraction/conftest.py`:

```python


@pytest.fixture(scope="session")
def pdf_extractor() -> PdfExtractor:
    """Session-scoped PdfExtractor with lazy model loading.

    Uses lazy_load=True to defer loading Marker's ML models until
    the first extraction. This speeds up test collection and allows
    tests to skip if models aren't available.

    Returns:
        Configured PdfExtractor instance.
    """
    return PdfExtractor(lazy_load=True)
```

**Step 3: Verify all fixtures are discoverable**

Run: `uv run pytest tests/extraction/ --collect-only --fixtures 2>&1 | grep -E "(golden_set_pdfs|zotero_reader|pdf_extractor)"`
Expected: Shows all three fixtures listed

**Step 4: Commit**

```bash
git add tests/extraction/conftest.py
git commit -m "feat(tests): add pdf_extractor fixture with lazy loading"
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Register extraction marker in pyproject.toml

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add extraction marker to pytest configuration**

In `pyproject.toml`, locate the `[tool.pytest.ini_options]` section and add the extraction marker to the markers list. The current markers list (around line 58-63) should be updated to include:

```toml
markers = [
    "unit: Unit tests (substeps)",
    "stage: Full pipeline stage tests",
    "contract: Transition/contract tests",
    "integration: End-to-end integration tests",
    "extraction: PDF extraction quality and accuracy tests",
]
```

**Step 2: Verify marker is registered**

Run: `uv run pytest --markers | grep extraction`
Expected: Shows `@pytest.mark.extraction: PDF extraction quality and accuracy tests`

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: register extraction marker in pytest configuration"
```
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Verify Phase 1 completion

**Files:**
- None (verification only)

**Step 1: Verify directory structure**

Run: `find tests/extraction -type f | sort`
Expected output:
```
tests/extraction/__init__.py
tests/extraction/conftest.py
tests/extraction/golden_set/Benjamin1996.pdf
tests/extraction/golden_set/Chalkidis2020.pdf
... (more PDFs)
```

**Step 2: Verify fixture discovery**

Run: `uv run pytest tests/extraction/ --collect-only 2>&1 | tail -5`
Expected: Collection completes without errors (may show "no tests ran" which is expected)

**Step 3: Verify imports work**

Run: `uv run python -c "from tests.extraction.conftest import golden_set_pdfs, GOLDEN_SET_DIR; print(f'Found {len(list(GOLDEN_SET_DIR.glob(\"*.pdf\")))} PDFs')"`
Expected: `Found 18 PDFs` (or similar count)

**Step 4: Run ruff to check code quality**

Run: `uv run ruff check tests/extraction/`
Expected: No errors (or only warnings that don't block)

Run: `uv run ruff format tests/extraction/`
Expected: Files formatted (may show "X files left unchanged" or "X files reformatted")

**Step 5: Commit any formatting changes**

```bash
git add tests/extraction/
git commit -m "style: apply ruff formatting to extraction tests" --allow-empty
```

**Phase 1 complete when:**
- `tests/extraction/` directory exists with `__init__.py` and `conftest.py`
- `tests/extraction/golden_set/` contains the moved PDFs
- `pytest tests/extraction/ --collect-only` runs without error
- `extraction` marker is registered in pyproject.toml
<!-- END_TASK_7 -->
