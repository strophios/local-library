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

    from local_library.ingestion.zotero import ZoteroReader

# Golden set directory relative to this file
GOLDEN_SET_DIR = Path(__file__).parent / "golden_set"


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
    from local_library.ingestion.zotero import ZoteroReader

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
