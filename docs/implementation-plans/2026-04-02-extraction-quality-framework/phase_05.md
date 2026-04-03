## Phase 5: Test Runner and Reporting

**Goal:** Orchestrator that runs the full pipeline, produces results JSON, Rich dashboard, and regression comparison.

**Pattern:** Imperative Shell (coordinates I/O between Functional Core modules). Follows retrieval eval pattern: `.to_dict()` + `json.dumps()` for output, explicit baseline comparison.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Write runner unit tests

**Files:**
- Create: `tests/unit/test_runner_logic.py`

**Step 1: Write failing tests for aggregation and comparison logic**

These test the Functional Core parts of the runner (aggregation, comparison, serialization) without requiring Marker or PDF generation.

```python
# pattern: Imperative Shell
"""Tests for runner aggregation, comparison, and serialization logic."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

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
            RegionScore("r1", "heading-h1", {"CER": 0, "WER": 0},
                        {"detected": True}, 0.9, 1.0),
            RegionScore("r2", "heading-h2", {"CER": 0, "WER": 0},
                        {"detected": True}, 0.9, 1.0),
            RegionScore("r3", "table-simple", {"CER": 0, "WER": 0},
                        {"detected": False}, 0.9, 1.0),
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
        baseline = {
            "results": {
                "doc1": {
                    "T0_clean": {"semantic": {"CER": 0.05, "WER": 0.10}}
                }
            }
        }
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / "baseline.json").write_text(json.dumps(baseline))

        runner = ExtractionQualityRunner(tmp_path, tmp_path, results_dir)

        # Report with worse CER
        from tests.extraction.synthetic.runner import DocumentResult, TierResult

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

        from tests.extraction.synthetic.runner import DocumentResult, TierResult

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

        baseline = {
            "results": {
                "doc1": {
                    "T0_clean": {"semantic": {"CER": 0.10, "WER": 0.20}}
                }
            }
        }
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / "baseline.json").write_text(json.dumps(baseline))

        runner = ExtractionQualityRunner(tmp_path, tmp_path, results_dir)

        from tests.extraction.synthetic.runner import DocumentResult, TierResult

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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_runner_logic.py -v`
Expected: ImportError — `tests.extraction.synthetic.runner` does not exist yet

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement test runner module

**Files:**
- Create: `tests/extraction/synthetic/runner.py`

**Step 1: Implement the module**

```python
# pattern: Imperative Shell
"""Extraction quality test runner.

Orchestrates the full pipeline:
  1. Load source documents and parse annotations
  2. Generate (or load cached) PDFs across noise tiers
  3. Extract each PDF via Marker + cleanup pipeline
  4. Align extracted text to source annotations
  5. Score each aligned region (semantic + structural)
  6. Aggregate and write results JSON
  7. Compare against baseline for regression detection

Usage:
  runner = ExtractionQualityRunner(sources_dir, fixtures_dir, results_dir)
  report = runner.run()
  runner.write_results(report)
  regressions = runner.compare_to_baseline(report)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from local_library.ingestion.artifact_cleanup import clean_artifacts
from local_library.ingestion.markdown_cleanup import cleanup_markdown
from local_library.ingestion.pdf import PdfExtractor

from tests.extraction.synthetic.alignment import (
    align_regions,
)
from tests.extraction.synthetic.annotations import (
    AnnotatedRegion,
    parse_annotations,
)
from tests.extraction.synthetic.generate import NoiseTier, generate_all_tiers
from tests.extraction.synthetic.metrics import (
    character_error_rate,
    word_error_rate,
)
from tests.extraction.synthetic.validators import validate_region

logger = logging.getLogger(__name__)


@dataclass
class RegionScore:
    """Scores for a single aligned region."""

    region_id: str
    feature_type: str
    semantic: dict[str, float]  # {"CER": ..., "WER": ...}
    structural: dict[str, Any]  # {"detected": ..., ...details}
    similarity: float  # Alignment similarity
    coverage: float  # Alignment coverage

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "feature_type": self.feature_type,
            "semantic": self.semantic,
            "structural": self.structural,
            "similarity": self.similarity,
            "coverage": self.coverage,
        }


@dataclass
class TierResult:
    """Results for one document at one noise tier."""

    tier: str
    semantic_summary: dict[str, float]  # Averaged CER/WER
    structural_summary: dict[str, dict[str, Any]]  # Per feature type
    regions: list[dict[str, Any]]
    alignment_failures: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "semantic": self.semantic_summary,
            "structural": self.structural_summary,
            "regions": self.regions,
            "alignment_failures": self.alignment_failures,
        }


@dataclass
class DocumentResult:
    """Results for one source document across all tiers."""

    document_name: str
    tiers: dict[str, TierResult] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            t: r.to_dict() for t, r in self.tiers.items()
        }


@dataclass
class QualityReport:
    """Complete quality report across all documents and tiers."""

    run_id: str
    pipeline_version: str
    timestamp: str
    documents: dict[str, DocumentResult] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "pipeline_version": self.pipeline_version,
            "timestamp": self.timestamp,
            "results": {
                name: doc.to_dict() for name, doc in self.documents.items()
            },
        }


class ExtractionQualityRunner:
    """Orchestrates extraction quality benchmarking."""

    def __init__(
        self,
        sources_dir: Path,
        fixtures_dir: Path,
        results_dir: Path,
    ) -> None:
        self.sources_dir = sources_dir
        self.fixtures_dir = fixtures_dir
        self.results_dir = results_dir
        self._extractor: PdfExtractor | None = None

    @property
    def extractor(self) -> PdfExtractor:
        """Lazy-load PdfExtractor (models loaded on first extraction)."""
        if self._extractor is None:
            self._extractor = PdfExtractor(lazy_load=True)
        return self._extractor

    def run(self) -> QualityReport:
        """Run the full extraction quality benchmark.

        Returns:
            QualityReport with scores for all documents x tiers.
        """
        import subprocess

        git_sha = "unknown"
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            git_sha = result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        now = datetime.now(timezone.utc)
        report = QualityReport(
            run_id=now.strftime("%Y-%m-%dT%H:%M:%S"),
            pipeline_version=git_sha,
            timestamp=now.isoformat(),
        )

        source_files = sorted(self.sources_dir.glob("*.md"))
        if not source_files:
            logger.warning("No source documents found in %s", self.sources_dir)
            return report

        for source_md in source_files:
            doc_name = source_md.stem
            logger.info("Processing %s", doc_name)

            # Parse annotations
            text = source_md.read_text(encoding="utf-8")
            regions = parse_annotations(text)

            if not regions:
                logger.warning("No annotations found in %s", doc_name)
                continue

            # Generate PDFs (cached)
            fixture_dir = self.fixtures_dir / doc_name
            tier_pdfs = generate_all_tiers(source_md, fixture_dir)

            doc_result = DocumentResult(document_name=doc_name)

            for tier, pdf_path in tier_pdfs.items():
                tier_result = self._evaluate_tier(
                    regions, pdf_path, tier
                )
                doc_result.tiers[tier.value] = tier_result

            report.documents[doc_name] = doc_result

        return report

    def _evaluate_tier(
        self,
        regions: list[AnnotatedRegion],
        pdf_path: Path,
        tier: NoiseTier,
    ) -> TierResult:
        """Extract PDF, align regions, and score.

        Args:
            regions: Annotated regions from source document.
            pdf_path: Path to the tier's PDF.
            tier: Which noise tier this is.

        Returns:
            TierResult with per-region and summary scores.
        """
        # Extract
        try:
            extraction = self.extractor.extract(pdf_path)
            extracted_text = extraction.text
        except Exception:
            logger.error(
                "Extraction failed for %s tier %s", pdf_path, tier.value,
                exc_info=True,
            )
            return TierResult(
                tier=tier.value,
                semantic_summary={"CER": 1.0, "WER": 1.0},
                structural_summary={},
                regions=[],
                alignment_failures=[
                    {"region_id": r.region_id, "feature_type": r.feature_type,
                     "reason": "extraction failed"}
                    for r in regions
                ],
            )

        # Apply cleanup pipeline — must mirror library.py:add() ordering.
        # Order is load-bearing: artifacts first (removes content), then
        # markdown cleanup (applies formatting). If library.py changes
        # its cleanup pipeline, this must be updated to match.
        cleaned = clean_artifacts(extracted_text)
        cleaned = cleanup_markdown(cleaned)

        # Align
        alignment = align_regions(regions, cleaned)

        # Score each aligned region
        region_scores: list[RegionScore] = []
        for aligned in alignment.aligned:
            cer = character_error_rate(aligned.region.content, aligned.matched_text)
            wer = word_error_rate(aligned.region.content, aligned.matched_text)
            structural = validate_region(
                aligned.region.feature_type,
                aligned.region.content,
                aligned.matched_text,
            )
            region_scores.append(
                RegionScore(
                    region_id=aligned.region.region_id,
                    feature_type=aligned.region.feature_type,
                    semantic={"CER": round(cer, 4), "WER": round(wer, 4)},
                    structural={
                        "detected": structural.detected,
                        **structural.details,
                    },
                    similarity=round(aligned.similarity, 4),
                    coverage=round(aligned.coverage, 4),
                )
            )

        # Aggregate
        semantic_summary = _aggregate_semantic(region_scores)
        structural_summary = _aggregate_structural(region_scores)

        return TierResult(
            tier=tier.value,
            semantic_summary=semantic_summary,
            structural_summary=structural_summary,
            regions=[s.to_dict() for s in region_scores],
            alignment_failures=[
                {"region_id": f.region_id, "feature_type": f.feature_type,
                 "reason": f.reason}
                for f in alignment.failures
            ],
        )

    def write_results(self, report: QualityReport) -> Path:
        """Write results to timestamped JSON file.

        Args:
            report: Completed quality report.

        Returns:
            Path to the written results file.
        """
        self.results_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{report.run_id.replace(':', '-')}.json"
        output_path = self.results_dir / filename

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), indent=2, fp=f)

        return output_path

    def compare_to_baseline(
        self,
        report: QualityReport,
        threshold: float = 0.05,
    ) -> list[dict[str, Any]]:
        """Compare report against baseline and return regressions.

        Checks both semantic metrics (CER/WER increasing) and structural
        metrics (detection rates decreasing). A regression is any
        document x tier combination exceeding threshold (relative change).

        Args:
            report: Current run's quality report.
            threshold: Relative change threshold for flagging. Default 5%.

        Returns:
            List of regression dicts with details. Empty if no regressions
            or no baseline exists.
        """
        baseline_path = self.results_dir / "baseline.json"
        if not baseline_path.exists():
            logger.info("No baseline found at %s", baseline_path)
            return []

        with open(baseline_path, encoding="utf-8") as f:
            baseline_data = json.load(f)

        regressions: list[dict[str, Any]] = []
        baseline_results = baseline_data.get("results", {})
        current_results = report.to_dict().get("results", {})

        for doc_name, doc_tiers in current_results.items():
            baseline_doc = baseline_results.get(doc_name, {})
            for tier_name, tier_data in doc_tiers.items():
                baseline_tier = baseline_doc.get(tier_name, {})
                if not baseline_tier:
                    continue

                # Semantic regression: CER/WER increasing is bad
                baseline_sem = baseline_tier.get("semantic", {})
                current_sem = tier_data.get("semantic", {})

                for metric in ["CER", "WER"]:
                    base_val = baseline_sem.get(metric, 0.0)
                    curr_val = current_sem.get(metric, 0.0)

                    if base_val > 0 and curr_val > base_val:
                        relative_increase = (curr_val - base_val) / base_val
                        if relative_increase > threshold:
                            regressions.append({
                                "document": doc_name,
                                "tier": tier_name,
                                "metric": metric,
                                "baseline": round(base_val, 4),
                                "current": round(curr_val, 4),
                                "relative_increase": round(
                                    relative_increase, 4
                                ),
                            })

                # Structural regression: detection rate decreasing is bad
                baseline_struct = baseline_tier.get("structural", {})
                current_struct = tier_data.get("structural", {})

                for feature_type, base_data in baseline_struct.items():
                    curr_data = current_struct.get(feature_type, {})
                    base_rate = base_data.get("detection_rate", 0.0)
                    curr_rate = curr_data.get("detection_rate", 0.0)

                    if base_rate > 0 and curr_rate < base_rate:
                        relative_decrease = (base_rate - curr_rate) / base_rate
                        if relative_decrease > threshold:
                            regressions.append({
                                "document": doc_name,
                                "tier": tier_name,
                                "metric": "detection_rate",
                                "feature_type": feature_type,
                                "baseline": round(base_rate, 4),
                                "current": round(curr_rate, 4),
                                "relative_increase": round(
                                    relative_decrease, 4
                                ),
                            })

        return regressions


def _aggregate_semantic(scores: list[RegionScore]) -> dict[str, float]:
    """Average CER and WER across all scored regions."""
    if not scores:
        return {"CER": 0.0, "WER": 0.0}
    avg_cer = sum(s.semantic["CER"] for s in scores) / len(scores)
    avg_wer = sum(s.semantic["WER"] for s in scores) / len(scores)
    return {"CER": round(avg_cer, 4), "WER": round(avg_wer, 4)}


def _aggregate_structural(
    scores: list[RegionScore],
) -> dict[str, dict[str, Any]]:
    """Aggregate structural scores by feature type."""
    by_type: dict[str, list[RegionScore]] = {}
    for s in scores:
        prefix = s.feature_type.split("-")[0]
        by_type.setdefault(prefix, []).append(s)

    result: dict[str, dict[str, Any]] = {}
    for feature, type_scores in by_type.items():
        detected_count = sum(
            1 for s in type_scores if s.structural.get("detected") is True
        )
        total = len(type_scores)
        result[feature] = {
            "detection_rate": round(
                detected_count / total, 4
            ) if total > 0 else 0.0,
            "count": total,
        }
    return result
```

**Step 1: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_runner_logic.py -v`
Expected: All tests pass

**Step 2: Verify module imports resolve**

Run: `uv run python -c "from tests.extraction.synthetic.runner import ExtractionQualityRunner; print('OK')"`
Expected: Prints "OK"

**Step 3: Commit**

```bash
git add tests/extraction/synthetic/runner.py tests/unit/test_runner_logic.py
git commit -m "feat: add extraction quality test runner with aggregation and regression detection"
```

<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

---

<!-- START_TASK_3 -->
### Task 3: Implement Rich reporting output

**Files:**
- Create: `tests/extraction/synthetic/reporting.py`

**Step 1: Implement the module**

```python
# pattern: Imperative Shell
"""Rich-formatted reporting for extraction quality results.

Provides human-readable summary output: green/yellow/red dashboard
per feature type and noise tier, regression flagging.
"""
from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table


def print_summary(
    report_data: dict[str, Any], console: Console | None = None
) -> None:
    """Print a human-readable quality summary.

    Args:
        report_data: Output of QualityReport.to_dict().
        console: Rich console to print to. Uses default if None.
    """
    con = console or Console()
    results = report_data.get("results", {})

    con.print(
        f"\n[bold]Extraction Quality Report[/bold]  "
        f"[dim]{report_data.get('timestamp', 'unknown')}  "
        f"pipeline: {report_data.get('pipeline_version', 'unknown')}[/dim]\n"
    )

    for doc_name, doc_tiers in results.items():
        table = Table(title=doc_name, show_header=True, header_style="bold")
        table.add_column("Tier", style="bold")
        table.add_column("CER", justify="right")
        table.add_column("WER", justify="right")
        table.add_column("Failures", justify="right")
        table.add_column("Detection", justify="right")

        for tier_name in [
            "T0_clean", "T1_ocr_needed", "T2_moderate_scan", "T3_degraded"
        ]:
            tier_data = doc_tiers.get(tier_name, {})
            if not tier_data:
                continue

            semantic = tier_data.get("semantic", {})
            cer = semantic.get("CER", 0.0)
            wer = semantic.get("WER", 0.0)
            failures = len(tier_data.get("alignment_failures", []))
            structural = tier_data.get("structural", {})

            # Compute overall detection rate
            total_detected = sum(
                v.get("detection_rate", 0.0) * v.get("count", 0)
                for v in structural.values()
            )
            total_count = sum(v.get("count", 0) for v in structural.values())
            detection_rate = (
                total_detected / total_count if total_count > 0 else 0.0
            )

            # Color coding
            cer_str = _color_metric(cer, good=0.05, warn=0.15)
            wer_str = _color_metric(wer, good=0.10, warn=0.25)
            fail_str = (
                f"[green]{failures}[/green]"
                if failures == 0
                else f"[red]{failures}[/red]"
            )
            # Color detection rate: low detection is bad (invert for threshold)
            det_str = _color_metric(
                1.0 - detection_rate, good=0.05, warn=0.20
            ).replace(f"{1.0 - detection_rate:.4f}", f"{detection_rate:.1%}")

            table.add_row(tier_name, cer_str, wer_str, fail_str, det_str)

        con.print(table)
        con.print()


def print_regressions(
    regressions: list[dict[str, Any]], console: Console | None = None
) -> None:
    """Print regression summary.

    Args:
        regressions: List from compare_to_baseline().
        console: Rich console to print to.
    """
    con = console or Console()

    if not regressions:
        con.print("[green]No regressions detected.[/green]\n")
        return

    con.print(
        f"[red bold]Regressions detected: {len(regressions)}[/red bold]\n"
    )

    table = Table(show_header=True, header_style="bold red")
    table.add_column("Document")
    table.add_column("Tier")
    table.add_column("Metric")
    table.add_column("Baseline", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("Change", justify="right")

    for r in regressions:
        change = r["relative_increase"]
        table.add_row(
            r["document"],
            r["tier"],
            r["metric"],
            f"{r['baseline']:.4f}",
            f"{r['current']:.4f}",
            f"[red]+{change:.1%}[/red]",
        )

    con.print(table)
    con.print()


def _color_metric(value: float, good: float, warn: float) -> str:
    """Color a metric value: green if <= good, yellow if <= warn, red."""
    formatted = f"{value:.4f}"
    if value <= good:
        return f"[green]{formatted}[/green]"
    elif value <= warn:
        return f"[yellow]{formatted}[/yellow]"
    else:
        return f"[red]{formatted}[/red]"
```

**Step 1: Verify imports**

Run: `uv run python -c "from tests.extraction.synthetic.reporting import print_summary; print('OK')"`
Expected: Prints "OK"

**Step 2: Commit**

```bash
git add tests/extraction/synthetic/reporting.py
git commit -m "feat: add Rich reporting for extraction quality results"
```

<!-- END_TASK_3 -->

---

<!-- START_TASK_4 -->
### Task 4: Add pytest integration and smoke test

**Files:**
- Modify: `tests/extraction/synthetic/conftest.py` (add session fixtures)
- Create: `tests/extraction/synthetic/test_smoke.py`

**Step 1: Update conftest.py with session fixtures**

Append to the existing `tests/extraction/synthetic/conftest.py` (which already has `pytest_addoption` and `pytest_collection_modifyitems` from Phase 1):

```python
# Append to existing tests/extraction/synthetic/conftest.py

from pathlib import Path

SYNTHETIC_DIR = Path(__file__).parent
SOURCES_DIR = SYNTHETIC_DIR / "sources"
FIXTURES_DIR = SYNTHETIC_DIR / "fixtures"
RESULTS_DIR = SYNTHETIC_DIR / "results"


@pytest.fixture(scope="session")
def quality_runner():
    """Session-scoped extraction quality runner."""
    from tests.extraction.synthetic.runner import ExtractionQualityRunner

    return ExtractionQualityRunner(
        sources_dir=SOURCES_DIR,
        fixtures_dir=FIXTURES_DIR,
        results_dir=RESULTS_DIR,
    )


@pytest.fixture(scope="session")
def quality_report(quality_runner):
    """Session-scoped quality report (runs full benchmark once)."""
    return quality_runner.run()
```

**Step 2: Create smoke test**

```python
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
```

**Step 3: Verify tests are skipped by default**

Run: `uv run pytest tests/extraction/synthetic/ -v`
Expected: Tests skipped with "need --run-extraction-quality option to run"

**Step 4: Commit**

```bash
git add tests/extraction/synthetic/conftest.py tests/extraction/synthetic/test_smoke.py
git commit -m "feat: add pytest integration and smoke test for extraction quality"
```

<!-- END_TASK_4 -->
