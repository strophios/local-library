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
        passed = total - len({f[0] for f in failures})

        print(f"\n{'=' * 60}")
        print(f"Extraction Quality Summary: {passed}/{total} documents passed")
        print(f"{'=' * 60}")

        if failures:
            print("\nFailures:")
            for citekey, reason in failures:
                print(f"  - {citekey}: {reason}")

        if results:
            avg_chars = sum(r[1] for r in results) / len(results)
            avg_ratio = sum(r[2] for r in results) / len(results)
            print("\nAverages:")
            print(f"  - Character count: {avg_chars:.0f}")
            print(f"  - Printable ratio: {avg_ratio:.2%}")

        # This test always passes - it's for diagnostic output only
        # Individual parametrized tests handle actual pass/fail
