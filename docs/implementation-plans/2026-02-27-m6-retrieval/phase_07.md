## Phase 7: Evaluation Framework

**Goal:** Provide measurement infrastructure for retrieval quality.

**Components:**
- `tests/eval/retrieval_eval.py` — metric functions (Precision@k, Recall@k, MRR), dataclasses, evaluation orchestration, CLI entry point
- `tests/eval/test_retrieval_metrics.py` — unit tests for metric computation
- `tests/eval/test_queries.json` — seed query set (~12 queries across categories)

**Dependencies:** Phase 5 (Library integration — `get_retriever()` factory method)

**Design note:** The labeled test query set is a stub with ~10-15 seed queries against the golden corpus. Populating it to the full 50-75 queries is a manual annotation effort that follows implementation. The framework enables measurement; it doesn't manufacture the ground truth.

<!-- START_TASK_1 -->
### Task 1: Create metric computation functions (Functional Core)

**Files:**
- Create: `tests/eval/retrieval_eval.py`

**Context files for the executor:**
- Read `RAG_background/v1_backport_content.md` lines 58-94 for starter metric formulas
- Read `src/local_library/embeddings/base.py` for SearchResult dataclass
- Read `tests/extraction/conftest.py` lines 431-550 for existing evaluation pattern (GroundTruth, DocumentResult, AccuracyReport)

**Step 1: Create the eval directory**

```bash
mkdir -p tests/eval
touch tests/eval/__init__.py
```

**Step 2: Create retrieval_eval.py**

Create `tests/eval/retrieval_eval.py`:

```python
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
```

**Step 3: Verify syntax**

Run: `uv run python -c "from tests.eval.retrieval_eval import precision_at_k, recall_at_k, mean_reciprocal_rank; print('OK')"`
Expected: Import succeeds

**Step 4: Commit**

```bash
git add tests/eval/__init__.py tests/eval/retrieval_eval.py
git commit -m "feat(eval): add retrieval evaluation framework with IR metrics"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Write unit tests for metric computation functions

**Files:**
- Create: `tests/eval/test_retrieval_metrics.py`

**Step 1: Create the test file**

Create `tests/eval/test_retrieval_metrics.py`:

```python
"""Tests for retrieval evaluation metric computation."""

# pattern: Functional Core

import pytest

from tests.eval.retrieval_eval import (
    EvalReport,
    QueryResult,
    evaluate_query,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
)


class TestPrecisionAtK:
    """Tests for precision_at_k."""

    def test_all_relevant(self) -> None:
        """All top-k results are relevant."""
        retrieved = ["a", "b", "c"]
        relevant = {"a", "b", "c"}
        assert precision_at_k(retrieved, relevant, 3) == 1.0

    def test_none_relevant(self) -> None:
        """No top-k results are relevant."""
        retrieved = ["x", "y", "z"]
        relevant = {"a", "b", "c"}
        assert precision_at_k(retrieved, relevant, 3) == 0.0

    def test_partial_relevant(self) -> None:
        """Some top-k results are relevant."""
        retrieved = ["a", "x", "b", "y", "c"]
        relevant = {"a", "b", "c"}
        assert precision_at_k(retrieved, relevant, 5) == pytest.approx(3 / 5)

    def test_k_larger_than_results(self) -> None:
        """k exceeds number of retrieved results."""
        retrieved = ["a", "b"]
        relevant = {"a", "b"}
        # Only 2 results for k=5: 2/5 = 0.4
        assert precision_at_k(retrieved, relevant, 5) == pytest.approx(2 / 5)

    def test_k_zero(self) -> None:
        """k=0 returns 0."""
        assert precision_at_k(["a"], {"a"}, 0) == 0.0

    def test_empty_retrieved(self) -> None:
        """Empty retrieved list."""
        assert precision_at_k([], {"a"}, 5) == 0.0


class TestRecallAtK:
    """Tests for recall_at_k."""

    def test_all_found(self) -> None:
        """All relevant documents found in top-k."""
        retrieved = ["a", "b", "c", "x"]
        relevant = {"a", "b", "c"}
        assert recall_at_k(retrieved, relevant, 10) == 1.0

    def test_none_found(self) -> None:
        """No relevant documents in top-k."""
        retrieved = ["x", "y", "z"]
        relevant = {"a", "b"}
        assert recall_at_k(retrieved, relevant, 3) == 0.0

    def test_partial_found(self) -> None:
        """Some relevant documents found."""
        retrieved = ["a", "x", "y"]
        relevant = {"a", "b", "c"}
        assert recall_at_k(retrieved, relevant, 3) == pytest.approx(1 / 3)

    def test_empty_relevant(self) -> None:
        """No relevant documents exist."""
        assert recall_at_k(["a"], set(), 5) == 0.0

    def test_empty_retrieved(self) -> None:
        """Empty retrieved list."""
        assert recall_at_k([], {"a"}, 5) == 0.0


class TestMeanReciprocalRank:
    """Tests for mean_reciprocal_rank."""

    def test_first_result_relevant(self) -> None:
        """First result is relevant: MRR = 1.0."""
        assert mean_reciprocal_rank(["a", "b", "c"], {"a"}) == 1.0

    def test_second_result_relevant(self) -> None:
        """Second result is relevant: MRR = 0.5."""
        assert mean_reciprocal_rank(["x", "a", "b"], {"a"}) == 0.5

    def test_third_result_relevant(self) -> None:
        """Third result is relevant: MRR = 1/3."""
        assert mean_reciprocal_rank(["x", "y", "a"], {"a"}) == pytest.approx(1 / 3)

    def test_no_relevant_found(self) -> None:
        """No relevant result in list: MRR = 0."""
        assert mean_reciprocal_rank(["x", "y", "z"], {"a"}) == 0.0

    def test_empty_retrieved(self) -> None:
        """Empty retrieved list."""
        assert mean_reciprocal_rank([], {"a"}) == 0.0

    def test_multiple_relevant_takes_first(self) -> None:
        """MRR uses the first relevant result only."""
        assert mean_reciprocal_rank(["x", "a", "b"], {"a", "b"}) == 0.5


class TestEvaluateQuery:
    """Tests for evaluate_query."""

    def test_computes_all_metrics(self) -> None:
        """evaluate_query returns QueryResult with all metrics."""
        query = {
            "id": "q1",
            "text": "test query",
            "category": "factual",
            "relevant_docs": ["a", "b"],
        }
        retrieved = ["a", "x", "b", "y", "z"]

        result = evaluate_query(query, retrieved)

        assert isinstance(result, QueryResult)
        assert result.query_id == "q1"
        assert result.category == "factual"
        assert result.precision_at_5 == pytest.approx(2 / 5)
        assert result.recall_at_10 == 1.0  # Both found in top 5
        assert result.mrr == 1.0  # First result is relevant


class TestEvalReport:
    """Tests for EvalReport aggregate metrics."""

    def test_empty_report(self) -> None:
        """Empty report returns 0 for all metrics."""
        report = EvalReport()
        assert report.mean_precision_at_5 == 0.0
        assert report.mean_recall_at_10 == 0.0
        assert report.mean_mrr == 0.0

    def test_aggregate_metrics(self) -> None:
        """Report computes correct averages across queries."""
        report = EvalReport()
        report.add(QueryResult(
            query_id="q1", query_text="q1", category="factual",
            precision_at_5=0.8, precision_at_10=0.6, recall_at_10=1.0,
            mrr=1.0, retrieved_docs=[], relevant_docs=[],
        ))
        report.add(QueryResult(
            query_id="q2", query_text="q2", category="factual",
            precision_at_5=0.4, precision_at_10=0.3, recall_at_10=0.5,
            mrr=0.5, retrieved_docs=[], relevant_docs=[],
        ))

        assert report.mean_precision_at_5 == pytest.approx(0.6)
        assert report.mean_mrr == pytest.approx(0.75)

    def test_results_by_category(self) -> None:
        """Report groups results by category."""
        report = EvalReport()
        report.add(QueryResult(
            query_id="q1", query_text="q1", category="factual",
            precision_at_5=0.8, precision_at_10=0.6, recall_at_10=1.0,
            mrr=1.0, retrieved_docs=[], relevant_docs=[],
        ))
        report.add(QueryResult(
            query_id="q2", query_text="q2", category="conceptual",
            precision_at_5=0.4, precision_at_10=0.3, recall_at_10=0.5,
            mrr=0.5, retrieved_docs=[], relevant_docs=[],
        ))

        by_cat = report.results_by_category()
        assert "factual" in by_cat
        assert "conceptual" in by_cat
        assert len(by_cat["factual"]) == 1

    def test_format_summary(self) -> None:
        """format_summary produces human-readable output."""
        report = EvalReport()
        report.add(QueryResult(
            query_id="q1", query_text="q1", category="factual",
            precision_at_5=0.8, precision_at_10=0.6, recall_at_10=1.0,
            mrr=1.0, retrieved_docs=[], relevant_docs=[],
        ))

        summary = report.format_summary()
        assert "Precision@5" in summary
        assert "Recall@10" in summary
        assert "MRR" in summary

    def test_to_dict(self) -> None:
        """to_dict produces JSON-serializable output."""
        report = EvalReport()
        report.add(QueryResult(
            query_id="q1", query_text="q1", category="factual",
            precision_at_5=0.8, precision_at_10=0.6, recall_at_10=1.0,
            mrr=1.0, retrieved_docs=[], relevant_docs=[],
        ))

        d = report.to_dict()
        assert "total_queries" in d
        assert d["total_queries"] == 1
        assert "mean_precision_at_5" in d
        assert "by_category" in d
```

**Step 2: Run tests**

Run: `uv run pytest tests/eval/test_retrieval_metrics.py -v --tb=short`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/eval/test_retrieval_metrics.py
git commit -m "test(eval): add unit tests for retrieval metric computation"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create seed test query set

**Files:**
- Create: `tests/eval/test_queries.json`

**Context:** This is a seed query set with ~10-15 example queries across categories. These are written against the golden test corpus (20 academic PDFs). The queries and relevance labels are best-effort starting points — they should be validated and expanded through manual annotation after the framework is operational.

**Step 1: Create test_queries.json**

Create `tests/eval/test_queries.json`:

```json
{
  "description": "Labeled test queries for retrieval evaluation. Relevance is at the document level (citekeys). Expand this set through manual annotation after running retrieval and labeling results.",
  "queries": [
    {
      "id": "factual_001",
      "text": "What is the role of social identity in intergroup behavior?",
      "category": "factual",
      "relevant_docs": ["Tajfel1979"],
      "unanswerable": false
    },
    {
      "id": "factual_002",
      "text": "What is the phenomenological concept of the lifeworld?",
      "category": "factual",
      "relevant_docs": ["Schutz1944"],
      "unanswerable": false
    },
    {
      "id": "factual_003",
      "text": "What are the NIST guidelines for digital evidence?",
      "category": "factual",
      "relevant_docs": ["NIST2023"],
      "unanswerable": false
    },
    {
      "id": "conceptual_001",
      "text": "How does actor-network theory describe the relationship between human and non-human actors?",
      "category": "conceptual",
      "relevant_docs": ["Callon1998"],
      "unanswerable": false
    },
    {
      "id": "conceptual_002",
      "text": "What is the relationship between culture and social structure?",
      "category": "conceptual",
      "relevant_docs": ["Sewell1996a"],
      "unanswerable": false
    },
    {
      "id": "conceptual_003",
      "text": "How does commodity fetishism obscure social relations?",
      "category": "conceptual",
      "relevant_docs": ["Marx1968"],
      "unanswerable": false
    },
    {
      "id": "methodology_001",
      "text": "How are legal texts processed with natural language processing?",
      "category": "methodology",
      "relevant_docs": ["Chalkidis2020"],
      "unanswerable": false
    },
    {
      "id": "methodology_002",
      "text": "What methods are used for information retrieval evaluation?",
      "category": "methodology",
      "relevant_docs": ["Melucci1995"],
      "unanswerable": false
    },
    {
      "id": "comparative_001",
      "text": "How do embodied cognition theories differ from traditional cognitive models?",
      "category": "comparative",
      "relevant_docs": ["Wilson-Mendenhall2018"],
      "unanswerable": false
    },
    {
      "id": "comparative_002",
      "text": "What is the difference between commons-based peer production and traditional economic models?",
      "category": "comparative",
      "relevant_docs": ["CBPP2015"],
      "unanswerable": false
    },
    {
      "id": "adversarial_001",
      "text": "What is the current stock price of Apple?",
      "category": "adversarial",
      "relevant_docs": [],
      "unanswerable": true
    },
    {
      "id": "adversarial_002",
      "text": "How do quantum computers solve the traveling salesman problem?",
      "category": "adversarial",
      "relevant_docs": [],
      "unanswerable": true
    }
  ]
}
```

**Step 2: Verify JSON is valid**

Run: `uv run python -c "import json; d = json.load(open('tests/eval/test_queries.json')); print(f'{len(d[\"queries\"])} queries loaded')"`
Expected: `12 queries loaded`

**Step 3: Commit**

```bash
git add tests/eval/test_queries.json
git commit -m "feat(eval): add seed test query set for retrieval evaluation"
```
<!-- END_TASK_3 -->
