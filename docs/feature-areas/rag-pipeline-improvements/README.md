# RAG Pipeline Improvements

Last updated: 2026-04-17

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

**Dev-corpus baseline** (hybrid+rerank, ~20 docs, post-extraction-fix): English-only MRR=0.944, Recall@10=0.979, NDCG@10=0.947 on 70 queries. Aggregate NDCG@10=0.880 when cross-language queries are folded in; per-query diagnosis shows the aggregate "conceptual query gap" is mostly cross-language contamination, not a structural conceptual-retrieval weakness. Full results in `tests/eval/baseline_results.json`; analysis in `tests/eval/README.md`.

**Full corpus imported** (1,216 docs, 99.3% success). Initial corpus-scale eval run shows apparent quality regression — see below for why this is largely an annotation artifact rather than a real retrieval regression.

## Near-Term: Eval Re-Annotation at Corpus Scale

The big shift: the evaluation framework was built and tuned against a 20-doc dev set. At 1,216 documents, the same 76 queries surface many more plausibly-correct results that aren't in the gold set, so they score as misses even when retrieval is working correctly. The corpus-scale numbers look worse than the dev-corpus numbers, but this reflects the annotation gap, not a pipeline regression. Informal manual spot-checking of queries at corpus scale suggests retrieval quality is fine.

The real next step is making the eval set meaningful at the new scale before investing more in pipeline tuning:

- **Re-annotate existing 76 queries** against the full corpus — each query likely has additional relevant documents we didn't know existed at the dev-corpus stage.
- **Expand the query set** — more queries, better coverage across categories and document types now that the corpus is diverse.
- **Add chunk-level annotations** — current annotations are document-level. Chunk-level gold data would let us measure retrieval precision more directly and separate retrieval quality from chunk-selection quality.
- **Reassess quality targets** once the eval infrastructure is solid at scale.

The existing improvement queue (conceptual query gap, query expansion, etc.) is still valid, but prioritizing it over re-annotation would mean tuning against noisy signal.

### Done
- ✓ Expanded query set to 76 queries with graded relevance and annotation rubric (dev-corpus scale)
- ✓ Cross-encoder reranking implemented, benchmarked, enabled by default
- ✓ FTS5 query preprocessing: stop-word removal, OR-mode, sanitizer hardening
- ✓ RRF weight tuning (2:1 vector-to-FTS ratio)
- ✓ Baseline evaluation run across all configurations (dev corpus)
- ✓ Full Zotero corpus imported (1,216 docs)
- ✓ First pass of corpus-scale eval — results flagged as annotation-limited

### In Progress / Blocked

- **Re-annotation at corpus scale** — eval set expansion and re-scoring (top priority; blocks most other work)
- **Establish corpus-scale quality targets** (blocked on re-annotation)
- **Investigate conceptual query gap** at corpus scale (blocked on re-annotation — dev-corpus gap may or may not survive re-annotation)

### Improvement Queue

Items below are still ordered roughly by expected impact once the eval infrastructure supports meaningful measurement at corpus scale:

1. ~~**Cross-encoder reranking**~~ — Implemented. Document-aware grouping, MiniLM-L-12-v2, sigmoid normalization, broadened candidate pool. Recall@10 improved ~7% over plain vector on dev corpus.
2. ~~**FTS query preprocessing**~~ — Implemented. Stop-word removal + explicit OR mode made FTS viable (was returning 0 results). Asymmetric RRF weights tuned.

3. **Conceptual query improvement**
   - Dev-corpus aggregate conceptual NDCG@10=0.784 was largely driven by cross-language misses; English conceptual NDCG@10=0.911 (only one genuine English miss, `conceptual_002` against Sewell1996a)
   - The remaining English gap may not survive re-annotation at corpus scale — it's two queries on 20 docs
   - If it does: candidate approaches are query expansion, increased chunk overlap, chunk merging at retrieval time, or document-level scoring

4. **Cross-language retrieval** (known limitation)
   - German documents (Marx1968, Benjamin2014) poorly retrieved by English queries
   - nomic-embed-text is English-primary; cross-language alignment is fragile
   - Extraction changes that improve English text quality can degrade cross-language retrieval by shifting embedding space
   - Options: multilingual embedding model, query expansion with translated terms, dual embeddings, or accept as limitation
   - See `tests/eval/README.md` § "Cross-Language Retrieval Limitation" for full analysis

5. **Query expansion**
   - Synonym injection, acronym resolution
   - Potentially: LLM-based query rewriting (pre-search)

6. **Chunk preprocessing**
   - Filter non-semantic content from chunks (headers, footers, reference lists)
   - Consider: separate "display text" vs. "embedding text" per chunk

If the above aren't sufficient:

7. **Embedding strategy changes** (require re-embedding entire corpus)
   - Late chunking (embed full document, chunk embeddings post-hoc)
   - Alternative embedding models (Qwen3, BGE, E5-Mistral)
   - Different chunking parameters (size, overlap, boundary strategy)

8. **Hierarchical retrieval**
   - Document-level embeddings (of summaries or full text) for coarse retrieval
   - Then chunk-level retrieval within top documents

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

- How do we efficiently re-annotate 76 queries against 1,216 documents? Full manual review is prohibitive. Options: run each query and annotate the top-N returned results (biased toward whatever retriever we use), LLM-assisted annotation with human spot-checking, or sampling-based approaches. Likely some combination.
- Should we expand the query set before or after re-annotating existing queries? Re-annotating first gives a consistent baseline; expanding first gets more signal but means annotating more queries twice (once naively, once properly).
- What quality targets are appropriate once we have solid corpus-scale measurements? Dev-corpus English-only numbers (MRR=0.944, NDCG@10=0.947) set a ceiling expectation, but degradation at scale is expected and normal.
- What's the right approach for the conceptual query gap? Chunk overlap tuning is cheap; query expansion is more complex but potentially higher impact. May or may not survive re-annotation.
- Should the evaluation framework test end-to-end RAG answer quality, or just retrieval quality? Retrieval is well-measured on dev corpus; answer quality evaluation is the remaining gap.
- Is there a meaningful difference between "good retrieval" and "good for citation search"? The Neovim workflow may need different tuning than general RAG queries.

## Dependencies

**Provides to other areas:**
- Search quality directly affects Neovim Citation Workflow relevance
- Embedding quality affects Automated Content Analysis (clustering, tagging)
- Pipeline improvements apply to web content once ingested

**Needs from other areas:**
- None — this area improves existing infrastructure

## References

- `docs/archive/build_plan.md` § "Post-M7: Pipeline Evaluation and Corpus Scaling" — evaluation pass sequencing
- `docs/design-plans/2026-03-05-document-aware-cross-encoder-reranking.md` — cross-encoder design
- `tests/eval/` — existing evaluation framework (retrieval_eval.py, test_queries.json)
- `RAG_background/00_final_summary_report.md` — original RAG architecture recommendations
- `RAG_background/embedding_approaches_report.md` — embedding model analysis
- `RAG_background/vector_storage_report.md` — storage and search strategies
