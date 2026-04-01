# RAG Pipeline Improvements

Last updated: 2026-04-01

## Vision

Continuously improve the quality, speed, and capability of the retrieval-to-answer pipeline. This area covers everything between "user asks a question" and "system returns a good answer" — embedding strategy, retrieval quality, query processing, and LLM interaction.

Unlike the other feature areas, this isn't building toward a single deliverable. It's an ongoing concern: the pipeline is the foundation that every other feature area depends on, and incremental improvements here compound across the entire system.

## Current State

The pipeline is functional end-to-end with competitive retrieval quality on the dev corpus:
- **Chunking**: Section-aware markdown splitting (~512 tokens, ~15% overlap) via `MarkdownChunker`
- **Embeddings**: nomic-embed-text-v1.5 (768-dim) via sentence-transformers with `search_document:`/`search_query:` prefixes
- **Retrieval**: `VectorRetriever` (cosine similarity), `FTSRetriever` (BM25 via FTS5 with stop-word removal + OR-mode), `HybridRetriever` (RRF fusion, 2:1 vector-to-FTS weight ratio)
- **Reranking**: Document-aware `CrossEncoderReranker` (ms-marco-MiniLM-L-12-v2) via `RerankedRetriever` decorator; enabled by default. Selected via benchmark against 5 candidates (see `docs/benchmarks/2026-03-06-reranker-model-selection.md`)
- **RAG**: `RAGInterface` orchestrates context assembly → prompt construction → LLM generation (LiteLLM)
- **Evaluation**: 76 labeled queries with graded relevance (3-tier), Precision@k, Recall@k, MRR, NDCG@k metrics. See `tests/eval/README.md` for full details

**Baseline results** (hybrid+rerank, ~20-doc dev corpus): MRR=0.913, Recall@10=0.926, NDCG@10=0.896. Conceptual queries are the weakest category (NDCG@10=0.784). Full results in `tests/eval/baseline_results.json`.

## Near-Term: Evaluation Pass and Corpus Scaling

The evaluation pass is underway, gated before full corpus import. See `build_plan.md` § "Post-M7: Pipeline Evaluation and Corpus Scaling".

### Done
- ✓ Expanded query set to 76 queries with graded relevance and annotation rubric
- ✓ Cross-encoder reranking implemented, benchmarked, enabled by default
- ✓ FTS5 query preprocessing: stop-word removal, OR-mode, sanitizer hardening
- ✓ RRF weight tuning (2:1 vector-to-FTS ratio)
- ✓ Baseline evaluation run across all configurations

### In Progress
- Establish quality targets based on baseline analysis
- Investigate conceptual query gap (NDCG@10=0.784 vs 0.896 overall)
- Determine which pipeline improvement to target next

### Remaining Before Corpus Import
- Meet quality targets on dev corpus
- Import full Zotero corpus (~1400 docs)
- Re-evaluate with full corpus

### Improvement Queue

The iterative improvement loop continues. Items completed are struck through; remaining items ordered by expected impact:

1. ~~**Cross-encoder reranking**~~ — Implemented. Document-aware grouping, MiniLM-L-12-v2, sigmoid normalization, broadened candidate pool. Recall@10 improved ~7% over plain vector.

2. ~~**FTS query preprocessing**~~ — Implemented. Stop-word removal + explicit OR mode made FTS viable (was returning 0 results). Asymmetric RRF weights tuned.

3. **Conceptual query improvement** (next target)
   - Queries about mechanisms/arguments score NDCG@10=0.784 vs 0.967 factual
   - Likely causes: distributed arguments across chunks, abstract vocabulary, chunk boundary issues
   - Potential approaches: query expansion, increased chunk overlap, chunk merging at retrieval time, document-level scoring

4. **Query expansion**
   - Synonym injection, acronym resolution
   - Potentially: LLM-based query rewriting (pre-search)

5. **Chunk preprocessing**
   - Filter non-semantic content from chunks (headers, footers, reference lists)
   - Consider: separate "display text" vs. "embedding text" per chunk

If the above aren't sufficient:

5. **Embedding strategy changes** (require re-embedding entire corpus)
   - Late chunking (embed full document, chunk embeddings post-hoc)
   - Alternative embedding models (Qwen3, BGE, E5-Mistral)
   - Different chunking parameters (size, overlap, boundary strategy)

6. **Hierarchical retrieval**
   - Document-level embeddings (of summaries or full text) for coarse retrieval
   - Then chunk-level retrieval within top documents
   - See `project_breakdown.md` notes on multi-stage search

## Longer-Term Ideas

### Local LLM Experimentation
- Run a small, quantized model locally for query rewriting, answer generation, or both
- Relevant if hardware improves or for latency-sensitive operations where API round-trips are too slow
- Could serve as fallback when no API key is configured

### Answer Quality Improvements
- Better context assembly (reorder chunks for coherence, not just relevance)
- Citation precision: LLM cites specific chunks, not just documents
- Confidence scoring for answers (how well-supported is this answer by the retrieved context?)
- "I don't know" calibration: reliably abstain when context is insufficient

### Advanced Retrieval Strategies
- HyDE (Hypothetical Document Embeddings): generate a hypothetical answer, embed it, search for similar real chunks
- Multi-hop retrieval: answer complex questions by chaining retrieval steps
- Contextual retrieval: use surrounding chunks to disambiguate

### Performance
- Latency optimization for the vector search portion (the LLM portion is less controllable)
- ONNX export for embedding/reranking models
- Investigate whether sqlite-vec is the bottleneck at scale, or something else
- Scale ceiling assessment: when does brute-force search become unacceptable? (~250K vectors estimated)

## Open Questions

- What quality targets are appropriate? Baseline is established (MRR=0.913, NDCG@10=0.896); targets need to be set based on this and expected degradation at scale.
- What's the right approach for the conceptual query gap? Chunk overlap tuning is cheap; query expansion is more complex but potentially higher impact.
- Should the evaluation framework test end-to-end RAG answer quality, or just retrieval quality? Retrieval is now well-measured; answer quality evaluation is the remaining gap.
- At what corpus size does performance become a concern? ~20 documents currently; need to reassess after full corpus import (~1400 docs, ~100K+ vectors).
- Is there a meaningful difference between "good retrieval" and "good for citation search"? The Neovim workflow may need different tuning than general RAG queries.

## Dependencies

**Provides to other areas:**
- Search quality directly affects Neovim Citation Workflow relevance
- Embedding quality affects Automated Content Analysis (clustering, tagging)
- Pipeline improvements apply to web content once ingested

**Needs from other areas:**
- None — this area improves existing infrastructure

## References

- `build_plan.md` § "Post-M7: Pipeline Evaluation and Corpus Scaling" — evaluation pass sequencing
- `docs/design-plans/2026-03-05-document-aware-cross-encoder-reranking.md` — cross-encoder design
- `tests/eval/` — existing evaluation framework (retrieval_eval.py, test_queries.json)
- `RAG_background/00_final_summary_report.md` — original RAG architecture recommendations
- `RAG_background/embedding_approaches_report.md` — embedding model analysis
- `RAG_background/vector_storage_report.md` — storage and search strategies
- `project_breakdown.md` — notes on retrieval improvements, hierarchical search, late chunking
