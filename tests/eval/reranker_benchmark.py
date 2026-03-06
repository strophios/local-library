"""Benchmark cross-encoder reranker models for latency and load time.

Usage:
    uv run python tests/eval/reranker_benchmark.py [--k 10] [--output results.json]

Compares three cross-encoder models plus a no-reranking baseline:
- cross-encoder/ms-marco-MiniLM-L-6-v2
- cross-encoder/ms-marco-MiniLM-L-12-v2
- BAAI/bge-reranker-v2-m3
- baseline (vector retriever, no reranking)

Primary measurements: model load time and per-query latency.
Quality metrics (NDCG@10, MRR) are reported as informational only — the
current test query set (12 seed queries) is too small for reliable quality
comparison. Re-run after expanding to 50-100 validated queries.
"""

# pattern: Imperative Shell

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from retrieval_eval import mean_reciprocal_rank, ndcg_at_k

from local_library.core.library import Library
from local_library.embeddings.base import SearchResult

MODELS = [
    "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "cross-encoder/ms-marco-MiniLM-L-12-v2",
    "BAAI/bge-reranker-v2-m3",
]

QUERY_FILE = Path(__file__).parent / "test_queries.json"


@dataclass
class ModelResult:
    """Benchmark results for a single model (or baseline)."""

    model_name: str
    load_time_s: float
    mean_latency_s: float
    mean_ndcg_at_10: float
    mean_mrr: float
    per_query: list[dict] = field(default_factory=list)


def _load_queries(path: Path) -> list[dict]:
    """Load and filter answerable test queries."""
    with open(path) as f:
        queries = json.load(f)
    return [q for q in queries["queries"] if not q.get("unanswerable", False)]


def _result_citekeys(results: list[SearchResult]) -> list[str]:
    """Extract unique citekeys from search results for metric evaluation."""
    seen: set[str] = set()
    citekeys: list[str] = []
    for r in results:
        if r.doc_citekey and r.doc_citekey not in seen:
            seen.add(r.doc_citekey)
            citekeys.append(r.doc_citekey)
    return citekeys


def benchmark_baseline(lib: Library, queries: list[dict], k: int) -> ModelResult:
    """Benchmark vector retrieval without reranking."""
    retriever = lib.get_retriever(mode="vector", rerank=False)

    latencies = []
    ndcgs = []
    mrrs = []
    per_query = []

    for q in queries:
        start = time.perf_counter()
        results = retriever.retrieve(q["text"], k=k)
        elapsed = time.perf_counter() - start

        retrieved_ids = _result_citekeys(results)
        relevant_ids = set(q["relevant_docs"])

        ndcg = ndcg_at_k(retrieved_ids, relevant_ids, k=k)
        mrr = mean_reciprocal_rank(retrieved_ids, relevant_ids)

        latencies.append(elapsed)
        ndcgs.append(ndcg)
        mrrs.append(mrr)
        per_query.append(
            {
                "query_id": q["id"],
                "latency_s": round(elapsed, 4),
                "ndcg_at_k": round(ndcg, 4),
                "mrr": round(mrr, 4),
            }
        )

    return ModelResult(
        model_name="baseline (no reranking)",
        load_time_s=0.0,
        mean_latency_s=sum(latencies) / len(latencies) if latencies else 0.0,
        mean_ndcg_at_10=sum(ndcgs) / len(ndcgs) if ndcgs else 0.0,
        mean_mrr=sum(mrrs) / len(mrrs) if mrrs else 0.0,
        per_query=per_query,
    )


def benchmark_model(lib: Library, model_name: str, queries: list[dict], k: int) -> ModelResult:
    """Benchmark a specific cross-encoder model."""
    from local_library.embeddings.reranking import CrossEncoderReranker, RerankedRetriever

    # Measure model load time
    load_start = time.perf_counter()
    reranker = CrossEncoderReranker(model_name=model_name, lazy_load=False)
    load_time = time.perf_counter() - load_start

    base_retriever = lib.get_retriever(mode="vector", rerank=False)
    retriever = RerankedRetriever(inner=base_retriever, reranker=reranker)

    latencies = []
    ndcgs = []
    mrrs = []
    per_query = []

    for q in queries:
        start = time.perf_counter()
        results = retriever.retrieve(q["text"], k=k)
        elapsed = time.perf_counter() - start

        retrieved_ids = _result_citekeys(results)
        relevant_ids = set(q["relevant_docs"])

        ndcg = ndcg_at_k(retrieved_ids, relevant_ids, k=k)
        mrr = mean_reciprocal_rank(retrieved_ids, relevant_ids)

        latencies.append(elapsed)
        ndcgs.append(ndcg)
        mrrs.append(mrr)
        per_query.append(
            {
                "query_id": q["id"],
                "latency_s": round(elapsed, 4),
                "ndcg_at_k": round(ndcg, 4),
                "mrr": round(mrr, 4),
            }
        )

    return ModelResult(
        model_name=model_name,
        load_time_s=round(load_time, 2),
        mean_latency_s=sum(latencies) / len(latencies) if latencies else 0.0,
        mean_ndcg_at_10=sum(ndcgs) / len(ndcgs) if ndcgs else 0.0,
        mean_mrr=sum(mrrs) / len(mrrs) if mrrs else 0.0,
        per_query=per_query,
    )


def format_comparison(results: list[ModelResult]) -> str:
    """Format results as a comparison table."""
    lines = [
        f"{'Model':<50} {'Load(s)':>8} {'Latency(s)':>11} {'NDCG@10*':>9} {'MRR*':>7}",
        "-" * 90,
    ]
    for r in results:
        lines.append(
            f"{r.model_name:<50} {r.load_time_s:>8.2f} "
            f"{r.mean_latency_s:>11.4f} {r.mean_ndcg_at_10:>9.4f} {r.mean_mrr:>7.4f}"
        )
    lines.append("")
    lines.append("* Quality metrics are informational only (test query set too small for")
    lines.append("  reliable comparison). Re-run after expanding to 50-100 validated queries.")
    return "\n".join(lines)


def main() -> None:
    """Run reranker benchmark."""
    parser = argparse.ArgumentParser(description="Benchmark cross-encoder reranker models")
    parser.add_argument("--k", type=int, default=10, help="Number of results to return")
    parser.add_argument("--output", type=str, help="Path to write JSON results")
    args = parser.parse_args()

    queries = _load_queries(QUERY_FILE)
    print(f"Loaded {len(queries)} answerable queries from {QUERY_FILE}")
    print("NOTE: Quality metrics (NDCG, MRR) are informational only with this query set.")

    all_results: list[ModelResult] = []

    with Library() as lib:
        # Baseline
        print("\nBenchmarking baseline (no reranking)...")
        baseline = benchmark_baseline(lib, queries, k=args.k)
        all_results.append(baseline)
        print(f"  Mean latency: {baseline.mean_latency_s:.4f}s")

        # Each model
        for model_name in MODELS:
            print(f"\nBenchmarking {model_name}...")
            result = benchmark_model(lib, model_name, queries, k=args.k)
            all_results.append(result)
            print(f"  Load time: {result.load_time_s:.2f}s")
            print(f"  Mean latency: {result.mean_latency_s:.4f}s")

    print("\n" + format_comparison(all_results))

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps([asdict(r) for r in all_results], indent=2) + "\n")
        print(f"\nResults written to {output_path}")

    sys.exit(0)


if __name__ == "__main__":
    main()
