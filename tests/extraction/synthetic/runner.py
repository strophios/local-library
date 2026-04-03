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
import time
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
    strip_annotations,
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
    document_semantic: dict[str, float]  # Whole-doc CER/WER (alignment-independent)
    regions: list[dict[str, Any]]
    alignment_failures: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "semantic": self.semantic_summary,
            "document_semantic": self.document_semantic,
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
        return {t: r.to_dict() for t, r in self.tiers.items()}


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
            "results": {name: doc.to_dict() for name, doc in self.documents.items()},
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

    def run(
        self,
        tiers: list[NoiseTier] | None = None,
    ) -> QualityReport:
        """Run the full extraction quality benchmark.

        Args:
            tiers: Noise tiers to evaluate. None means all tiers.

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

        source_files = sorted(f for f in self.sources_dir.glob("*.md") if f.name != "COVERAGE.md")
        if not source_files:
            logger.warning("No source documents found in %s", self.sources_dir)
            return report

        active_tiers = tiers or list(NoiseTier)
        total_docs = len(source_files)
        total_evals = total_docs * len(active_tiers)
        completed_evals = 0
        run_start = time.monotonic()

        for doc_idx, source_md in enumerate(source_files, 1):
            doc_name = source_md.stem
            doc_start = time.monotonic()
            logger.info("[%d/%d] Processing %s", doc_idx, total_docs, doc_name)

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

            source_text = strip_annotations(text)

            for tier, pdf_path in tier_pdfs.items():
                if tier not in active_tiers:
                    continue
                tier_start = time.monotonic()
                tier_result = self._evaluate_tier(regions, source_text, pdf_path, tier)
                tier_elapsed = time.monotonic() - tier_start
                completed_evals += 1
                logger.info(
                    "  [%d/%d] %s %s — %.1fs",
                    completed_evals,
                    total_evals,
                    doc_name,
                    tier.value,
                    tier_elapsed,
                )
                doc_result.tiers[tier.value] = tier_result

            doc_elapsed = time.monotonic() - doc_start
            logger.info("  %s complete — %.1fs", doc_name, doc_elapsed)
            report.documents[doc_name] = doc_result

        total_elapsed = time.monotonic() - run_start
        logger.info(
            "Benchmark complete: %d docs, %d tiers in %.1fs",
            total_docs,
            completed_evals,
            total_elapsed,
        )
        return report

    def _evaluate_tier(
        self,
        regions: list[AnnotatedRegion],
        source_text: str,
        pdf_path: Path,
        tier: NoiseTier,
    ) -> TierResult:
        """Extract PDF, align regions, and score.

        Args:
            regions: Annotated regions from source document.
            source_text: Full source markdown with annotations stripped.
            pdf_path: Path to the tier's PDF.
            tier: Which noise tier this is.

        Returns:
            TierResult with per-region and summary scores.
        """
        # Extract
        try:
            extract_start = time.monotonic()
            extraction = self.extractor.extract(pdf_path)
            extract_elapsed = time.monotonic() - extract_start
            extracted_text = extraction.text
            logger.info(
                "    Extraction: %.1fs (%d chars)",
                extract_elapsed,
                len(extracted_text),
            )

            # Save extracted markdown for diagnostic visibility
            output_dir = self.results_dir / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            doc_name = pdf_path.parent.name
            output_path = output_dir / f"{doc_name}_{tier.value}.md"
            output_path.write_text(extracted_text, encoding="utf-8")
        except Exception:
            logger.error(
                "Extraction failed for %s tier %s",
                pdf_path,
                tier.value,
                exc_info=True,
            )
            return TierResult(
                tier=tier.value,
                semantic_summary={"CER": 1.0, "WER": 1.0},
                document_semantic={"CER": 1.0, "WER": 1.0},
                structural_summary={},
                regions=[],
                alignment_failures=[
                    {
                        "region_id": r.region_id,
                        "feature_type": r.feature_type,
                        "reason": "extraction failed",
                    }
                    for r in regions
                ],
            )

        # Apply cleanup pipeline — must mirror library.py:add() ordering.
        # Order is load-bearing: artifacts first (removes content), then
        # markdown cleanup (applies formatting). If library.py changes
        # its cleanup pipeline, this must be updated to match.
        cleaned = clean_artifacts(extracted_text)
        cleaned = cleanup_markdown(cleaned)

        # Document-level semantic metrics (alignment-independent).
        # Compares full normalized source against full normalized extraction
        # so we have a quality signal even when region alignment fails.
        doc_cer = character_error_rate(source_text, cleaned)
        doc_wer = word_error_rate(source_text, cleaned)
        document_semantic = {"CER": round(doc_cer, 4), "WER": round(doc_wer, 4)}

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
            document_semantic=document_semantic,
            structural_summary=structural_summary,
            regions=[s.to_dict() for s in region_scores],
            alignment_failures=[
                {"region_id": f.region_id, "feature_type": f.feature_type, "reason": f.reason}
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
            json.dump(report.to_dict(), f, indent=2)

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

                    # Skip zero baselines: relative change is undefined
                    if base_val > 0 and curr_val > base_val:
                        relative_increase = (curr_val - base_val) / base_val
                        if relative_increase > threshold:
                            regressions.append(
                                {
                                    "document": doc_name,
                                    "tier": tier_name,
                                    "metric": metric,
                                    "baseline": round(base_val, 4),
                                    "current": round(curr_val, 4),
                                    "relative_increase": round(relative_increase, 4),
                                }
                            )

                # Structural regression: detection rate decreasing is bad
                baseline_struct = baseline_tier.get("structural", {})
                current_struct = tier_data.get("structural", {})

                for feature_type, base_data in baseline_struct.items():
                    curr_data = current_struct.get(feature_type, {})
                    base_rate = base_data.get("detection_rate", 0.0)
                    curr_rate = curr_data.get("detection_rate", 0.0)

                    # Skip zero baselines: relative change is undefined
                    if base_rate > 0 and curr_rate < base_rate:
                        relative_decrease = (base_rate - curr_rate) / base_rate
                        if relative_decrease > threshold:
                            regressions.append(
                                {
                                    "document": doc_name,
                                    "tier": tier_name,
                                    "metric": "detection_rate",
                                    "feature_type": feature_type,
                                    "baseline": round(base_rate, 4),
                                    "current": round(curr_rate, 4),
                                    "relative_increase": round(relative_decrease, 4),
                                }
                            )

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
        detected_count = sum(1 for s in type_scores if s.structural.get("detected") is True)
        total = len(type_scores)
        result[feature] = {
            "detection_rate": round(detected_count / total, 4) if total > 0 else 0.0,
            "count": total,
        }
    return result
