# pattern: Imperative Shell
"""Tests for metadata extraction accuracy validation.

Validates that metadata extracted from PDF content matches ground truth
from Zotero. This is the M3b validation infrastructure.

Until M3b implements actual metadata extraction heuristics, these tests
will skip. Once extraction logic exists, tests automatically validate
against the golden set.

Accuracy thresholds:
- Title: 0.9 (90% similarity)
- Authors: 0.7 (70% Jaccard overlap)
- Year: exact match
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from local_library.ingestion.pdf import PdfExtractor
    from tests.extraction.conftest import GroundTruth

# Accuracy thresholds for M3b validation
TITLE_THRESHOLD = 0.9
AUTHOR_THRESHOLD = 0.7


def extract_metadata_from_text(text: str) -> dict:
    """Extract bibliographic metadata from document text.

    PLACEHOLDER: This function will be implemented in M3b.
    For now, returns empty dict to indicate no extraction capability.

    When M3b is implemented, this should:
    - Extract title from first lines / header patterns
    - Extract authors from author line patterns
    - Extract year from date patterns

    Args:
        text: Extracted text content from PDF

    Returns:
        Dict with keys: title, authors, year (all optional)
        Empty dict indicates extraction not yet implemented.
    """
    # TODO(M3b): Implement actual extraction heuristics
    # See design doc for planned approach:
    # - Title: first non-empty line, header patterns
    # - Authors: "by X, Y" patterns, affiliation proximity
    # - Year: copyright lines, date patterns
    return {}


def _extraction_implemented() -> bool:
    """Check if M3b metadata extraction is implemented.

    Returns True when extract_metadata_from_text returns actual data.
    Used to skip tests until M3b is complete.
    """
    # Test with sample text that would clearly have metadata
    sample = "Title: Test Document\nBy John Smith\n2023"
    result = extract_metadata_from_text(sample)
    return bool(result)  # Non-empty dict means implemented


# Module-level marker to skip all tests until M3b is implemented.
# This prevents session-scoped fixtures from being evaluated when extraction
# is not available, ensuring tests SKIP rather than ERROR.
pytestmark = pytest.mark.skipif(
    not _extraction_implemented(),
    reason="M3b metadata extraction not yet implemented. "
    "Implement extract_metadata_from_text() to enable these tests.",
)


@pytest.mark.extraction
class TestMetadataExtraction:
    """Tests for M3b metadata extraction accuracy.

    These tests compare extracted metadata against Zotero ground truth.
    Until M3b implements extraction, tests skip with informative messages.
    """

    def test_title_accuracy(
        self,
        pdf_path: Path,
        citekey: str,
        pdf_extractor: PdfExtractor,
        ground_truth: dict[str, GroundTruth],
    ) -> None:
        """Extracted title should match ground truth with ≥90% similarity.

        Title extraction is the primary metadata signal for identification.
        High accuracy is required for reliable matching.

        Note: Parameters (pdf_path, citekey) are populated by pytest_generate_tests()
        using the golden set PDFs from tests/extraction/golden_set/.
        This allows individual test reports for each PDF in the test matrix.
        """
        from tests.extraction.conftest import title_similarity

        if citekey not in ground_truth:
            pytest.skip(f"No ground truth available for {citekey}")

        # Extract text and metadata
        result = pdf_extractor.extract(pdf_path)
        metadata = extract_metadata_from_text(result.text)

        extracted_title = metadata.get("title", "")
        expected_title = ground_truth[citekey].title

        similarity = title_similarity(extracted_title, expected_title)

        assert similarity >= TITLE_THRESHOLD, (
            f"Title accuracy for {citekey}: {similarity:.2%} "
            f"(threshold: {TITLE_THRESHOLD:.0%})\n"
            f"  Extracted: {extracted_title!r}\n"
            f"  Expected:  {expected_title!r}"
        )

    def test_author_accuracy(
        self,
        pdf_path: Path,
        citekey: str,
        pdf_extractor: PdfExtractor,
        ground_truth: dict[str, GroundTruth],
    ) -> None:
        """Extracted authors should match ground truth with ≥70% overlap.

        Author extraction is more challenging due to varied formats.
        A lower threshold accounts for partial matches and ordering variations.

        Note: Parameters (pdf_path, citekey) are populated by pytest_generate_tests()
        using the golden set PDFs from tests/extraction/golden_set/.
        This allows individual test reports for each PDF in the test matrix.
        """
        from tests.extraction.conftest import author_match_score

        if citekey not in ground_truth:
            pytest.skip(f"No ground truth available for {citekey}")

        # Extract text and metadata
        result = pdf_extractor.extract(pdf_path)
        metadata = extract_metadata_from_text(result.text)

        extracted_authors = tuple(metadata.get("authors", []))
        expected_authors = ground_truth[citekey].authors

        score = author_match_score(extracted_authors, expected_authors)

        assert score >= AUTHOR_THRESHOLD, (
            f"Author accuracy for {citekey}: {score:.2%} "
            f"(threshold: {AUTHOR_THRESHOLD:.0%})\n"
            f"  Extracted: {extracted_authors}\n"
            f"  Expected:  {expected_authors}"
        )

    def test_year_accuracy(
        self,
        pdf_path: Path,
        citekey: str,
        pdf_extractor: PdfExtractor,
        ground_truth: dict[str, GroundTruth],
    ) -> None:
        """Extracted year should exactly match ground truth.

        Year extraction should be reliable when present in document.
        Missing ground truth years are considered passing.

        Note: Parameters (pdf_path, citekey) are populated by pytest_generate_tests()
        using the golden set PDFs from tests/extraction/golden_set/.
        This allows individual test reports for each PDF in the test matrix.
        """
        from tests.extraction.conftest import year_matches

        if citekey not in ground_truth:
            pytest.skip(f"No ground truth available for {citekey}")

        gt = ground_truth[citekey]

        # Skip if no ground truth year to compare
        if gt.issued_year is None:
            pytest.skip(f"No ground truth year for {citekey}")

        # Extract text and metadata
        result = pdf_extractor.extract(pdf_path)
        metadata = extract_metadata_from_text(result.text)

        extracted_year = metadata.get("year")

        assert year_matches(extracted_year, gt.issued_year), (
            f"Year mismatch for {citekey}\n"
            f"  Extracted: {extracted_year!r}\n"
            f"  Expected:  {gt.issued_year!r}"
        )
