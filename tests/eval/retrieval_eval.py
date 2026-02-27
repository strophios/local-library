"""Retrieval evaluation framework.

Computes standard IR metrics (Precision@k, Recall@k, MRR) against a labeled
test query set. Designed as a standalone script that can be run against any
database with embedded documents.

Usage:
    uv run python tests/eval/retrieval_eval.py --db-path <path> [--mode hybrid|vector|fts]
"""

# pattern: Functional Core (metric computation) + Imperative Shell (script orchestration)

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ── Functional Core: Metric computation ──────────────────────────


@dataclass(frozen=True)
class QueryResult:
    """Evaluation result for a single query."""

    query_id: str
    query_text: str
    category: str
    precision_at_5: float
    precision_at_10: float
    recall_at_10: float
    mrr: float
    retrieved_docs: list[str]
    relevant_docs: list[str]


def precision_at_k(retrieved_doc_ids: list[str], relevant_doc_ids: set[str], k: int) -> float:
    """Compute Precision@k: fraction of top-k results that are relevant.

    Args:
        retrieved_doc_ids: Ordered list of retrieved document identifiers (citekeys)
        relevant_doc_ids: Set of relevant document identifiers
        k: Number of top results to consider

    Returns:
        Precision score in [0, 1]
    """
    if k == 0:
        return 0.0
    top_k = retrieved_doc_ids[:k]
    relevant_in_top_k = sum(1 for doc in top_k if doc in relevant_doc_ids)
    return relevant_in_top_k / k


def recall_at_k(retrieved_doc_ids: list[str], relevant_doc_ids: set[str], k: int) -> float:
    """Compute Recall@k: fraction of relevant documents found in top-k results.

    Args:
        retrieved_doc_ids: Ordered list of retrieved document identifiers (citekeys)
        relevant_doc_ids: Set of relevant document identifiers
        k: Number of top results to consider

    Returns:
        Recall score in [0, 1]. Returns 0.0 if no relevant documents exist.
    """
    if not relevant_doc_ids:
        return 0.0
    top_k = retrieved_doc_ids[:k]
    found = sum(1 for doc in top_k if doc in relevant_doc_ids)
    return found / len(relevant_doc_ids)


def mean_reciprocal_rank(retrieved_doc_ids: list[str], relevant_doc_ids: set[str]) -> float:
    """Compute MRR: reciprocal of the rank of the first relevant result.

    Args:
        retrieved_doc_ids: Ordered list of retrieved document identifiers (citekeys)
        relevant_doc_ids: Set of relevant document identifiers

    Returns:
        MRR score in (0, 1]. Returns 0.0 if no relevant result found.
    """
    for rank, doc_id in enumerate(retrieved_doc_ids, start=1):
        if doc_id in relevant_doc_ids:
            return 1.0 / rank
    return 0.0


def evaluate_query(
    query: dict[str, Any],
    retrieved_citekeys: list[str],
) -> QueryResult:
    """Evaluate a single query against its labeled relevance judgments.

    Args:
        query: Query dict with keys: id, text, category, relevant_docs
        retrieved_citekeys: Ordered list of citekeys from search results

    Returns:
        QueryResult with computed metrics
    """
    relevant = set(query["relevant_docs"])
    return QueryResult(
        query_id=query["id"],
        query_text=query["text"],
        category=query["category"],
        precision_at_5=precision_at_k(retrieved_citekeys, relevant, 5),
        precision_at_10=precision_at_k(retrieved_citekeys, relevant, 10),
        recall_at_10=recall_at_k(retrieved_citekeys, relevant, 10),
        mrr=mean_reciprocal_rank(retrieved_citekeys, relevant),
        retrieved_docs=retrieved_citekeys[:10],
        relevant_docs=query["relevant_docs"],
    )


@dataclass
class EvalReport:
    """Aggregate evaluation report across all queries."""

    results: list[QueryResult] = field(default_factory=list)

    def add(self, result: QueryResult) -> None:
        """Add a query result to the report."""
        self.results.append(result)

    @property
    def mean_precision_at_5(self) -> float:
        """Mean Precision@5 across all queries."""
        if not self.results:
            return 0.0
        return sum(r.precision_at_5 for r in self.results) / len(self.results)

    @property
    def mean_precision_at_10(self) -> float:
        """Mean Precision@10 across all queries."""
        if not self.results:
            return 0.0
        return sum(r.precision_at_10 for r in self.results) / len(self.results)

    @property
    def mean_recall_at_10(self) -> float:
        """Mean Recall@10 across all queries."""
        if not self.results:
            return 0.0
        return sum(r.recall_at_10 for r in self.results) / len(self.results)

    @property
    def mean_mrr(self) -> float:
        """Mean Reciprocal Rank across all queries."""
        if not self.results:
            return 0.0
        return sum(r.mrr for r in self.results) / len(self.results)

    def results_by_category(self) -> dict[str, list[QueryResult]]:
        """Group results by query category."""
        by_cat: dict[str, list[QueryResult]] = {}
        for r in self.results:
            by_cat.setdefault(r.category, []).append(r)
        return by_cat

    def format_summary(self) -> str:
        """Format a human-readable summary of evaluation metrics."""
        lines = [
            f"Retrieval Evaluation ({len(self.results)} queries)",
            "=" * 50,
            f"  Precision@5:  {self.mean_precision_at_5:.3f}",
            f"  Precision@10: {self.mean_precision_at_10:.3f}",
            f"  Recall@10:    {self.mean_recall_at_10:.3f}",
            f"  MRR:          {self.mean_mrr:.3f}",
            "",
            "By category:",
        ]

        for cat, results in sorted(self.results_by_category().items()):
            n = len(results)
            p5 = sum(r.precision_at_5 for r in results) / n
            r10 = sum(r.recall_at_10 for r in results) / n
            mrr = sum(r.mrr for r in results) / n
            lines.append(f"  {cat} ({n} queries): P@5={p5:.3f}  R@10={r10:.3f}  MRR={mrr:.3f}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Export report as a dict for JSON serialization."""
        return {
            "total_queries": len(self.results),
            "mean_precision_at_5": round(self.mean_precision_at_5, 4),
            "mean_precision_at_10": round(self.mean_precision_at_10, 4),
            "mean_recall_at_10": round(self.mean_recall_at_10, 4),
            "mean_mrr": round(self.mean_mrr, 4),
            "by_category": {
                cat: {
                    "count": len(results),
                    "precision_at_5": round(
                        sum(r.precision_at_5 for r in results) / len(results), 4
                    ),
                    "recall_at_10": round(
                        sum(r.recall_at_10 for r in results) / len(results), 4
                    ),
                    "mrr": round(sum(r.mrr for r in results) / len(results), 4),
                }
                for cat, results in sorted(self.results_by_category().items())
            },
        }


# ── Imperative Shell: Script orchestration ───────────────────────


def load_test_queries(path: Path) -> list[dict[str, Any]]:
    """Load labeled test queries from JSON file.

    Args:
        path: Path to test_queries.json

    Returns:
        List of query dicts with keys: id, text, category, relevant_docs
    """
    with open(path) as f:
        data = json.load(f)
    return data["queries"]


def run_evaluation(
    db_path: Path,
    queries_path: Path,
    mode: str = "hybrid",
    json_output: bool = False,
) -> EvalReport:
    """Run retrieval evaluation against labeled query set.

    Args:
        db_path: Path to SQLite database with embedded documents
        queries_path: Path to test_queries.json
        mode: Retriever mode (hybrid, vector, fts)
        json_output: Output as JSON instead of table

    Returns:
        EvalReport with metrics for all queries
    """
    from local_library.core import Library

    queries = load_test_queries(queries_path)
    report = EvalReport()

    with Library(db_path=db_path, embed_on_add=False) as lib:
        retriever = lib.get_retriever(mode=mode)

        for query in queries:
            if query.get("unanswerable", False):
                continue  # Skip adversarial queries for retrieval metrics

            results = retriever.retrieve(query["text"], k=10)

            # Map chunk-level results to document-level citekeys.
            # Metrics are computed at document granularity: multiple chunks
            # from the same document count as one relevant result. This is
            # practical for a ~20-document golden set and avoids the need
            # for chunk-level relevance annotations.
            retrieved_citekeys = []
            for r in results:
                citekey = r.doc_citekey
                if citekey and citekey not in retrieved_citekeys:
                    retrieved_citekeys.append(citekey)

            qr = evaluate_query(query, retrieved_citekeys)
            report.add(qr)

    return report


def run_comparative_evaluation(
    db_path: Path,
    queries_path: Path,
    json_output: bool = False,
) -> dict[str, EvalReport]:
    """Run evaluation for all three retriever modes and compare.

    Args:
        db_path: Path to SQLite database with embedded documents
        queries_path: Path to test_queries.json
        json_output: Output as JSON

    Returns:
        Dict mapping mode name to EvalReport
    """
    reports = {}
    for mode in ("vector", "fts", "hybrid"):
        reports[mode] = run_evaluation(db_path, queries_path, mode=mode)
    return reports


def main() -> None:
    """CLI entry point for evaluation script."""
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality")
    parser.add_argument("--db-path", type=Path, required=True, help="Path to SQLite database")
    parser.add_argument(
        "--queries",
        type=Path,
        default=Path(__file__).parent / "test_queries.json",
        help="Path to test queries JSON",
    )
    parser.add_argument("--mode", default="all", help="Retriever mode (hybrid, vector, fts, or all)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if not args.db_path.exists():
        print(f"error: database not found: {args.db_path}", file=sys.stderr)
        sys.exit(1)

    if not args.queries.exists():
        print(f"error: query file not found: {args.queries}", file=sys.stderr)
        sys.exit(1)

    if args.mode == "all":
        reports = run_comparative_evaluation(args.db_path, args.queries)
        if args.json:
            output = {mode: report.to_dict() for mode, report in reports.items()}
            print(json.dumps(output, indent=2))
        else:
            for mode, report in reports.items():
                print(f"\n{'─' * 50}")
                print(f"Mode: {mode}")
                print(report.format_summary())
    else:
        report = run_evaluation(args.db_path, args.queries, mode=args.mode)
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print(report.format_summary())


if __name__ == "__main__":
    main()
