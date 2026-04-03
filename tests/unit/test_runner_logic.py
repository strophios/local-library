# pattern: Imperative Shell
"""Tests for runner aggregation, comparison, and serialization logic."""

from __future__ import annotations

import json
from pathlib import Path

from tests.extraction.synthetic.runner import (
    QualityReport,
    RegionScore,
    TierResult,
    _aggregate_semantic,
    _aggregate_structural,
)


class TestAggregateSemanticScores:
    """Test CER/WER averaging across regions."""

    def test_averages_correctly(self):
        scores = [
            RegionScore("r1", "heading", {"CER": 0.1, "WER": 0.2}, {}, 0.9, 1.0),
            RegionScore("r2", "heading", {"CER": 0.3, "WER": 0.4}, {}, 0.8, 1.0),
        ]
        result = _aggregate_semantic(scores)
        assert abs(result["CER"] - 0.2) < 1e-4
        assert abs(result["WER"] - 0.3) < 1e-4

    def test_empty_returns_zeros(self):
        result = _aggregate_semantic([])
        assert result["CER"] == 0.0
        assert result["WER"] == 0.0

    def test_single_score(self):
        scores = [
            RegionScore("r1", "table", {"CER": 0.05, "WER": 0.1}, {}, 0.95, 1.0),
        ]
        result = _aggregate_semantic(scores)
        assert abs(result["CER"] - 0.05) < 1e-4


class TestAggregateStructuralScores:
    """Test structural score aggregation by feature type."""

    def test_groups_by_feature_prefix(self):
        scores = [
            RegionScore("r1", "heading-h1", {"CER": 0, "WER": 0}, {"detected": True}, 0.9, 1.0),
            RegionScore("r2", "heading-h2", {"CER": 0, "WER": 0}, {"detected": True}, 0.9, 1.0),
            RegionScore("r3", "table-simple", {"CER": 0, "WER": 0}, {"detected": False}, 0.9, 1.0),
        ]
        result = _aggregate_structural(scores)
        assert "heading" in result
        assert result["heading"]["count"] == 2
        assert result["heading"]["detection_rate"] == 1.0
        assert "table" in result
        assert result["table"]["detection_rate"] == 0.0

    def test_empty_returns_empty(self):
        result = _aggregate_structural([])
        assert result == {}


class TestQualityReportSerialization:
    """Test report round-trip serialization."""

    def test_to_dict_roundtrip(self):
        report = QualityReport(
            run_id="test-run",
            pipeline_version="abc123",
            timestamp="2026-04-02T00:00:00",
        )
        data = report.to_dict()
        assert data["run_id"] == "test-run"
        assert data["pipeline_version"] == "abc123"
        assert "results" in data

    def test_json_serializable(self):
        report = QualityReport(
            run_id="test",
            pipeline_version="abc",
            timestamp="2026-04-02",
        )
        # Should not raise
        json_str = json.dumps(report.to_dict())
        parsed = json.loads(json_str)
        assert parsed["run_id"] == "test"


class TestCompareToBaseline:
    """Test regression comparison logic."""

    def test_no_baseline_returns_empty(self, tmp_path: Path):
        from tests.extraction.synthetic.runner import ExtractionQualityRunner

        runner = ExtractionQualityRunner(tmp_path, tmp_path, tmp_path)
        report = QualityReport("run", "v1", "now")
        assert runner.compare_to_baseline(report) == []

    def test_detects_semantic_regression(self, tmp_path: Path):
        from tests.extraction.synthetic.runner import ExtractionQualityRunner

        # Write a fake baseline
        baseline = {"results": {"doc1": {"T0_clean": {"semantic": {"CER": 0.05, "WER": 0.10}}}}}
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / "baseline.json").write_text(json.dumps(baseline))

        runner = ExtractionQualityRunner(tmp_path, tmp_path, results_dir)

        # Report with worse CER
        from tests.extraction.synthetic.runner import DocumentResult

        report = QualityReport("run", "v2", "now")
        doc = DocumentResult("doc1")
        doc.tiers["T0_clean"] = TierResult(
            tier="T0_clean",
            semantic_summary={"CER": 0.10, "WER": 0.10},
            structural_summary={},
            regions=[],
            alignment_failures=[],
        )
        report.documents["doc1"] = doc

        regressions = runner.compare_to_baseline(report, threshold=0.05)
        assert len(regressions) >= 1
        assert regressions[0]["metric"] == "CER"

    def test_detects_structural_regression(self, tmp_path: Path):
        from tests.extraction.synthetic.runner import ExtractionQualityRunner

        baseline = {
            "results": {
                "doc1": {
                    "T0_clean": {
                        "semantic": {"CER": 0.05, "WER": 0.10},
                        "structural": {
                            "heading": {"detection_rate": 1.0, "count": 3},
                            "table": {"detection_rate": 1.0, "count": 2},
                        },
                    }
                }
            }
        }
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / "baseline.json").write_text(json.dumps(baseline))

        runner = ExtractionQualityRunner(tmp_path, tmp_path, results_dir)

        from tests.extraction.synthetic.runner import DocumentResult

        report = QualityReport("run", "v2", "now")
        doc = DocumentResult("doc1")
        doc.tiers["T0_clean"] = TierResult(
            tier="T0_clean",
            semantic_summary={"CER": 0.05, "WER": 0.10},
            structural_summary={
                "heading": {"detection_rate": 1.0, "count": 3},
                "table": {"detection_rate": 0.5, "count": 2},
            },
            regions=[],
            alignment_failures=[],
        )
        report.documents["doc1"] = doc

        regressions = runner.compare_to_baseline(report, threshold=0.05)
        structural_regs = [r for r in regressions if r["metric"] == "detection_rate"]
        assert len(structural_regs) >= 1
        assert structural_regs[0]["document"] == "doc1"

    def test_no_regression_when_improved(self, tmp_path: Path):
        from tests.extraction.synthetic.runner import ExtractionQualityRunner

        baseline = {"results": {"doc1": {"T0_clean": {"semantic": {"CER": 0.10, "WER": 0.20}}}}}
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / "baseline.json").write_text(json.dumps(baseline))

        runner = ExtractionQualityRunner(tmp_path, tmp_path, results_dir)

        from tests.extraction.synthetic.runner import DocumentResult

        report = QualityReport("run", "v2", "now")
        doc = DocumentResult("doc1")
        doc.tiers["T0_clean"] = TierResult(
            tier="T0_clean",
            semantic_summary={"CER": 0.05, "WER": 0.10},
            structural_summary={},
            regions=[],
            alignment_failures=[],
        )
        report.documents["doc1"] = doc

        regressions = runner.compare_to_baseline(report, threshold=0.05)
        assert regressions == []
