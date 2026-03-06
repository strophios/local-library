# Retrieval Improvement Techniques: Comparative Study

Last updated: 2026-03-05

## Context and Motivation

The current local-library RAG pipeline uses a straightforward single-pass architecture:

```
user question (unchanged) → hybrid retrieval (vector + FTS5 via RRF) → context assembly → LLM
```

The primary pain point is **vocabulary mismatch**: queries using different terminology than the source documents return irrelevant results. The corpus is currently ~20 documents for testing but will grow to ~1200 (Zotero import) and beyond (web ingestion).

This report evaluates five retrieval improvement techniques against the current baseline.

---

## 1. Query Expansion / Multi-Query Rewriting

### Mechanism

An LLM generates multiple alternative phrasings of the user's query. Retrieval runs against all variants, and results are merged (typically via RRF or union + dedup). Variants include:

- **Multi-query**: Generate 3-5 reformulations, retrieve for each, fuse results
- **Query rewriting**: Single improved query (more search-friendly phrasing)
- **Step-back prompting**: Generate a more abstract/general version alongside the original
- **RAG-Fusion**: Combine reformulated query results using reciprocal rank fusion

### Quality Impact

Strong evidence for significant improvement over baseline RAG:

- RQ-RAG achieves ~288% improvement on PopQA, ~275% over standard retrieval on HotpotQA (multi-hop tasks)
- Directly addresses vocabulary mismatch by generating synonym-rich alternative phrasings
- Multi-query approaches broaden recall by covering more of the terminology space

**Failure modes** (important): Recent research (arXiv:2505.12694) identifies two specific failure conditions:
1. **Unfamiliar queries**: When the LLM lacks knowledge about the topic, expansion degrades retrieval. More severe in general domains than specialized ones.
2. **Ambiguous queries**: LLMs exhibit popularity bias — expansion surfaces documents for common interpretations, reducing recall for rare ones.
3. **Corpus drift**: Expansions generated from the LLM's training data may not align with corpus-specific vocabulary, producing hallucinated terms.

Query *rewriting* approaches (GaQR) are more robust than answer-generation approaches (HyDE, Q2D) because they avoid requiring specific knowledge about query content.

### Local Feasibility

Promising. GOLFer (arXiv:2506.04762) demonstrates that LLaMA-3-8B with a hallucination filter outperforms HyDE with GPT-4o on some retrieval datasets. The key insight: smaller models can generate useful expansions if you filter out hallucinated/non-factual terms.

However, running a 7-8B model locally adds significant memory overhead (~16GB) and inference time. For query expansion specifically (short output), local 7B models on Apple Silicon should produce results in 1-3 seconds.

**Alternative**: For our FTS5 component, a simpler non-LLM approach could work: expand the query with synonyms from a thesaurus or WordNet. No LLM required, zero latency cost, and specifically targets the BM25 lexical matching that FTS5 does. This wouldn't help the vector component but would strengthen FTS within our existing hybrid pipeline.

### Latency

- Cloud LLM call: ~0.5-2s per expansion (3-5 expansions → 0.5-2s total if parallelized)
- Local 7B model: ~1-3s for generating expansions
- Additional retrieval runs: minimal (retrieval itself is fast against SQLite)
- Total added: ~1-3s typical

### Implementation Complexity

Moderate. Core changes:
1. Add a query expansion step before retrieval in `Library.query()`
2. Run retrieval N times (once per expanded query)
3. Merge results via RRF (we already have `_rrf_fuse`)
4. The LLM call uses our existing `LLMClient` abstraction

### Composability

Excellent. Query expansion is "upstream" of everything else — it improves what goes into retrieval. Composes naturally with:
- Reranking (expand → retrieve → rerank)
- Multi-stage retrieval (expand → coarse → fine)
- Late chunking (orthogonal — expansion is query-side, late chunking is index-side)

Caution: Using expanded queries directly with cross-encoder rerankers can cause "query distribution shift" — the expanded text looks different from the short queries the reranker was trained on.

### Scale Behavior

- **20 docs**: Still helpful for vocabulary mismatch, but the small corpus means most relevant docs will be retrieved anyway. Effect may be subtle.
- **1200+ docs**: Increasingly important. More documents means more terminology variation and more opportunities for vocabulary mismatch. The benefits compound with corpus size.
- **Testing note**: At 20 docs, query expansion will primarily help with recall of specific documents that use different terminology than the query. The improvement may not be dramatic but should be measurable on targeted test cases.

---

## 2. HyDE (Hypothetical Document Embeddings)

### Mechanism

Instead of embedding the user's query directly, HyDE:
1. Uses an LLM to generate a **hypothetical answer** to the query
2. Embeds that hypothetical document
3. Uses the resulting vector for similarity search

The intuition: a plausible answer paragraph is closer in embedding space to the actual source passages than a short question is.

### Quality Impact

The original paper (Gao et al., 2022) shows HyDE significantly outperforms unsupervised dense retrievers (Contriever) and approaches the performance of fine-tuned retrievers across web search, QA, and fact verification — all in a zero-shot setting.

**Best use cases**:
- Domain-specific content where retrievers may not generalize well
- Complex, abstract, or multi-faceted queries
- Situations with significant vocabulary gap between questions and documents

**Failure modes**:
- **Unfamiliar topics**: If the LLM lacks domain knowledge, the hypothetical document will be wrong, pulling retrieval in the wrong direction. This can *hurt* performance vs. baseline.
- **Factual/specific queries**: For queries like "What year was X published?", a hypothetical answer may hallucinate details that mislead vector search.
- **Latency-sensitive paths**: Adds both LLM generation and re-embedding time.

### Local Feasibility

Challenging. HyDE requires the LLM to generate a coherent, topically relevant passage — a harder task than query expansion. Small local models (7B) produce lower-quality hypothetical documents, and the quality of HyDE is directly tied to the quality of the generated text.

GOLFer demonstrates that hallucination filtering can compensate for small model weaknesses, but this adds complexity.

### Latency

- LLM generation: ~1-3s (cloud) or ~3-8s (local 7B for a paragraph)
- Re-embedding: ~50-100ms (nomic-embed is fast)
- Total added: ~1-8s depending on model choice

### Implementation Complexity

Moderate. Similar to query expansion but instead of running multiple retrievals, you replace the query embedding:
1. Generate hypothetical document via LLM
2. Embed with `search_document:` prefix (not `search_query:`)
3. Use resulting vector for similarity search
4. Optionally blend with original query embedding (weighted average)

### Composability

Mixed. HyDE modifies the vector search specifically — it doesn't help FTS5 at all. This means:
- **With hybrid search**: Only improves the vector component; FTS5 still uses the original query
- **With query expansion**: Can combine (expand for FTS, HyDE for vector), but adds complexity
- **With reranking**: Works well — HyDE improves initial retrieval, reranker refines ordering
- **With late chunking**: Orthogonal and compatible

Research warns that using HyDE-generated text directly with cross-encoder rerankers causes query distribution shift, degrading reranker performance.

### Scale Behavior

- **20 docs**: Benefits are unclear. With few documents, the embedding space is sparse and even a mediocre query vector will find relevant content. HyDE's advantage emerges when the embedding space is crowded.
- **1200+ docs**: More beneficial. Denser embedding space means the quality of the query vector matters more for distinguishing relevant from irrelevant.
- **Testing note**: At 20 docs, HyDE may show minimal or even negative impact. Don't evaluate it on the small corpus alone.

---

## 3. Multi-Stage / Hierarchical Retrieval

### Mechanism

Decompose retrieval into stages, from coarse to fine:

1. **Coarse stage**: Score at document level (e.g., average of chunk embeddings, or a separate document-level embedding) to identify candidate documents
2. **Fine stage**: Search chunks within the top-K documents
3. **Optional reranking stage**: Cross-encoder or LLM rescoring of final candidates

Variants include:
- **Document-level pre-filtering**: Score documents, then retrieve chunks from top documents only
- **Hierarchical indices**: Maintain document, section, and chunk-level indices
- **Multi-scale chunking**: Index at multiple chunk sizes (100, 200, 500 tokens), fuse results via RRF — shown to improve retrieval by 1-37% across benchmarks

### Quality Impact

Hierarchical RAG reduces noise, lowers inference costs, and improves answer fidelity by ensuring retrieved chunks come from contextually relevant documents rather than isolated matching passages.

The benefit is primarily about **precision in context assembly** — preventing the RAG context from being polluted by chunks that match keywords but come from irrelevant documents.

### Local Feasibility

Fully local. No LLM required. The coarse stage can be implemented with:
- Average chunk embeddings per document (compute once at index time)
- BM25 document-level scoring
- Metadata-based filtering (already partially supported via `--doc` flag)

### Latency

Minimal additional latency. The coarse stage adds one cheap query (document-level vector search or BM25), and the fine stage searches a reduced set. Net effect may actually be *faster* than searching all chunks, especially at 1200+ documents.

### Implementation Complexity

Moderate to high. Requires:
1. Document-level embeddings (store average of chunk vectors, or a separate embedding)
2. A two-pass retrieval flow in `Library.query()`
3. Changes to `EmbeddingStorage` to support document-level queries
4. Decision on how to compute document-level scores

### Composability

Good. Multi-stage is a retrieval architecture that other techniques plug into:
- Query expansion → multi-stage retrieval (expanded queries drive the coarse stage)
- Multi-stage → reranking (rerank the final chunk results)
- Late chunking (improves chunk embedding quality within the fine stage)

### Scale Behavior

This is the most scale-dependent technique:

- **20 docs**: Minimal benefit. With 20 documents and ~100-500 chunks total, single-pass retrieval is fast and effective. Adding a coarse stage adds complexity without meaningful quality gain.
- **1200+ docs**: Significant benefit. With ~6000-50000 chunks, the probability of irrelevant chunks scoring highly increases. Document-level pre-filtering reduces this noise substantially.
- **10K+ docs**: Essential. Brute-force chunk search becomes both slower and noisier.
- **Testing note**: At 20 docs, this technique will show negligible improvement. Plan to evaluate it after Zotero import.

---

## 4. Late Chunking

### Mechanism

Standard chunking: split document into chunks → embed each chunk independently.

Late chunking: embed the full document as one sequence → pool token-level embeddings into chunk-level vectors.

The key difference: in late chunking, each chunk's embedding is computed with **full attention across the entire document**. A methods section "knows" about the abstract; a results section "knows" about the methodology. This preserves long-range context that standard chunking destroys.

Implementation:
1. Tokenize the full document (must fit in model context window)
2. Forward pass through the embedding model (produces token-level embeddings)
3. Map chunk boundaries onto the token sequence
4. Mean-pool token embeddings within each chunk span

### Quality Impact

Late chunking produces contextually richer embeddings with the same storage cost as standard chunking. Jina AI's research shows it preserves contextual information that is lost in naive chunking, particularly for:
- Cross-section references ("the method described above")
- Anaphoric references ("this approach", "their results")
- Terminology defined earlier in the document

The improvement is most pronounced for academic papers where sections reference each other heavily.

### Local Feasibility

Feasible with caveats:

- **nomic-embed-text-v1.5**: 137M parameters, 8192 token context window. Running a full 8192-token forward pass on Apple Silicon CPU is feasible but slower than standard chunking (one long pass vs. several short passes). Memory is manageable (~500MB-1GB).
- **Implementation**: ~30 lines of code change to the pooling step. The main work is extracting token-level embeddings before pooling, mapping chunk boundaries to token positions, then mean-pooling within each chunk span.

### The Context Window Problem

This is the critical constraint for our corpus:
- **~60% of documents** fit within 8192 tokens — late chunking works fully
- **~40% of documents** exceed 8192 tokens — need a fallback strategy

Options for overflow documents:
1. **Hybrid approach**: Late-chunk the first 8192 tokens, standard-chunk the remainder. Boundary chunks lose some context.
2. **Sliding window**: Process in overlapping 8192-token windows. Better context continuity but more complex.
3. **Switch embedding models**: A larger context window model could reduce or eliminate the overflow problem.

The 60/40 split means any implementation must handle both paths, adding complexity. As web ingestion grows the corpus, the ratio improves (web articles are typically shorter).

### Embedding Model Alternatives for Late Chunking

Could a different embedding model with a larger context window make late chunking viable for the full corpus? The answer is: **not compellingly, given current local-deployment constraints.**

#### Models with 32K+ Context Windows

| Model | Context | MTEB (English) | Params | Local on Apple Silicon? | Inference (8K doc) |
|-------|---------|----------------|--------|------------------------|-------------------|
| nomic-embed-text-v1.5 (current) | 8K | 62.3% | ~137M | Yes (CPU) | 300-500ms |
| Jina-v3 | 8K | 65.5% | 570M | Yes (MPS) | 500ms-1s |
| Qwen3-Embedding-0.6B | **32K** | 64.3% | 0.6B | Yes (GGUF, ~1-2GB) | 2-5s |
| Qwen3-Embedding-8B | 32K | **70.6%** | 8B | No (16-32GB VRAM) | N/A locally |
| NV-Embed-v2 | 32K | 72.3% | 8B | No (GPU-only) | N/A locally |

**Key finding**: The only locally-viable 32K model is **Qwen3-Embedding-0.6B**. It offers only a 2-point MTEB improvement over nomic (64.3% vs 62.3%) at 4-10x slower inference. The models that are actually *much better* (Qwen3-8B at 70.6%, NV-Embed-v2 at 72.3%) cannot run on consumer Apple Silicon.

**Jina-v3** is notable for a different reason: same 8K context as nomic but 3 points better on MTEB (65.5%), and Jina AI specifically developed late chunking — Jina models have the best-documented late chunking support. A switch to Jina-v3 would improve retrieval quality generally *and* provide the best foundation if late chunking is implemented later. This is worth evaluating independently of late chunking.

#### Assessment

A model switch does not solve the late chunking overflow problem — no locally-viable model covers all documents in a single pass. The decision on late chunking should be based on whether the quality gain justifies the complexity of a dual-path implementation (late chunking for ≤8K documents, standard for overflow), not on the availability of a larger-context model.

If late chunking is implemented, **Jina-v3** is the natural model to pair it with (better MTEB, designed for late chunking, same 8K context as current setup). This would also provide a standalone retrieval quality improvement independent of late chunking.

### Latency

For documents within the context window:
- One forward pass of 8192 tokens vs. ~10-20 forward passes of ~400 tokens each
- The single long pass is typically slower than the sum of short passes (quadratic attention scaling), but not dramatically so
- Estimated: ~2-5x slower per document at embedding time (index time, not query time)
- **No query-time latency impact** — embeddings are computed at index time

### Implementation Complexity

Moderate. The core algorithm is simple (~30 lines), but:
1. Must extract token-level embeddings from sentence-transformers (need to bypass final pooling)
2. Must map chunk text boundaries to token positions (use tokenizer offset mapping)
3. Must handle the overflow case for documents exceeding context window
4. Re-embedding existing documents required (one-time migration)

### Composability

Orthogonal to query-side techniques:
- **Query expansion**: Fully compatible (late chunking is index-side)
- **Reranking**: Compatible (rerankers work on text, not embeddings)
- **Multi-stage retrieval**: Compatible and potentially synergistic — better chunk embeddings improve both coarse and fine stages
- **HyDE**: Compatible (HyDE modifies query embedding, late chunking modifies document embeddings)

### Scale Behavior

Scale-independent in a different way than other techniques:

- **Effect scales with document length**, not corpus size. Long documents benefit more.
- **20 docs vs 1200 docs**: Same per-document improvement. More documents means more total benefit, but the marginal improvement per document doesn't change.
- **Testing note**: Late chunking's benefit should be measurable even at 20 docs, provided some are long enough for cross-section context to matter. Test with queries that require understanding context from multiple sections of a single document.

---

## 5. Cross-Encoder Reranking (Document-Aware)

### Mechanism

After initial retrieval (bi-encoder + FTS5 hybrid), pass candidates through a cross-encoder model that jointly encodes (query, passage) pairs with full cross-attention. The cross-encoder produces a relevance score for each pair, and results are reordered.

Cross-encoders are more accurate than bi-encoders because they see the full interaction between query and passage tokens, but too slow for full corpus search (must score each candidate individually).

#### Naive vs. Document-Aware Reranking

**Naive approach** (standard): Retrieve top-N chunks, rerank them, return top-k. Problem: if 5 of the top 10 chunks come from the same document, the final context lacks source diversity. Relevant content from other documents gets crowded out.

**Document-aware approach** (recommended): Use document structure to ensure source diversity:

```
1. Retrieve top-100 chunks via hybrid search (larger initial k)
2. Group chunks by parent document
3. For each document with ≥1 chunk in the top-100:
   - Select the top 2-3 chunks (by initial retrieval score)
4. Rerank all selected chunks via cross-encoder
5. Return top-k results
```

This approach:
- **Guarantees source diversity**: Every document with signal gets representation in the reranking pool
- **Catches cross-section relevance**: Taking 2-3 chunks per document surfaces passages that aren't individually top-ranked but come from highly relevant documents
- **Is efficient**: If 100 chunks span 25 documents, you rerank ~50-75 pairs instead of 100
- **Provides lightweight multi-stage retrieval**: Instead of building a separate document-level index, you derive document-level signal from chunk-level retrieval you're already doing — most of the benefit of hierarchical retrieval with minimal implementation cost

This is related to but distinct from the full multi-stage retrieval in Section 3. Full multi-stage builds a separate document-level index and does explicit coarse→fine passes. Document-aware reranking achieves a similar effect as a post-processing step on existing chunk retrieval.

### Quality Impact

Cross-encoder reranking provides consistent improvements over bi-encoder retrieval:
- Dedicated rerankers achieve ~0.78 NDCG@10, outperforming LLM-based reranking (~0.70 NDCG@10)
- The primary value is **precision improvement** — better ordering of the top results
- Cross-encoders trained on diverse datasets generalize well to new domains
- Document-aware grouping adds **source diversity** on top of precision — the RAG context draws from more documents, reducing the risk of missing relevant sources

**Regarding vocabulary mismatch specifically**: Cross-encoders help indirectly. They can recognize that a passage about "model performance metrics" is relevant to a query about "machine learning accuracy" because they see the full token interaction. However, they can only rerank what was *retrieved* — if the relevant passage wasn't in the initial candidate set, reranking can't help. The document-aware approach partially mitigates this: by pulling 2-3 chunks per candidate document, it surfaces passages that may use different vocabulary than the top-scoring chunk from that document.

**Diminishing returns with hybrid search**: Our current hybrid search (vector + FTS5 via RRF) already creates a "relevance ceiling." Adding reranking still helps order within that ceiling, but the marginal improvement is smaller than adding reranking to vector-only retrieval. Document-aware grouping provides additional value beyond pure reranking by changing *which* candidates are considered.

### Local Feasibility

**Very feasible.** This is the most practical local technique:

| Model | Parameters | Memory | CPU Latency (per pair) | NDCG@10 |
|-------|-----------|--------|----------------------|---------|
| cross-encoder/ms-marco-MiniLM-L-6-v2 | 22M | <100MB | ~5ms | Good |
| cross-encoder/ms-marco-MiniLM-L-12-v2 | 33M | <200MB | ~8ms | Better |
| BAAI/bge-reranker-v2-m3 | ~300M | ~1GB | ~350ms total batch | Best |

The MiniLM models are extremely efficient on Apple Silicon. For the document-aware approach (typically 50-75 pairs after grouping):
- MiniLM-L-6: ~250-375ms total
- MiniLM-L-12: ~400-600ms total
- BGE-reranker-v2-m3: ~500ms on M1 MacBook

All well within acceptable latency.

### Implementation

Simple. sentence-transformers provides `CrossEncoder` directly:

```python
from sentence_transformers import CrossEncoder
model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

# Document-aware reranking flow:
# 1. Retrieve broad candidate set
candidates = retriever.retrieve(query, k=100)

# 2. Group by document, take top 2-3 per document
from itertools import groupby
grouped = groupby(sorted(candidates, key=lambda c: c.doc_id), key=lambda c: c.doc_id)
selected = []
for doc_id, chunks in grouped:
    top_chunks = sorted(chunks, key=lambda c: c.score, reverse=True)[:3]
    selected.extend(top_chunks)

# 3. Rerank selected chunks
pairs = [(query, chunk.text) for chunk in selected]
scores = model.predict(pairs)

# 4. Return top-k by reranker score
reranked = sorted(zip(selected, scores), key=lambda x: x[1], reverse=True)[:k]
```

Integration points:
1. Add a `Reranker` protocol to `embeddings/base.py`
2. Implement `CrossEncoderReranker` with document-aware grouping logic
3. Insert reranking step after retrieval in `HybridRetriever.retrieve()` or `Library.query()`
4. Lazy-load the model (consistent with existing pattern)
5. `EmbeddingStorage` already tracks `doc_id` per chunk, so grouping is trivial

### Composability

Excellent. Reranking is "downstream" of retrieval and composes with everything:
- Query expansion → retrieval → **reranking** (standard pipeline; expansion broadens the initial candidate set, document-aware grouping preserves that diversity through reranking)
- Multi-stage → **reranking** (rerank final candidates; document-aware reranking partially subsumes multi-stage for smaller corpora)
- Late chunking → retrieval → **reranking** (better embeddings feed better candidates to reranker)

One caveat: HyDE-expanded or query-expanded text should **not** be passed to the reranker as the query. Use the original user query for reranking.

### Scale Behavior

- **20 docs**: Noticeable improvement. Document-aware grouping ensures all documents with any signal get reranked, which matters even with a small corpus.
- **1200+ docs**: More valuable. Larger candidate pools means more noise for the reranker to filter, and more documents competing for the final result set.
- **Latency scaling**: Linear in number of reranked pairs (not corpus size). With document-aware grouping, the number of pairs scales with the number of *documents* that have signal, not the raw chunk count.
- **Testing note**: Reranking should show measurable improvement even at 20 docs, making it good for early validation. Document-aware grouping is especially testable: compare top-10 results with and without grouping to see if source diversity improves.

---

## Comparative Summary

### Quality Impact (estimated, relative to our current hybrid baseline)

| Technique | Vocabulary Mismatch | General Quality | Confidence |
|-----------|-------------------|-----------------|------------|
| Query Expansion | **High** (direct target) | Moderate-High | High (well-studied) |
| HyDE | Moderate-High | Moderate | Medium (inconsistent across domains) |
| Multi-Stage Retrieval | Low (indirect) | Moderate-High at scale | Medium |
| Late Chunking | Low-Moderate (indirect) | Moderate | Medium (less studied at our scale) |
| Cross-Encoder Reranking | Moderate (indirect) | Moderate | High (well-studied, consistent) |

### Local Feasibility

| Technique | Runs Locally? | Hardware Requirements | Query-Time Cost |
|-----------|--------------|----------------------|-----------------|
| Query Expansion | Partially | 7B model (~16GB) or cloud LLM | 1-3s |
| HyDE | Partially | 7B model (~16GB) or cloud LLM | 1-8s |
| Multi-Stage Retrieval | **Yes, fully** | No additional models | Negligible |
| Late Chunking | **Yes, fully** | Same as current (nomic-embed) | **Zero** (index-time only) |
| Cross-Encoder Reranking | **Yes, fully** | ~100MB-1GB additional | 100-500ms |

### Implementation Effort

| Technique | Complexity | Key Changes |
|-----------|-----------|-------------|
| Query Expansion | Moderate | New pre-retrieval step, LLM integration |
| HyDE | Moderate | New pre-retrieval step, embedding swap |
| Multi-Stage Retrieval | Moderate-High | Document-level indices, two-pass flow |
| Late Chunking | Moderate | Embedding pipeline changes, migration |
| Cross-Encoder Reranking | **Low** | Post-retrieval step, new model |

### Scale Behavior Summary

| Technique | Benefit at 20 docs | Benefit at 1200+ docs | Scales with... |
|-----------|--------------------|-----------------------|----------------|
| Query Expansion | Subtle but present | Significant | Corpus vocabulary diversity |
| HyDE | Minimal/risky | Moderate | Embedding space density |
| Multi-Stage Retrieval | Negligible | Significant | Corpus size (chunk count) |
| Late Chunking | Measurable (if long docs) | Same per-doc benefit | Document length |
| Cross-Encoder Reranking | Measurable | More valuable | Candidate set noise |

---

## Recommendations

### Priority 1: Document-Aware Cross-Encoder Reranking

**Why first**: Lowest implementation effort, fully local, measurable improvement even at 20 docs, composes well with everything else we might add later. The MiniLM-L-6-v2 model adds ~250-375ms and <100MB memory. This is the highest-ROI retrieval improvement available.

**Approach**: Retrieve top-100 chunks via hybrid search, group by parent document, select top 2-3 chunks per document, rerank the selection via cross-encoder, return top-k. This provides both precision improvement (cross-encoder scoring) and source diversity (document-aware grouping) in a single step.

This document-aware approach also provides a lightweight form of multi-stage retrieval — deriving document-level signal from chunk retrieval rather than building a separate document-level index. This partially addresses the multi-stage retrieval benefit (Priority 3) at minimal additional cost.

### Priority 2: Query Expansion (cloud LLM path)

**Why second**: Directly targets the vocabulary mismatch pain point. Since we already have LiteLLM integration for the `ask` command, adding a query expansion step before retrieval reuses existing infrastructure. Start with a simple multi-query approach (generate 3 alternative phrasings, retrieve for each, fuse via RRF).

**Approach**: Add as an optional pre-retrieval step. Use the existing `LLMClient` to generate expansions. Make it toggleable (some queries don't need expansion). Consider a non-LLM fallback (synonym expansion for FTS5) for the local-only path.

**Synergy with Priority 1**: Query expansion broadens the initial candidate set with more diverse vocabulary. Document-aware reranking then preserves that diversity through the ranking process rather than collapsing it to a few dominant documents. The two techniques address different aspects of the same problem (vocabulary mismatch → missing relevant content).

### Priority 3: Full Multi-Stage Retrieval (after Zotero import)

**Why third**: Significant benefit at 1200+ docs but negligible at 20. Wait until after the Zotero corpus import to implement and evaluate. Document-aware reranking (Priority 1) provides a lighter-weight version of this for smaller corpora, but full multi-stage with document-level indices becomes worth the complexity at scale.

**Approach**: Compute document-level embeddings (average of chunk vectors) at index time. Add a coarse retrieval pass before chunk-level search. This extends beyond the document-aware reranking by maintaining a separate document-level index and searching all chunks from top documents (not just those that appeared in the initial top-100).

### Defer: Late Chunking

**Why defer**: The 60/40 document size split means we need a hybrid approach (late chunking for fitting documents, standard for overflow), adding complexity. No locally-viable embedding model with a larger context window (32K) offers a compelling quality improvement — Qwen3-0.6B provides 32K context but only 2 MTEB points over nomic at 4-10x slower inference. The models that are significantly better (Qwen3-8B, NV-Embed-v2) require dedicated GPU.

The improvement from late chunking is real but incremental, and it requires re-embedding the entire corpus. Evaluate after priorities 1-3 are in place and measured — it may be that the combination of reranking + query expansion eliminates the quality gaps that late chunking addresses.

**Reconsider when**: If evaluation shows that cross-section context loss is a significant source of retrieval errors (e.g., queries about methods consistently miss results sections that reference those methods), or if a higher-context embedding model becomes locally viable.

**If implemented**: Jina-v3 (65.5% MTEB, 8K context, 570M params) is the natural model choice — it was developed by the team that created late chunking, has the best-documented support for it, and provides a ~3 MTEB point quality improvement over nomic as a standalone benefit. A switch to Jina-v3 could be evaluated independently as a general retrieval quality upgrade.

### Defer: HyDE

**Why defer**: Inconsistent improvement across domains, shares the same vocabulary mismatch benefit as query expansion but with more failure modes and higher latency. Query expansion is the more reliable and more composable technique for our use case.

**Reconsider when**: If query expansion doesn't sufficiently address the vocabulary mismatch problem, HyDE could be tried as an alternative for the vector retrieval component specifically (while query expansion handles FTS5).

---

## What Would Change These Recommendations

- **Local-only becomes a hard requirement** → Drop query expansion from Priority 2 (or implement only the synonym/thesaurus-based FTS5 expansion). Reranking and multi-stage retrieval remain fully local.
- **Latency budget tightens significantly** → Cross-encoder reranking is still fast enough. Query expansion adds the most latency and could be made optional per-query.
- **Corpus grows beyond 10K documents** → Full multi-stage retrieval becomes essential, not just helpful. Document-aware reranking won't scale. Consider document clustering.
- **Evaluation shows cross-section context loss is a major error source** → Revisit late chunking. Evaluate Jina-v3 as a combined quality + late-chunking-readiness upgrade.
- **A locally-viable 32K+ embedding model with MTEB ≥ 68%** becomes available → Re-evaluate late chunking. Eliminating the overflow problem significantly reduces implementation complexity and makes late chunking a straightforward win.
