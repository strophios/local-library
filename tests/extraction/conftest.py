# pattern: Imperative Shell
"""
Fixtures for extraction testing infrastructure.

Provides:
- golden_set_pdfs: Discovers PDFs in golden_set/ directory
- zotero_reader: Session-scoped ZoteroReader for ground truth
- pdf_extractor: Session-scoped PdfExtractor with lazy loading
- ground_truth: Loads and normalizes Zotero metadata for comparison
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

    from local_library.ingestion.pdf import PdfExtractor
    from local_library.ingestion.zotero import ZoteroReader

# Golden set directory relative to this file
GOLDEN_SET_DIR = Path(__file__).parent / "golden_set"


def _normalize_title(title: str) -> str:
    """Normalize title for comparison.

    Strips whitespace and converts to lowercase for case-insensitive
    comparison. Preserves internal whitespace for word matching.

    Args:
        title: Raw title string from CSL-JSON

    Returns:
        Normalized title (stripped, lowercased)
    """
    return title.strip().lower()


def _normalize_author_name(author: dict[str, Any]) -> str:
    """Normalize a single author entry to "Family, Given" format.

    Handles both personal names (family/given) and organizational names (literal).

    Args:
        author: Single author dict from CSL-JSON author array

    Returns:
        Normalized name string: "Family, Given" or literal name
    """
    if "literal" in author:
        # Organizational author
        return author["literal"].strip()

    family = author.get("family", "").strip()
    given = author.get("given", "").strip()

    if family and given:
        return f"{family}, {given}"
    if family:
        return family
    if given:
        return given
    return ""


def _normalize_authors(authors: list[dict[str, Any]]) -> tuple[str, ...]:
    """Normalize author list for comparison.

    Converts all authors to "Family, Given" format and sorts alphabetically
    for order-independent comparison.

    Args:
        authors: Author array from CSL-JSON

    Returns:
        Tuple of normalized author names, sorted alphabetically
    """
    normalized = [_normalize_author_name(a) for a in authors]
    # Filter out empty strings from malformed entries
    normalized = [n for n in normalized if n]
    # Sort for order-independent comparison
    return tuple(sorted(normalized))


def _extract_year(issued: dict[str, Any] | None) -> str | None:
    """Extract publication year from CSL-JSON issued field.

    CSL-JSON date format: {"date-parts": [[2023, 5, 15]]} or {"date-parts": [[2023]]}
    The first element of date-parts[0] is the year.

    Args:
        issued: The "issued" field from CSL-JSON, or None

    Returns:
        Year as string (e.g., "2023") or None if not available
    """
    if not issued:
        return None

    date_parts = issued.get("date-parts")
    if not date_parts or not date_parts[0]:
        return None

    year = date_parts[0][0]
    if year is None:
        return None

    return str(year)


@dataclass(frozen=True)
class GroundTruth:
    """Ground truth metadata for a single document.

    Normalized from CSL-JSON for consistent comparison against extracted metadata.
    All fields use normalized string forms suitable for comparison.

    Attributes:
        citekey: BetterBibTeX citation key (lookup key)
        title: Document title, stripped and lowercased
        authors: Tuple of author names in "Family, Given" format, sorted
        issued_year: Publication year as string, or None if not available
    """

    citekey: str
    title: str
    authors: tuple[str, ...]
    issued_year: str | None

    @classmethod
    def from_csl_json(cls, citekey: str, csl_json: dict[str, Any]) -> GroundTruth:
        """Create GroundTruth from CSL-JSON metadata.

        Normalizes:
        - Title: stripped, lowercased
        - Authors: "Family, Given" format, sorted alphabetically
        - Year: extracted from date-parts[0][0]

        Args:
            citekey: The citation key for this item
            csl_json: CSL-JSON metadata dictionary

        Returns:
            Normalized GroundTruth instance
        """
        title = _normalize_title(csl_json.get("title", ""))
        authors = _normalize_authors(csl_json.get("author", []))
        issued_year = _extract_year(csl_json.get("issued"))

        return cls(
            citekey=citekey,
            title=title,
            authors=authors,
            issued_year=issued_year,
        )


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


@pytest.fixture(scope="session")
def pdf_extractor() -> PdfExtractor:
    """Session-scoped PdfExtractor with lazy model loading.

    Uses lazy_load=True to defer loading Marker's ML models until
    the first extraction. This speeds up test collection and allows
    tests to skip if models aren't available.

    Returns:
        Configured PdfExtractor instance.
    """
    from local_library.ingestion.pdf import PdfExtractor

    return PdfExtractor(lazy_load=True)


@pytest.fixture(scope="session")
def ground_truth(
    zotero_reader: ZoteroReader,
    golden_set_pdfs: list[tuple[Path, str]],
) -> dict[str, GroundTruth]:
    """Load ground truth metadata for all golden set documents.

    Looks up each citekey in Zotero and normalizes the CSL-JSON metadata
    for comparison. Documents without Zotero entries are skipped with a
    warning.

    Args:
        zotero_reader: Session-scoped ZoteroReader
        golden_set_pdfs: List of (path, citekey) tuples from golden set

    Returns:
        Dictionary mapping citekey to GroundTruth
    """
    import warnings

    from local_library.core.errors import ZoteroError

    truth: dict[str, GroundTruth] = {}

    for _pdf_path, citekey in golden_set_pdfs:
        try:
            item = zotero_reader.get_item(citekey)
            truth[citekey] = GroundTruth.from_csl_json(citekey, item.csl_json)
        except ZoteroError as e:
            warnings.warn(
                f"Could not load ground truth for {citekey}: {e}",
                stacklevel=2,
            )

    if not truth:
        pytest.skip("No ground truth could be loaded from Zotero")

    return truth
