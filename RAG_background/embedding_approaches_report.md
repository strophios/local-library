# Text Embedding Approaches for Academic RAG Systems

A comprehensive analysis of chunking strategies and embedding models for a personal knowledge management system focused on academic documents.

**System Context**:
- ~1,400 academic documents in markdown format
- Target query latency: <500ms
- Hardware: 2021 MacBook Pro M1 Pro (16GB RAM assumed)
- API cost budget: ~$0.50–1.00 for full library embedding

---

## 1. Chunking Strategies

### 1.1 Strategy Overview

| Strategy | Description | Compute Cost | Context Preservation |
|----------|-------------|--------------|---------------------|
| Fixed-size | Split at token/character boundaries | Low | Poor |
| Recursive/hierarchical | Split at natural boundaries (paragraphs, then sentences) | Low-Medium | Good |
| Semantic | Split based on topic/meaning shifts | High | Excellent |
| Late chunking | Embed full document, then pool into chunks | Medium-High | Excellent |

### 1.2 Academic Document Considerations

Academic papers have distinct structural properties that inform chunking:

1. **Section boundaries matter**: Abstract, introduction, methods, results, discussion have different retrieval value. A chunk spanning methods→results loses coherence.

2. **Citation density**: Academic text is dense with inline citations. Chunks that split mid-citation context (e.g., "As shown by Smith et al. [1], the relationship between X and Y..." split after "between") degrade retrieval.

3. **Equation and figure references**: "See Equation 3" is meaningless without the equation. Consider treating equations as atomic units.

4. **Average document size**: A typical 15-page academic paper is ~10,000 tokens. With 512-token chunks and 10% overlap, that's roughly 22 chunks per document. For 1,400 documents: ~30,800 chunks.

### 1.3 Recommended Approach

**Start with**: `RecursiveCharacterTextSplitter` (LangChain) or equivalent hierarchical splitter.

**Parameters**:
- Chunk size: 512 tokens (balances context and specificity)
- Overlap: 50–100 tokens (10–20%)
- Separators priority: `["\n\n", "\n", ". ", " "]`

**For academic documents specifically**:
- Consider section-aware chunking that respects paper structure
- Keep abstracts as single chunks (typically 150–300 tokens)—high retrieval value
- If markdown has headers, use them as split points before falling back to paragraphs

### 1.4 Late Chunking: A Promising Alternative

[Late chunking](https://jina.ai/news/late-chunking-in-long-context-embedding-models/) inverts the traditional order: embed first, chunk second.

**How it works**:
1. Process the entire document through a long-context embedding model (e.g., 8192 tokens)
2. Apply mean pooling to token embeddings within chunk boundaries
3. Each chunk embedding captures full document context

**Advantages**:
- Preserves long-distance dependencies (e.g., a methods chunk "knows" about the abstract)
- No information loss at boundaries
- Same chunk boundaries can be used, but embeddings are contextually richer

**Limitations**:
- Requires long-context embedding model (Jina v2, nomic-embed-text)
- Documents exceeding context window need traditional chunking for overflow
- Slightly higher compute cost

**Verdict**: Strong candidate for academic documents where cross-section context matters. Implementation available via [Jina AI's late-chunking repository](https://github.com/jina-ai/late-chunking).

---

## 2. Embedding Models

### 2.1 API-Based Models

#### OpenAI text-embedding-3 Family

| Model | Dimensions | Cost (per 1M tokens) | Notes |
|-------|------------|---------------------|-------|
| text-embedding-3-small | 1536 | $0.02 | Good baseline, Matryoshka support |
| text-embedding-3-large | 3072 | $0.13 | Higher quality, can reduce dims |

**Matryoshka embeddings**: Both models support dimension reduction without retraining. A 3072-dim embedding can be truncated to 256, 512, or 1024 dims with graceful quality degradation. Useful for storage/latency optimization.

**Academic performance**: OpenAI embeddings outperform general-purpose models (E5, Instructor, MPNet) on scientific tasks but [underperform SPECTER2 on SciRepEval](https://allenai.org/blog/specter2-adapting-scientific-document-embeddings-to-multiple-fields-and-task-formats-c95686c06567).

#### Cohere Embed v3

| Variant | Dimensions | Cost (per 1M tokens) |
|---------|------------|---------------------|
| embed-english-v3.0 | 1024 | $0.10 |
| embed-multilingual-v3.0 | 1024 | $0.10 |

**Notable features**:
- Designed to work with Cohere Rerank (significant accuracy boost)
- Input type parameter (`search_document` vs `search_query`) improves asymmetric retrieval
- 100+ language support in multilingual variant

### 2.2 Local Models

#### General-Purpose Models

| Model | Dimensions | Context | M1 Performance | MTEB Score |
|-------|------------|---------|----------------|------------|
| all-MiniLM-L6-v2 | 384 | 256 | ~15ms/1K tokens | ~63% |
| E5-base-v2 | 768 | 512 | ~30ms/1K tokens | ~83% |
| BGE-M3 | 1024 | 8192 | ~50ms/1K tokens | ~85% |
| nomic-embed-text | 768 | 8192 | ~60ms/1K tokens | ~86% |

**M1 Mac Performance Reality**:
Based on [MLX benchmarking research](https://arxiv.org/abs/2510.18921), M1 Macs show:
- BERT-base inference: ~180ms (vs 23ms on CUDA GPU)
- Linear transformations: ~19ms (vs 3ms on CUDA)
- Approximately 6-8x slower than NVIDIA A10 for transformer operations

However, for embedding workloads:
- Batch processing amortizes overhead
- [Apple Neural Engine optimizations](https://machinelearning.apple.com/research/neural-engine-transformers) can provide up to 10x speedup for optimized models
- MPS (Metal Performance Shaders) backend improves PyTorch performance

**Practical expectation**: For a single query embedding, expect 50–150ms latency on M1 Pro with most models. Well within the 500ms budget.

#### Academic-Specific Models

##### SPECTER2

[SPECTER2](https://github.com/allenai/SPECTER2) is purpose-built for scientific documents:

**Architecture**:
- Base: SciBERT (trained on 1.14M scientific papers)
- Training: 6M citation triplets across 23 fields of study
- Task-specific adapters: Classification, Regression, Retrieval, Search

**Performance**:
- Outperforms OpenAI embeddings on [SciRepEval benchmark](https://aclanthology.org/2023.emnlp-main.338/) (24 scientific tasks)
- 2+ points absolute improvement over single-embedding SOTA
- Includes retrieval-specific adapter for paper→paper similarity

**Limitations**:
- 512 token context (requires chunking for full papers)
- Optimized for title+abstract; full-text retrieval less tested
- Document-level focus; may not be ideal for chunk retrieval

**Usage**:
```python
from transformers import AutoTokenizer, AutoModel
tokenizer = AutoTokenizer.from_pretrained('allenai/specter2')
model = AutoModel.from_pretrained('allenai/specter2')
# For retrieval tasks, add the proximity adapter
model.load_adapter("allenai/specter2_proximity", source="hf")
```

##### SciBERT

- 110M parameters, BERT architecture
- Trained on 1.14M papers from Semantic Scholar (3.1B tokens)
- Custom vocabulary for scientific terms
- Good as base encoder; less optimized for retrieval than SPECTER2

### 2.3 Model Selection Matrix

| Use Case | Best Choice | Rationale |
|----------|-------------|-----------|
| Maximum academic accuracy | SPECTER2 + proximity adapter | Domain-specific training, citation-aware |
| Best cost/quality balance | OpenAI text-embedding-3-small | Cheap, good quality, simple API |
| Zero ongoing cost | nomic-embed-text | Long context, strong accuracy, runs locally |
| Multilingual academic | BGE-M3 | Multi-vector retrieval, 100+ languages |
| Fastest local inference | all-MiniLM-L6-v2 | 5-8% accuracy tradeoff for 4x speed |

---

## 3. Chunk-Model Interactions

### 3.1 Model-Dependent Chunk Sizing

Different models have different "sweet spots" for chunk size:

| Model | Optimal Chunk Size | Rationale |
|-------|-------------------|-----------|
| all-MiniLM-L6-v2 | 128–256 tokens | 256 context limit; smaller chunks work well |
| E5/BGE | 256–512 tokens | Balanced; diminishing returns above 512 |
| nomic-embed-text | 512–1024 tokens | Long context; can leverage larger chunks |
| SPECTER2 | 256–512 tokens | 512 limit; title+abstract is ideal unit |

### 3.2 Query-Document Asymmetry

For asymmetric retrieval (short query → long document chunks):

1. **Instruction-tuned models** (E5, BGE): Prepend task instructions
   - Query: `"query: What is the relationship between X and Y?"`
   - Document: `"passage: [chunk text]"`

2. **Cohere**: Use `input_type` parameter
   - `search_query` for queries
   - `search_document` for corpus

3. **Late chunking**: Naturally handles asymmetry since chunk embeddings contain document context

### 3.3 Hybrid Retrieval

Combining dense (embedding) and sparse (BM25/keyword) retrieval often outperforms either alone:

**Implementation options**:
1. **Reciprocal Rank Fusion (RRF)**: Merge ranked lists from both retrievers
2. **Linear combination**: Weight dense and sparse scores
3. **BGE-M3 native**: Returns dense, sparse, and multi-vector representations

For academic documents, hybrid is particularly valuable:
- Sparse retrieval catches exact terminology (gene names, chemical formulas, acronyms)
- Dense retrieval catches semantic similarity (paraphrased concepts)

---

## 4. Practical Considerations

### 4.1 Vector Storage: sqlite-vec

[sqlite-vec](https://github.com/asg017/sqlite-vec) is the successor to sqlite-vss:

**Characteristics**:
- Pure C, no dependencies
- Brute-force search (no approximate nearest neighbors)
- Works anywhere SQLite runs

**Performance reality** ([based on benchmarks](https://marcobambini.substack.com/p/the-state-of-vector-search-in-sqlite)):
- Suitable for <100K vectors with low concurrency
- For 30K chunks (1,400 docs × ~22 chunks): well within capability
- Single-threaded writes; not suited for high-concurrency applications

**For this use case**: sqlite-vec is appropriate. The library size (~30K vectors) is small enough for brute-force search. Query latency will be dominated by embedding generation, not vector search.

### 4.2 Incremental Updates

When adding new documents:

1. **Embedding versioning**: Store model name/version with each embedding
2. **Batch updates**: Process new documents in batches to amortize API overhead
3. **Re-embedding triggers**: Define when full re-embedding is needed
   - Model upgrade: Yes
   - Chunk size change: Yes
   - Document edit: Re-embed affected document only

### 4.3 Cost Management

**Caching strategies**:
- Cache query embeddings for repeated queries
- For iterative development, cache document embeddings to avoid re-processing

**Dimension reduction**:
- OpenAI's Matryoshka embeddings allow storing at reduced dimensions
- Reduces storage and speeds up similarity computation
- 512-dim often retains 95%+ of 3072-dim quality

---

## 5. Cost Estimates for Full Library

### Assumptions
- 1,400 documents
- Average 10,000 tokens per document (15-page paper equivalent)
- Total: ~14M tokens for full corpus
- Chunking: 512 tokens → ~27,400 chunks (with overlap)

### Embedding Costs (One-Time)

| Model | Cost per 1M tokens | Full Library Cost | Notes |
|-------|-------------------|-------------------|-------|
| OpenAI text-embedding-3-small | $0.02 | **$0.28** | Best value API |
| OpenAI text-embedding-3-large | $0.13 | **$1.82** | Higher quality |
| Cohere embed-english-v3.0 | $0.10 | **$1.40** | Includes rerank synergy |
| Local models | $0 | **$0** | Compute time only |

### Local Compute Time Estimates (M1 Pro)

| Model | Est. Time per Doc | Full Library | Notes |
|-------|------------------|--------------|-------|
| all-MiniLM-L6-v2 | ~2s | ~45 min | Fastest |
| E5-base-v2 | ~5s | ~2 hours | Good balance |
| nomic-embed-text | ~8s | ~3 hours | Best local quality |
| SPECTER2 | ~6s | ~2.5 hours | Academic-optimized |

*Note: Times are rough estimates. Batch processing can improve throughput by 2-3x.*

### Storage Requirements

| Dimensions | Bytes per Vector | 27,400 Chunks | With Metadata |
|------------|------------------|---------------|---------------|
| 384 | 1,536 | ~42 MB | ~60 MB |
| 768 | 3,072 | ~84 MB | ~120 MB |
| 1024 | 4,096 | ~112 MB | ~150 MB |
| 3072 | 12,288 | ~337 MB | ~400 MB |

---

## 6. Recommendations

### 6.1 Easiest Path: OpenAI text-embedding-3-small

**Setup**:
- RecursiveCharacterTextSplitter: 512 tokens, 50 token overlap
- OpenAI text-embedding-3-small (1536 dims)
- sqlite-vec for storage

**Rationale**:
- Minimal infrastructure: API call + SQLite
- Cost: ~$0.28 for full library (well under budget)
- Quality: Strong general-purpose embeddings
- Latency: API call ~100ms + sqlite-vec search ~10ms = well under 500ms

**Tradeoffs**:
- Ongoing API dependency
- Not optimized for academic content
- No offline capability

**Implementation complexity**: Low

---

### 6.2 Best Quality: SPECTER2 + Late Chunking Hybrid

**Setup**:
- Late chunking with nomic-embed-text (8192 context) for full documents
- SPECTER2 for title+abstract embeddings (document-level retrieval)
- Hybrid retrieval: combine both for ranking
- BM25 sparse index for terminology matching

**Rationale**:
- SPECTER2 is purpose-built for academic paper retrieval
- Late chunking preserves cross-section context
- Hybrid approach handles both semantic and exact-match queries
- Fully local: no API costs, offline capable

**Tradeoffs**:
- Higher implementation complexity
- Longer initial embedding time (~4-5 hours)
- Two embedding models to maintain

**Implementation complexity**: High

---

### 6.3 Optimal ROI: nomic-embed-text with Section-Aware Chunking

**Setup**:
- Section-aware chunking: split on markdown headers, then recursive within sections
- Chunk size: 512 tokens, 64 token overlap
- nomic-embed-text-v1.5 (768 dims, 8192 context)
- sqlite-vec storage
- Optional: BM25 sparse index for hybrid retrieval

**Rationale**:
- **Zero ongoing cost**: One-time compute investment (~3 hours)
- **High quality**: 86%+ on MTEB, long context window
- **Academic-friendly**: 8192 context handles most paper sections in full
- **Offline capable**: No API dependency
- **Future-proof**: Can implement late chunking with same model

**Tradeoffs**:
- Initial compute time investment
- Not as specialized as SPECTER2 for academic content
- Requires local GPU/CPU resources

**Implementation complexity**: Medium

**Why this is optimal for your use case**:
1. Your budget ($0.50–1.00) suggests cost sensitivity; free is better
2. 1,400 documents is small enough for local processing
3. M1 Pro can handle nomic-embed-text with acceptable latency
4. Academic focus benefits from long-context model (full sections as context)
5. Section-aware chunking respects paper structure without complex parsing

---

## 7. Open Questions and Benchmarking Suggestions

### 7.1 Questions Requiring Empirical Testing

1. **SPECTER2 chunk retrieval performance**: SPECTER2 is trained on title+abstract. How does it perform on arbitrary paper chunks? Worth benchmarking against general-purpose models on your specific retrieval tasks.

2. **Late chunking overhead**: What's the actual latency difference on M1 Pro between traditional chunking and late chunking? The theoretical benefit may not justify the complexity for your library size.

3. **Optimal chunk size for your content**: The 256–512 recommendation is a starting point. Your academic domains may have different characteristics (equation-heavy? code-heavy?).

4. **Reranking value**: Does adding a reranker (Cohere, cross-encoder) improve results enough to justify the added latency and cost?

### 7.2 Suggested Benchmarking Protocol

1. **Create a test set**:
   - 20–30 queries you'd actually ask
   - For each, manually identify 3–5 relevant chunks/documents
   - Include both factual ("What dataset did paper X use?") and conceptual ("Papers about transformer optimization")

2. **Metrics to track**:
   - Recall@5 and Recall@10
   - Mean Reciprocal Rank (MRR)
   - Latency (embedding + search)

3. **Variables to test**:
   - Chunk size: 256 vs 512 vs 1024
   - Models: OpenAI-small vs nomic vs SPECTER2
   - Late chunking: on vs off
   - Hybrid: dense-only vs dense+sparse

4. **Minimum viable test**:
   - Embed 100 documents with each configuration
   - 10 test queries
   - Compare Recall@5

### 7.3 Architecture Decision Record

Before implementing, document:
- Which chunking strategy and why
- Which embedding model and why
- Expected costs (time and money)
- How re-embedding will be triggered
- How incremental updates work

---

## Sources

### Chunking and RAG Architecture
- [Jina AI: Late Chunking in Long-Context Embedding Models](https://jina.ai/news/late-chunking-in-long-context-embedding-models/)
- [GitHub: jina-ai/late-chunking](https://github.com/jina-ai/late-chunking)
- [Weaviate: Late Chunking - Balancing Precision and Cost](https://weaviate.io/blog/late-chunking)
- [DataCamp: Late Chunking for RAG Implementation](https://www.datacamp.com/tutorial/late-chunking)

### Embedding Models
- [Allen AI: SPECTER2 Blog Post](https://allenai.org/blog/specter2-adapting-scientific-document-embeddings-to-multiple-fields-and-task-formats-c95686c06567)
- [GitHub: allenai/SPECTER2](https://github.com/allenai/SPECTER2)
- [ACL Anthology: SciRepEval Benchmark](https://aclanthology.org/2023.emnlp-main.338/)
- [Hugging Face: SPECTER2](https://huggingface.co/allenai/specter2)
- [Hugging Face: BGE-M3](https://huggingface.co/BAAI/bge-m3)

### Apple Silicon Performance
- [arXiv: Benchmarking On-Device ML on Apple Silicon with MLX](https://arxiv.org/abs/2510.18921)
- [Apple ML Research: Deploying Transformers on Apple Neural Engine](https://machinelearning.apple.com/research/neural-engine-transformers)
- [GitHub: HuggingFaceGuidedTourForMac](https://github.com/domschl/HuggingFaceGuidedTourForMac)

### Vector Storage
- [GitHub: asg017/sqlite-vec](https://github.com/asg017/sqlite-vec)
- [Marco Bambini: The State of Vector Search in SQLite](https://marcobambini.substack.com/p/the-state-of-vector-search-in-sqlite)
- [Qdrant Vector Database Benchmarks](https://qdrant.tech/benchmarks/)

### Token Estimation
- [Token Count Estimation Guide](https://www.linkedin.com/pulse/how-estimate-text-length-a4-pages-from-token-count-albert-jeremy-n0iwc)
