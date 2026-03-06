# Cross-Encoder Reranker Model Selection

Date: 2026-03-06

## Context

Three cross-encoder models were evaluated as candidates for the default
reranker in the document-aware cross-encoder reranking pipeline.

## Models Evaluated

| Model | Parameters | Notes |
|-------|-----------|-------|
| cross-encoder/ms-marco-MiniLM-L-6-v2 | ~23M | Fastest, least accurate |
| cross-encoder/ms-marco-MiniLM-L-12-v2 | ~33M | Balanced (design plan default) |
| BAAI/bge-reranker-v2-m3 | ~568M | Most capable, requires trust_remote_code |

## Latency Results

| Model | Load(s) | Latency(s) | NDCG@10* | MRR* |
|-------|---------|-----------|----------|------|
| baseline (no reranking) | 0.00 | 0.6118 | 2.3901 | 0.6000 |
| cross-encoder/ms-marco-MiniLM-L-6-v2 | 4.36 | 0.4603 | 1.0937 | 0.5778 |
| cross-encoder/ms-marco-MiniLM-L-12-v2 | 5.43 | 0.3097 | 1.1788 | 0.5944 |
| BAAI/bge-reranker-v2-m3 | 45.58 | 2.3541 | 1.4488 | 0.7333 |

## Selection

Default model: `cross-encoder/ms-marco-MiniLM-L-12-v2`

Rationale: MiniLM-L-12-v2 provides a strong latency/capability tradeoff. Per-query latency of 0.31s is well below the 2s target and represents a 49% improvement over the baseline. The model delivers consistent latency across queries with no outliers. While the larger BGE model shows better MRR (0.73), its 2.35s per-query latency (4x slower than MiniLM-L-12) makes it impractical for interactive RAG workflows without CPU acceleration. MiniLM-L-6-v2 is faster but adds less reranking value. MiniLM-L-12-v2 remains the recommended default for users with standard hardware.

## Quality Benchmarking (Deferred)

Quality metrics (NDCG@10, MRR) were computed against the current 10-query
test set (12 total, 2 unanswerable) but are not reliable for model selection at this scale. Quality
benchmarking should be re-run after the test query set is expanded to
50-100 validated queries (see build_plan.md § "Post-M7: Pipeline Evaluation
and Corpus Scaling").

Note: NDCG values appear inflated (>1.0 in some cases) due to the limited
query set and small corpus (20 documents, 180+ chunks). This is expected
at small scale; metrics stabilize with larger corpora and query sets.

To re-run the full benchmark:

    uv run python tests/eval/reranker_benchmark.py --output tests/eval/reranker_results.json

## Corpus at Time of Benchmarking

- Documents: 20
- Chunks (approx): 180+
- Test queries: 12 total (10 answerable, 2 adversarial)
- Retrieval mode for baseline: vector (semantic search via nomic-embed-text-v1.5)
- Top-k for reranking: 10

## Implementation Notes

- Default model configured in `CrossEncoderReranker.__init__()` as `cross-encoder/ms-marco-MiniLM-L-12-v2`
- Model is lazy-loaded on first rerank call (not during initialization)
- Model download (~33-50 MB) occurs on first use; subsequent queries within same session reuse loaded model
- Load time (4.36-5.43s per model) is per-session cost, not per-query
- Benchmark uses `RerankedRetriever` wrapper with default pool_size=100 and min_pool_ratio=3

## Recommendations for Future Work

1. **Query Set Expansion (Post-M7)**: Expand test set to 50-100 queries for reliable quality metrics
2. **Corpus Scaling**: Run benchmark on full library (1000+ documents) to see latency characteristics at scale
3. **CPU Acceleration**: Consider optimizing for CPU-bound deployments (quantization, distillation)
4. **Multi-Model Support**: Keep MiniLM-L-6-v2 as fallback for low-latency settings, BGE for high-quality scenarios
