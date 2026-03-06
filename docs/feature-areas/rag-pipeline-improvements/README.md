# RAG Pipeline Improvements

Last updated: 2026-03-06

## Vision

Continuously improve the quality, speed, and capability of the retrieval-to-answer pipeline. This area covers everything between "user asks a question" and "system returns a good answer" — embedding strategy, retrieval quality, query processing, and LLM interaction.

Unlike the other feature areas, this isn't building toward a single deliverable. It's an ongoing concern: the pipeline is the foundation that every other feature area depends on, and incremental improvements here compound across the entire system.

## Current State

The pipeline is functional end-to-end:
- **Chunking**: Section-aware markdown splitting (~512 tokens, ~15% overlap) via `MarkdownChunker`
- **Embeddings**: nomic-embed-text-v1.5 (768-dim) via sentence-transformers with `search_document:`/`search_query:` prefixes
- **Retrieval**: `VectorRetriever` (cosine similarity), `FTSRetriever` (BM25 via FTS5), `HybridRetriever` (RRF fusion)
- **RAG**: `RAGInterface` orchestrates context assembly → prompt construction → LLM generation (LiteLLM)
- **Evaluation**: 12 labeled test queries with Precision@k, Recall@k, MRR, NDCG@k metrics

The cross-encoder reranking stage has been designed (`docs/design-plans/2026-03-05-document-aware-cross-encoder-reranking.md`) but not implemented.

## Near-Term: Post-M7 Evaluation Pass

This is the immediate work, gated before full corpus import. See `build_plan.md` § "Post-M7: Pipeline Evaluation and Corpus Scaling".

### Evaluation Framework Expansion
- Expand test query set from 12 to 50-100 queries
- Write queries against documents actually read and queried (not synthetic)
- Annotate with relevance judgments at chunk level (not just document level)
- Establish quality targets: Precision@5, MRR, answer quality rubric
- Add latency benchmarks per operation

### Iterative Improvement Loop

Evaluate → identify weaknesses → implement next improvement → re-evaluate. Stop when benchmarks are met. The improvement queue, roughly ordered by cost/complexity:

1. **Cross-encoder reranking** (design complete)
   - Document-aware grouping + cross-encoder rescoring
   - Expected: significant precision improvement with modest latency cost
   - See `docs/design-plans/2026-03-05-document-aware-cross-encoder-reranking.md`

2. **Query preprocessing**
   - FTS5 query sanitization (partially implemented — natural language queries now handled)
   - Query expansion: synonym injection, acronym resolution
   - Potentially: LLM-based query rewriting (pre-search)

3. **Chunk preprocessing**
   - More aggressive markdown/formatting cleanup for chunk text (partially addressed)
   - Filter non-semantic content from chunks (headers, footers, reference lists)
   - Consider: separate "display text" vs. "embedding text" per chunk

4. **Retrieval parameter tuning**
   - RRF k parameter (currently 60)
   - Vector/FTS weight balance
   - Candidate pool sizes
   - Cross-encoder model selection (MiniLM-L-6 vs L-12 vs BGE-reranker-v2-m3)

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

- What quality targets are appropriate? Need to establish these during the evaluation pass.
- Should the evaluation framework test end-to-end RAG answer quality, or just retrieval quality? (The build plan suggests both, with retrieval as baseline and answer quality as the more informative signal.)
- At what corpus size does performance become a concern? Currently running against ~20 documents.
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
