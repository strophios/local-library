# pattern: Imperative Shell
"""Smoke test for extraction quality framework.

Verifies the framework runs end-to-end. Requires source documents
in sources/ directory and pdflatex installed.
"""

from __future__ import annotations

import pytest


@pytest.mark.extraction_quality
class TestExtractionQualitySmoke:
    """Smoke test that the full pipeline runs without crashing."""

    def test_report_has_documents(self, quality_report):
        """At least one source document was processed."""
        assert len(quality_report.documents) > 0

    def test_all_tiers_present(self, quality_report):
        """Each document has results for all 4 noise tiers."""
        for doc_name, doc_result in quality_report.documents.items():
            assert len(doc_result.tiers) == 4, (
                f"{doc_name} missing tiers: got {list(doc_result.tiers.keys())}"
            )

    def test_write_results(self, quality_runner, quality_report):
        """Results can be written to JSON."""
        output_path = quality_runner.write_results(quality_report)
        assert output_path.exists()
        assert output_path.stat().st_size > 0
