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

# Exported for type checking in test files
__all__ = [
    "DocumentResult",
    "GroundTruth",
    "author_match_score",
    "title_similarity",
    "year_matches",
]


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


def title_similarity(extracted: str, expected: str) -> float:
    """Calculate similarity between extracted and expected titles.

    Uses SequenceMatcher ratio for normalized string comparison.
    Both strings are normalized (stripped, lowercased) before comparison.

    Args:
        extracted: Title extracted from document
        expected: Ground truth title from Zotero

    Returns:
        Similarity score from 0.0 (no match) to 1.0 (exact match)
    """
    from difflib import SequenceMatcher

    # Normalize both for comparison
    norm_extracted = _normalize_title(extracted)
    norm_expected = _normalize_title(expected)

    if not norm_expected:
        # Can't compare against empty ground truth
        return 0.0

    if not norm_extracted:
        # No extracted title means no match
        return 0.0

    return SequenceMatcher(None, norm_extracted, norm_expected).ratio()


def author_match_score(
    extracted: tuple[str, ...],
    expected: tuple[str, ...],
) -> float:
    """Calculate match score between extracted and expected authors.

    Uses set-based Jaccard similarity: |intersection| / |union|.
    Authors are normalized to "Family, Given" format and compared
    case-insensitively.

    Args:
        extracted: Tuple of extracted author names
        expected: Tuple of ground truth author names

    Returns:
        Match score from 0.0 (no overlap) to 1.0 (perfect match)
    """
    if not expected:
        # Can't compare against empty ground truth
        return 0.0 if extracted else 1.0  # Empty expected, empty extracted = match

    if not extracted:
        # No extracted authors means no match
        return 0.0

    # Normalize to lowercase for comparison
    extracted_set = {a.lower() for a in extracted}
    expected_set = {a.lower() for a in expected}

    intersection = extracted_set & expected_set
    union = extracted_set | expected_set

    if not union:
        return 1.0  # Both empty after normalization

    return len(intersection) / len(union)


def year_matches(extracted: str | None, expected: str | None) -> bool:
    """Check if extracted year matches expected year.

    Simple exact string match after normalization. Both values are
    converted to strings and stripped before comparison.

    Args:
        extracted: Year extracted from document (or None)
        expected: Ground truth year from Zotero (or None)

    Returns:
        True if years match, False otherwise
    """
    if expected is None:
        # No ground truth year - can't verify
        return True  # Assume match if we have nothing to compare against

    if extracted is None:
        # Expected a year but didn't extract one
        return False

    # Normalize to strings and strip
    extracted_str = str(extracted).strip()
    expected_str = str(expected).strip()

    return extracted_str == expected_str


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


@dataclass
class DocumentResult:
    """Captures extraction and comparison results for a single document.

    Used for diagnostic reporting to show which documents passed/failed
    and why. Not frozen because results are built incrementally.

    Attributes:
        citekey: Document identifier
        extraction_success: Whether extraction completed without error
        extraction_error: Error message if extraction failed
        title_similarity: Score from title comparison (0.0-1.0)
        author_score: Score from author comparison (0.0-1.0)
        year_match: Whether year matched ground truth
        extracted_title: Title found in extracted text (if any)
        extracted_authors: Authors found in extracted text (if any)
        extracted_year: Year found in extracted text (if any)
    """

    citekey: str
    extraction_success: bool = False
    extraction_error: str | None = None
    title_similarity: float = 0.0
    author_score: float = 0.0
    year_match: bool = False
    extracted_title: str | None = None
    extracted_authors: tuple[str, ...] | None = None
    extracted_year: str | None = None

    def passed_title(self, threshold: float = 0.9) -> bool:
        """Check if title similarity meets threshold."""
        return self.extraction_success and self.title_similarity >= threshold

    def passed_authors(self, threshold: float = 0.7) -> bool:
        """Check if author score meets threshold."""
        return self.extraction_success and self.author_score >= threshold

    def passed_year(self) -> bool:
        """Check if year matched."""
        return self.extraction_success and self.year_match

    def passed_all(
        self,
        title_threshold: float = 0.9,
        author_threshold: float = 0.7,
    ) -> bool:
        """Check if all metadata fields passed their thresholds."""
        return (
            self.passed_title(title_threshold)
            and self.passed_authors(author_threshold)
            and self.passed_year()
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
