# pattern: Imperative Shell
"""Tests for metadata extraction accuracy validation.

Validates that metadata extracted from PDF content matches ground truth
from Zotero. Uses TextMetadataExtractor from M3b implementation.

Accuracy thresholds (from design plan):
- Title: ≥80% accuracy (0.8 similarity threshold per document)
- Authors: ≥70% accuracy (0.7 Jaccard overlap)
- Date: ≥75% accuracy (exact year match)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from local_library.ingestion.pdf import ExtractionResult
    from tests.extraction.conftest import AccuracyReport, GroundTruth

# Accuracy thresholds for M3b validation (per-document)
TITLE_THRESHOLD = 0.8  # 80% similarity
AUTHOR_THRESHOLD = 0.7  # 70% Jaccard overlap
DATE_THRESHOLD = 0.75  # 75% exact match rate across golden set


def _extraction_implemented() -> bool:
    """Check if M3b metadata extraction is implemented.

    Returns True when TextMetadataExtractor is available and functional.
    """
    try:
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        # Test with sample text
        extractor = TextMetadataExtractor()
        result = extractor.extract("Title\n\nJohn Smith\n\n2023")
        return result.title.value is not None
    except (ImportError, AttributeError):
        return False


# Skip all tests if extraction not implemented
pytestmark = pytest.mark.skipif(
    not _extraction_implemented(),
    reason="M3b metadata extraction not yet implemented.",
)


def extract_metadata_from_text(text: str) -> dict:
    """Extract bibliographic metadata from document text.

    Uses TextMetadataExtractor for actual extraction.

    Args:
        text: Extracted text content from PDF

    Returns:
        Dict with keys: title, authors (list), year, confidence
    """
    from local_library.ingestion.text_extraction import TextMetadataExtractor

    extractor = TextMetadataExtractor()
    result = extractor.extract(text)

    return {
        "title": result.title.value,
        "authors": [a.value for a in result.authors if a.value],
        "year": result.date.value,
        "confidence": result.overall_confidence,
        "title_confidence": result.title.confidence,
        "author_confidence": (
            sum(a.confidence for a in result.authors) / len(result.authors)
            if result.authors
            else 0.0
        ),
        "date_confidence": result.date.confidence,
    }


@pytest.mark.extraction
class TestMetadataExtraction:
    """Tests for M3b metadata extraction accuracy.

    These tests compare extracted metadata against Zotero ground truth.
    Uses session-scoped cached_extractions to avoid redundant Marker calls.
    """

    def test_title_accuracy(
        self,
        citekey: str,
        cached_extractions: dict[str, ExtractionResult],
        ground_truth: dict[str, GroundTruth],
    ) -> None:
        """Extracted title should match ground truth with ≥80% similarity."""
        from tests.extraction.conftest import title_similarity

        if citekey not in ground_truth:
            pytest.skip(f"No ground truth available for {citekey}")

        # Get cached extraction and extract metadata
        result = cached_extractions[citekey]
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
        citekey: str,
        cached_extractions: dict[str, ExtractionResult],
        ground_truth: dict[str, GroundTruth],
    ) -> None:
        """Extracted authors should match ground truth with ≥70% overlap."""
        from tests.extraction.conftest import author_match_score

        if citekey not in ground_truth:
            pytest.skip(f"No ground truth available for {citekey}")

        # Get cached extraction and extract metadata
        result = cached_extractions[citekey]
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
        citekey: str,
        cached_extractions: dict[str, ExtractionResult],
        ground_truth: dict[str, GroundTruth],
    ) -> None:
        """Extracted year should exactly match ground truth."""
        from tests.extraction.conftest import year_matches

        if citekey not in ground_truth:
            pytest.skip(f"No ground truth available for {citekey}")

        gt = ground_truth[citekey]

        # Skip if no ground truth year to compare
        if gt.issued_year is None:
            pytest.skip(f"No ground truth year for {citekey}")

        # Get cached extraction and extract metadata
        result = cached_extractions[citekey]
        metadata = extract_metadata_from_text(result.text)

        extracted_year = metadata.get("year")

        assert year_matches(extracted_year, gt.issued_year), (
            f"Year mismatch for {citekey}\n"
            f"  Extracted: {extracted_year!r}\n"
            f"  Expected:  {gt.issued_year!r}"
        )


@pytest.mark.extraction
class TestAggregateAccuracy:
    """Tests for aggregate accuracy across the golden set.

    These tests verify that the overall extraction system meets
    the design targets when measured across all documents.
    Uses session-scoped cached_extractions to avoid redundant Marker calls.
    """

    def test_aggregate_date_accuracy_meets_threshold(
        self,
        cached_extractions: dict[str, ExtractionResult],
        ground_truth: dict[str, GroundTruth],
        golden_set_pdfs: list[tuple[Path, str]],
    ) -> None:
        """Date extraction should achieve ≥75% accuracy across golden set."""
        from tests.extraction.conftest import year_matches

        total_with_year = 0
        correct = 0

        for _pdf_path, citekey in golden_set_pdfs:
            if citekey not in ground_truth:
                continue

            gt = ground_truth[citekey]
            if gt.issued_year is None:
                continue  # Skip docs without ground truth year

            total_with_year += 1

            result = cached_extractions[citekey]
            metadata = extract_metadata_from_text(result.text)
            extracted_year = metadata.get("year")

            if year_matches(extracted_year, gt.issued_year):
                correct += 1

        if total_with_year == 0:
            pytest.skip("No documents with ground truth year available")

        accuracy = correct / total_with_year

        assert accuracy >= DATE_THRESHOLD, (
            f"Aggregate date accuracy {accuracy:.2%} below threshold {DATE_THRESHOLD:.0%}\n"
            f"  Correct: {correct}/{total_with_year}"
        )


@pytest.mark.extraction
class TestConfidenceCalibration:
    """Tests for confidence score calibration.

    Verifies that confidence scores correlate with actual accuracy:
    higher confidence should mean higher accuracy.
    Uses session-scoped cached_extractions to avoid redundant Marker calls.
    """

    def test_title_confidence_correlates_with_accuracy(
        self,
        citekey: str,
        cached_extractions: dict[str, ExtractionResult],
        ground_truth: dict[str, GroundTruth],
        accuracy_report: AccuracyReport,
    ) -> None:
        """Higher title confidence should correlate with higher accuracy.

        This test collects data for statistical analysis. The actual
        correlation check is done in the session summary.
        """
        from tests.extraction.conftest import DocumentResult, title_similarity

        if citekey not in ground_truth:
            pytest.skip(f"No ground truth available for {citekey}")

        # Get cached extraction and extract metadata
        result = cached_extractions[citekey]
        metadata = extract_metadata_from_text(result.text)

        extracted_title = metadata.get("title", "")
        expected_title = ground_truth[citekey].title

        similarity = title_similarity(extracted_title, expected_title)
        confidence = metadata.get("title_confidence", 0.0)

        # Record result for aggregation
        doc_result = DocumentResult(citekey=citekey)
        doc_result.extraction_success = True
        doc_result.title_similarity = similarity
        doc_result.extracted_title = extracted_title
        doc_result.title_confidence = confidence

        accuracy_report.add_result(doc_result)

    def test_high_confidence_implies_high_accuracy(
        self,
        citekey: str,
        cached_extractions: dict[str, ExtractionResult],
        ground_truth: dict[str, GroundTruth],
    ) -> None:
        """Documents with high confidence (>0.8) should have high accuracy.

        This is a spot check - if confidence is high, accuracy should be high.
        """
        from tests.extraction.conftest import title_similarity

        if citekey not in ground_truth:
            pytest.skip(f"No ground truth available for {citekey}")

        result = cached_extractions[citekey]
        metadata = extract_metadata_from_text(result.text)

        title_conf = metadata.get("title_confidence", 0.0)

        # Only test high-confidence extractions
        if title_conf < 0.8:
            pytest.skip(f"Title confidence {title_conf:.2f} below 0.8, skipping")

        # For high confidence, expect high accuracy
        extracted_title = metadata.get("title", "")
        expected_title = ground_truth[citekey].title
        similarity = title_similarity(extracted_title, expected_title)

        # High confidence (>0.8) should correlate with good accuracy (>0.7)
        assert similarity >= 0.7, (
            f"High confidence ({title_conf:.2f}) but low accuracy ({similarity:.2f}) for {citekey}"
        )

    def test_low_confidence_triggers_needs_review(
        self,
        citekey: str,
        cached_extractions: dict[str, ExtractionResult],
    ) -> None:
        """Documents with low confidence should have needs_review=True."""
        from local_library.ingestion.text_extraction import TextMetadataExtractor

        result = cached_extractions[citekey]

        extractor = TextMetadataExtractor(confidence_threshold=0.7)
        extraction = extractor.extract(result.text)

        # If overall confidence is low, needs_review should be True
        if extraction.overall_confidence < 0.7:
            assert extraction.needs_review is True, (
                f"Low confidence ({extraction.overall_confidence:.2f}) "
                f"but needs_review is False for {citekey}"
            )
