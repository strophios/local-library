"""Warm reranked hybrid search latency benchmark.

Skipped by default. Run with:
    uv run pytest tests/integration/daemon/test_search_latency.py --run-daemon-latency

Confirms Phase 3's "Done when":
    Measured warm reranked hybrid search latency on the dev corpus
    confirms p95 ≤ 500 ms.
"""

from __future__ import annotations

import time

import pytest

from local_library.core.library import Library

pytestmark = pytest.mark.daemon_latency


WARM_UP_QUERIES = ["retrieval augmented generation"] * 5
BENCHMARK_QUERIES = [
    "embeddings improve search quality over keyword matching",
    "single-instance daemon prevents concurrent database access",
    "JSON-RPC error codes map to domain error categories",
    "cross-encoder reranking improves NDCG over bi-encoder retrieval",
    "asyncio event loops compose with thread pool executors",
] * 10


def test_warm_reranked_hybrid_p95_under_500ms() -> None:
    with Library(embed_on_add=False) as lib:
        retriever = lib.get_retriever(mode="hybrid", rerank=True)
        for q in WARM_UP_QUERIES:
            retriever.retrieve(query=q, k=10)

        latencies: list[float] = []
        for q in BENCHMARK_QUERIES:
            t0 = time.perf_counter()
            retriever.retrieve(query=q, k=10)
            latencies.append(time.perf_counter() - t0)

        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(0.95 * len(latencies))]
        p99 = latencies[min(int(0.99 * len(latencies)), len(latencies) - 1)]

        print(
            f"\n  p50={p50 * 1000:.1f}ms  p95={p95 * 1000:.1f}ms  p99={p99 * 1000:.1f}ms"
            f"  (n={len(latencies)})"
        )

        assert p95 < 1.0, (
            f"warm reranked hybrid p95={p95 * 1000:.0f}ms exceeds 1s — "
            f"latency target needs revisiting"
        )
        if p95 > 0.5:
            pytest.fail(
                f"p95={p95 * 1000:.0f}ms exceeds 500ms target. This is the design's "
                f"developer yardstick; investigate before declaring Phase 3 done."
            )
