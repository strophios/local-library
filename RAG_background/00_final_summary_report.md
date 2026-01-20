# RAG System for Local-Library: Final Summary Report

## Executive Summary

This report consolidates research across five RAG pipeline components for the local-library personal knowledge management system. The recommendations balance quality, implementation effort, and alignment with project constraints: ~1,400 academic PDFs (growing), M1 Pro MacBook, portability valued, and self-sufficiency without Zotero dependency.

### Recommended Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           RAG SYSTEM ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────────┐    │
│  │   Academic   │     │    Marker    │     │   Structured Markdown    │    │
│  │    PDFs      │────►│  (primary)   │────►│   with heading hierarchy │    │
│  │  (~1,400+)   │     │              │     │                          │    │
│  └──────────────┘     └──────────────┘     └────────────┬─────────────┘    │
│                                                         │                   │
│                                                         ▼                   │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                     CHUNKING + EMBEDDING                              │  │
│  │  • Section-aware chunking (512 tokens, 10-20% overlap)               │  │
│  │  • nomic-embed-text (1024 dims, 8192 context, local, free)           │  │
│  │  • Prefixes: search_document: / search_query:                        │  │
│  └────────────────────────────────┬─────────────────────────────────────┘  │
│                                   │                                        │
│                                   ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                      STORAGE LAYER                                    │  │
│  │  • sqlite-vec for vectors (single-file, brute-force + SIMD)          │  │
│  │  • SQLite FTS5 for full-text (hybrid search via manual RRF)          │  │
│  │  • Main SQLite DB for metadata (CSL-JSON, citekeys)                  │  │
│  └────────────────────────────────┬─────────────────────────────────────┘  │
│                                   │                                        │
│                                   ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                      QUERY INTERFACE                                  │  │
│  │  • Custom ~200-line LLM wrapper (Claude, OpenAI, Ollama)             │  │
│  │  • Protocol-based retriever interface                                 │  │
│  │  • Token budget management per model                                  │  │
│  └────────────────────────────────┬─────────────────────────────────────┘  │
│                                   │                                        │
│                                   ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    CITATION TOOLING (MVP)                             │  │
│  │  • Citation suggestion via RAG                                        │  │
│  │  • Neovim autocomplete daemon (Unix socket, <200ms)                  │  │
│  │  • CLI + HTTP API + MCP server                                        │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Quick Reference: Final Recommendations

| Component | Recommendation | Rationale |
|-----------|---------------|-----------|
| **PDF Extraction** | Marker (primary) + olmOCR for OCR-heavy docs† | Best M1 support; selective olmOCR for scanned docs |
| **Chunking** | Section-aware, 512 tokens, 15% overlap | Respects academic structure, balances precision/context |
| **Embeddings** | nomic-embed-text (local)†† | Zero cost, 8K context, matches OpenAI small quality, M1-compatible |
| **Vector Storage** | sqlite-vec (v0.1.6) + FTS5 | Single-file portability, adequate for 100K vectors |
| **LLM Interface** | Custom wrapper + LiteLLM (~350 lines) | Full control over context assembly; LiteLLM for provider abstraction |
| **Citation Tools** | Suggestion + Triage MVP | Immediate value; triage-based verification sidesteps NLI accuracy concerns |

†See Section 1 for hybrid approach: Marker first, then selective olmOCR on remote GPU for scanned historical documents.

††**Critical**: nomic-embed-text requires prefixes: `search_query:` for queries, `search_document:` for documents. For dual-use (RAG + clustering), also use `clustering:` prefix for auto-tagging embeddings.

---

## Design Philosophy and Key Decisions

This section captures the reasoning behind the major architectural choices. These decisions reflect our priorities: **correctness over convenience**, **quality over speed**, and **simplicity where possible without sacrificing capability**.

### Why "Easiest" Often Won Over "Optimal ROI"

The individual component reports each identified three paths: Easiest, Best Quality, and Optimal ROI. In several cases, this summary recommends the "Easiest" option rather than "Optimal ROI":

| Component | Optimal ROI (per detailed report) | This Summary Recommends | Why |
|-----------|----------------------------------|------------------------|-----|
| PDF Extraction | Docling with Marker fallback | Marker (with selective olmOCR) | Docling has unresolved M1 dependency conflicts; Marker is proven |
| Vector Storage | LanceDB | sqlite-vec | Single-file portability matters more than native hybrid search at this scale |
| LLM Interface | LlamaIndex + LiteLLM | Custom + LiteLLM | LlamaIndex is heavyweight for a single-user system; custom gives full control |

**The reasoning**: "Optimal ROI" assumes a certain level of implementation effort is acceptable. For a personal knowledge management system, minimizing ongoing maintenance and maximizing portability often outweighs marginal quality gains. We can always migrate later if we hit limits.

### Key Tradeoffs We Accepted

1. **Brute-force vector search over ANN indexes**: sqlite-vec uses brute-force search, which is O(n) rather than O(log n). At ~100K vectors, this is still <100ms on M1 Pro with SIMD acceleration. We accept this ceiling (~250K vectors before degradation) in exchange for single-file simplicity.

2. **Manual hybrid search over native**: LanceDB offers native BM25 + vector search. We chose sqlite-vec + FTS5 with manual RRF (~30 lines of Python) to preserve single-file portability. If hybrid search becomes central to the workflow, LanceDB is a clean migration path.

3. **Local embeddings over API**: nomic-embed-text (62.28% MTEB) matches OpenAI text-embedding-3-small (62.3%) in quality. We chose local to avoid API dependency and ongoing costs, accepting that OpenAI text-embedding-3-large (64.6%) is ~2.3 percentage points better.

4. **Triage over automated verification**: NLI models achieve ~77-78% accuracy on academic text (vs ~90%+ on general text). Rather than defer verification entirely or invest weeks in validation, we reframed the problem: triage for human review instead of automated decisions. Same infrastructure, lower accuracy bar, immediate utility.

### What Would Change These Decisions

- **Scale beyond 250K vectors**: Migrate to LanceDB or wait for sqlite-vec ANN indexes
- **Hybrid search becomes critical**: Migrate to LanceDB for native BM25 + vector
- **Need automated verification workflows**: Invest in NLI validation (see citation tooling report Section 8.2)
- **Multi-user or server deployment**: Reconsider Qdrant or LanceDB for concurrent access
- **Heavy OCR workload ongoing**: Consider keeping olmOCR accessible for routine use, not just one-time batch

### Lessons from the Research Process

The research phase (18 agents across 6 phases) surfaced several insights worth preserving:

1. **Benchmark claims are contested**: olmOCR vs Marker benchmarking is disputed by both teams. Take published benchmarks as directional, not definitive.

2. **MTEB scores require context**: The "86% MTEB" figure for nomic-embed-text was actually the LoCo (long context) benchmark, not the overall MTEB average. Always verify what metric is being cited.

3. **Task-specific prefixes matter**: nomic-embed-text's quality depends on using the correct prefix (`search_query:`, `search_document:`, `clustering:`). This is easy to miss and silently degrades retrieval.

4. **NLI on academic text is hard**: The ~77-78% accuracy on SciNLI/MSciNLI (vs 90%+ on general NLI) is a genuine research-grade problem, not a tooling issue. Plan accordingly.

5. **"Deferred" doesn't mean "impossible"**: Citation verification and contradiction detection are deferred to triage-based approaches, not abandoned. The infrastructure supports upgrading to full verification if accuracy improves.

---

## 1. PDF Extraction

### The Problem

Converting academic PDFs to well-structured markdown suitable for semantic chunking. Quality requirements: accurate heading hierarchy, clean body text separation, reasonable equation/table handling.

### Evaluated Options

| Tool | Quality | M1 Support | Speed (M1) | License |
|------|---------|------------|------------|---------|
| **Marker** | Good (equations weak) | Excellent (native MPS) | ~4s/page | GPL-3.0 (code), CC-BY-NC-SA (models)* |
| **Docling** | Excellent (tables) | Good (dependency issues) | ~1.3s/page | MIT |
| **MinerU** | Very Good | Unstable | ~5s/page | AGPL-3.0 |
| **Nougat** | Excellent (equations) | Good (MPS via PyTorch) | ~40s/page | CC-BY-NC (models) |
| **GROBID** | Good (metadata) | Poor (Docker/ARM issues) | N/A | Apache-2.0 |

*Marker's model license includes revenue threshold waiver (<$5M revenue AND <$5M VC funding).

### Recommendation: Marker (Primary)

**Why Marker over Docling (the "Optimal ROI" choice)?**

The detailed PDF extraction report recommended Docling as "Optimal ROI" based on its speed (1.3s/page vs 4s/page) and excellent table handling. However, we chose Marker because:

1. **Docling has unresolved M1 dependency conflicts**: As of the research date, there's a version conflict between `mlx-vlm` (needs transformers ≥4.51.3) and `docling-ibm-models` (needs transformers <4.43.0). Until this is resolved, Docling is risky for M1 deployment.

2. **Marker is battle-tested**: More users, more edge cases discovered, more documentation for troubleshooting.

3. **Speed difference is acceptable**: 24 hours vs ~8 hours for initial processing is a one-time cost. For ongoing processing, the ~4s/page latency is fine for occasional new documents.

**Why Marker + olmOCR hybrid over pure Marker?**

olmOCR achieves better quality on scanned historical documents (82.3% on historical math scans), but at 20-100x slower speed and with NVIDIA GPU requirements. The hybrid approach captures the best of both:
- Marker handles the majority of documents well (digital-born PDFs, high-quality scans)
- olmOCR is reserved for the problematic subset where quality justifies the hassle

**Why Marker:**
- Best-documented M1 Pro support with native MPS acceleration
- Straightforward installation: `pip install marker-pdf`
- ~24 hours for full corpus (1,400 PDFs × ~15 pages avg × ~4s/page)
- Active development, good community support
- Reasonable quality for most academic content

**Known Limitations:**
- Equation handling is weaker than Nougat
- Scanned historical documents may have lower OCR quality
- Marker's maintainers claim 56% win rate against olmOCR (olmOCR claims 61% — benchmarks are contested)

**Quality Validation Checklist** (run on 20 random PDFs before full batch):
- [ ] Markdown structure preserved (headings render correctly)
- [ ] Multi-column layouts handled (text in reading order)
- [ ] Tables extracted reasonably
- [ ] No obvious truncation or corruption

### Hybrid Approach: Marker + Selective olmOCR

For libraries with significant scanned/OCR-heavy content AND access to remote NVIDIA GPUs:

**Strategy:**
1. **First pass (Marker)**: Process all PDFs locally (~24 hours on M1)
2. **Quality triage**: Identify problematic documents (poor OCR, mangled tables)
3. **Selective olmOCR**: Process only the problematic subset on remote GPU (requires 20GB+ VRAM)
4. **Ongoing**: Use Marker locally for new documents

**When olmOCR is worth the hassle:**
- Scanned historical documents (pre-1990s academic papers)
- Handwritten/typewritten content
- Complex multi-column layouts from older journals
- Heavy mathematical notation in scanned documents

**Speed difference:** Marker is 20-100x faster than olmOCR. This makes processing entire libraries with olmOCR impractical, but selective use on difficult documents is viable.

**Deferred Option:** Once Docling's M1 dependency issues are verified resolved, it could become primary (faster processing, better tables).

### Implementation Notes

```python
# Basic Marker usage
from marker.converters.pdf import PdfConverter

converter = PdfConverter()
result = converter(pdf_path)
markdown_text = result.markdown
```

For batch processing, use Marker's CLI with progress tracking:
```bash
marker_single /path/to/pdf --output_dir ./extracted/
```

---

## 2. Embeddings

### The Problem

Convert extracted markdown into vector representations. Requirements: <500ms query latency, support re-embedding, academic domain awareness.

### Evaluated Options

| Model | Type | Dims | Context | Cost | MTEB (approx) |
|-------|------|------|---------|------|---------------|
| OpenAI text-embedding-3-small | API | 1536 | 8191 | $0.02/1M tokens | ~62% |
| OpenAI text-embedding-3-large | API | 3072 | 8191 | $0.13/1M tokens | ~64% |
| **nomic-embed-text** | Local | 1024 | 8192 | Free | ~62% |
| SPECTER2 | Local | 768 | 512 | Free | Academic-optimized |
| BGE-base-en-v1.5 | Local | 768 | 512 | Free | ~63% |
| all-MiniLM-L6-v2 | Local | 384 | 256 | Free | ~56% |

### Recommendation: nomic-embed-text (Local)

**Why nomic-embed-text over OpenAI APIs?**

The core question is: does the ~2.3 percentage point advantage of OpenAI text-embedding-3-large (64.6% vs 62.28%) justify the API dependency and ongoing costs?

Our answer: **No, for this use case.**

1. **The quality difference is marginal**: 62.28% vs 62.3% (OpenAI small) is effectively a tie. Even vs OpenAI large (64.6%), the ~2% difference is unlikely to be perceptible in retrieval quality for a personal library.

2. **API dependency has hidden costs**: Rate limits, outages, privacy concerns, and the inability to work offline. For a personal knowledge system that should work indefinitely, local embedding is more robust.

3. **Re-embedding flexibility**: If a better local model emerges, re-embedding is free. With OpenAI, every re-embedding costs money.

4. **The dual-use case favors nomic**: nomic-embed-text's explicit support for `clustering:` prefix makes it uniquely suited for systems that need both RAG and auto-tagging.

**Why not SPECTER2 (academic-optimized)?**

SPECTER2 is trained specifically on academic papers and outperforms general models on scientific similarity tasks. However:
- 512-token context window truncates most paper sections
- Optimized for title+abstract retrieval, not arbitrary chunk retrieval
- Adding a second embedding model increases complexity without clear benefit

For a personal library where full-section context matters, nomic-embed-text's 8192-token context is more valuable than SPECTER2's domain optimization.

**Why nomic-embed-text:**
- **Zero ongoing cost**: ~$0 vs ~$0.28-$1.82 for OpenAI on full library
- **8192 token context**: Handles full paper sections without truncation
- **Equivalent quality**: 62.28% on MTEB — matches OpenAI text-embedding-3-small (62.3%)
- **Offline capable**: No API dependency, full privacy
- **M1 compatible**: Runs well via sentence-transformers or Ollama
- **Task-specific prefixes**: Supports separate prefixes for RAG, clustering, and classification

**MTEB Score Clarification**: Earlier reports cited ~86% for nomic-embed-text. This was incorrect — likely the LoCo (long context) benchmark (85.53%) or task-specific scores. The overall MTEB average is 62.28%, which matches OpenAI small. The recommendation stands because nomic-embed-text is free and local.

**Critical Implementation Detail:**
```python
# nomic-embed-text requires prefixes!
query_text = "search_query: " + user_query
doc_text = "search_document: " + chunk_content

# For clustering/auto-tagging (if using dual embeddings):
cluster_text = "clustering: " + chunk_content
```

Missing these prefixes significantly degrades retrieval quality.

### Dual Embedding Strategy (for RAG + Auto-Tagging)

If your system needs both RAG retrieval AND semantic clustering (e.g., for automated document tagging), maintain two embedding sets:

1. **RAG embeddings** (`search_document:` prefix): For query-document matching
2. **Clustering embeddings** (`clustering:` prefix): For document-document similarity with high linear separability

**Storage overhead**: ~6KB per document (~185MB total for 1,400 docs with chunks). Negligible.

**When to use dual embeddings:**
- You need both RAG and auto-tagging/clustering
- Quality matters more than storage efficiency
- You're using nomic-embed-text (which explicitly supports task prefixes)

### Chunking Strategy

**Section-aware chunking with RecursiveCharacterTextSplitter:**
- **Target size**: 512 tokens
- **Overlap**: 15% (~75 tokens)
- **Split hierarchy**: Headings → paragraphs → sentences
- **Preserve structure**: Keep markdown headers as chunk metadata

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,
    chunk_overlap=75,
    separators=["\n## ", "\n### ", "\n\n", "\n", " "],
    length_function=lambda x: len(x.split()),  # token approximation
)
```

### Cost Estimate

For ~1,400 documents averaging ~10K tokens each = ~14M tokens total:
- **nomic-embed-text (local)**: $0, ~2-3 hours compute
- **OpenAI small**: ~$0.28
- **OpenAI large**: ~$1.82

### Why Not SPECTER2?

SPECTER2 is optimized for scientific documents but has limitations:
- 512-token context (truncates most paper sections)
- Trained on title+abstract similarity, not arbitrary chunk retrieval
- Adding it as a secondary system increases complexity without clear benefit

For a personal library, nomic-embed-text's longer context and simpler architecture wins.

---

## 3. Vector Storage

### The Problem

Store embeddings efficiently, retrieve via similarity search with <500ms latency, support metadata filtering.

### Evaluated Options

| Solution | Single File | ANN Index | Hybrid Search | Metadata Filtering | Production Ready |
|----------|-------------|-----------|---------------|-------------------|------------------|
| **sqlite-vec** | Yes | No (brute-force) | Manual (FTS5) | Yes (partition keys) | Yes |
| LanceDB | No (directory) | Yes | Native | Yes | Yes |
| DuckDB VSS | Yes | Yes (HNSW) | Native | Limited (post-hoc) | **No (experimental)** |
| ChromaDB | No (directory) | Yes | External | Yes | Yes |

### Recommendation: sqlite-vec + FTS5

**Why sqlite-vec over LanceDB (the "Optimal ROI" choice)?**

The detailed report recommended LanceDB as "Optimal ROI" due to native hybrid search and better scale headroom. We chose sqlite-vec because:

1. **Single-file portability is genuinely valuable**: For a personal knowledge system, `cp library.db backup.db` is simpler than `rsync -av ./lance_dir/ backup/`. It's not a large difference, but simplicity compounds over time.

2. **Native hybrid search isn't essential**: The RRF implementation for combining sqlite-vec + FTS5 is ~30 lines of Python. LanceDB's native hybrid search is cleaner, but not worth changing storage architecture for.

3. **Scale headroom isn't needed yet**: sqlite-vec handles ~100K-250K vectors comfortably. Our projected ~30K chunks (1,400 docs × ~22 chunks) is well within limits. We can migrate if we hit the ceiling.

4. **SQLite is universal**: Every tool understands SQLite. Debugging, inspection, and integration are trivial. LanceDB's Arrow-based format is less universally supported.

**The tradeoff we're making**: We accept brute-force O(n) search and manual hybrid search implementation in exchange for maximum portability and ecosystem familiarity.

**Why sqlite-vec:**
- **Single-file portability**: `cp library.db backup.db` — done
- **Adequate performance**: Brute-force search is fast enough for ~100K vectors on M1 Pro (<4ms with quantization)
- **Production stable**: v0.1.6 (November 2024), backed by Mozilla Builders + Fly.io/Turso/SQLite Cloud
- **SQLite ecosystem**: Combine with FTS5, JSON functions, existing tooling
- **SIMD acceleration**: Native NEON support on M1
- **No data loss issues**: No sqlite-vec-specific bugs reported; standard SQLite durability applies

**Why NOT DuckDB VSS:**
Despite offering HNSW indexes in a single file, DuckDB VSS is explicitly experimental:
- Persistence issues risk data loss on unexpected shutdown
- HNSW index must fit entirely in RAM
- Metadata filtering only works post-hoc (not during search)
- Not recommended for production use

**Why NOT LanceDB:**
LanceDB is excellent but overkill here:
- Directory-based storage (acceptable, but sqlite-vec is simpler)
- Native hybrid search is nice, but FTS5 + manual RRF is straightforward
- Better suited for larger scale (500K+ vectors) or multi-user scenarios

**Complexity Assessment**: The difference between sqlite-vec and LanceDB is often overstated. LanceDB's API is clean and the directory-vs-single-file distinction is minor (`rsync` handles directories fine). If you need native hybrid search or expect to exceed 100K vectors, LanceDB is a viable alternative — see detailed report for comparison.

### Schema Design

```sql
-- Vector storage
CREATE VIRTUAL TABLE doc_vectors USING vec0(
    chunk_id TEXT PRIMARY KEY,
    embedding float[1024],
    year INTEGER PARTITION KEY,      -- Fast pre-filtering
    doc_type TEXT,                    -- Metadata column
    +doc_id TEXT,                     -- Auxiliary (for joins)
    +citekey TEXT,
    +section TEXT
);

-- Full-text search (for hybrid)
CREATE VIRTUAL TABLE doc_fts USING fts5(
    chunk_id,
    content,
    title,
    abstract
);
```

### Hybrid Search Implementation

```python
from collections import defaultdict

def hybrid_search(query: str, query_embedding: list, alpha: float = 0.7, k: int = 10):
    """
    Combine vector similarity and BM25 via Reciprocal Rank Fusion.
    alpha: weight for vector results (0.7 = 70% vector, 30% BM25)
    """
    # Vector search
    vector_results = db.execute("""
        SELECT chunk_id, distance
        FROM doc_vectors
        WHERE embedding MATCH ?
        ORDER BY distance
        LIMIT ?
    """, [query_embedding, k * 3]).fetchall()

    # BM25 search
    bm25_results = db.execute("""
        SELECT chunk_id, rank
        FROM doc_fts
        WHERE doc_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, [query, k * 3]).fetchall()

    # Reciprocal Rank Fusion
    scores = defaultdict(float)
    rrf_k = 60  # Standard RRF constant

    for rank, (chunk_id, _) in enumerate(vector_results, start=1):
        scores[chunk_id] += alpha / (rrf_k + rank)

    for rank, (chunk_id, _) in enumerate(bm25_results, start=1):
        scores[chunk_id] += (1 - alpha) / (rrf_k + rank)

    # Return top-k by fused score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [chunk_id for chunk_id, _ in ranked[:k]]
```

### Scale Ceiling

sqlite-vec handles ~100K-250K vectors well with brute-force search. Beyond that:
- Consider migrating to LanceDB
- Or wait for sqlite-vec ANN indexes (on roadmap, no timeline)

**Mitigation**: Maintain Parquet exports of embeddings for easy migration.

---

## 4. LLM Query Interface

### The Problem

Provide retrieved context to LLMs for augmented generation. Must work with Claude, OpenAI, and Ollama without lock-in.

### Evaluated Options

| Approach | Dependencies | Flexibility | Maintenance |
|----------|--------------|-------------|-------------|
| **Custom wrapper** | 3-4 | Full control | You own it |
| LiteLLM | 20+ core, 50+ transitive | 100+ providers | External dependency |
| LangChain | Heavy | High abstraction | Rapid API churn |
| LlamaIndex | Medium | RAG-focused | Good for retrieval |

### Recommendation: Custom RAGInterface + LiteLLM (Path 3 from detailed report)

**Note**: The detailed LLM query interface report covers three architectural paths. This is **Path 3 (Optimal ROI)** — a custom wrapper for context assembly/citation handling with LiteLLM for provider abstraction.

**Architecture split:**
- **Custom code (~200-300 lines)**: Context assembly, token budget management, citation formatting
- **LiteLLM**: Provider abstraction (handles auth, response parsing, error handling for 3 providers)

**Why this split:**
- **Context assembly is your code**: This is core to RAG quality and should be custom
- **Provider abstraction is commodity**: LiteLLM handles the tedious parts well for 3 providers
- **Full control where it matters**: You own retrieval logic and context assembly
- **Minimal effort where it doesn't**: Provider differences are abstracted away

**Alternative (pure custom)**: If you prefer zero external dependencies, ~350 lines handles all three providers directly. See implementation sketch below.

### Implementation Sketch

```python
from dataclasses import dataclass
from typing import Protocol, Iterator
from anthropic import Anthropic
from openai import OpenAI
import ollama

class LLMProvider(Protocol):
    def complete(self, messages: list[dict], **kwargs) -> str: ...
    def stream(self, messages: list[dict], **kwargs) -> Iterator[str]: ...
    def count_tokens(self, messages: list[dict]) -> int: ...

@dataclass
class ClaudeProvider:
    client: Anthropic = None
    model: str = "claude-sonnet-4-5-20250514"

    def __post_init__(self):
        self.client = self.client or Anthropic()

    def complete(self, messages: list[dict], **kwargs) -> str:
        # Extract system message (Claude uses separate parameter)
        system = next((m["content"] for m in messages if m["role"] == "system"), None)
        user_messages = [m for m in messages if m["role"] != "system"]

        response = self.client.messages.create(
            model=self.model,
            system=system,
            messages=user_messages,
            max_tokens=kwargs.get("max_tokens", 4096),
        )
        return response.content[0].text

    def count_tokens(self, messages: list[dict]) -> int:
        # Use Anthropic's official API (not tiktoken!)
        return self.client.messages.count_tokens(
            model=self.model,
            messages=messages
        ).input_tokens

@dataclass
class OpenAIProvider:
    client: OpenAI = None
    model: str = "gpt-4o"

    def __post_init__(self):
        self.client = self.client or OpenAI()

    def complete(self, messages: list[dict], **kwargs) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs
        )
        return response.choices[0].message.content

    def count_tokens(self, messages: list[dict]) -> int:
        import tiktoken
        enc = tiktoken.encoding_for_model(self.model)
        return sum(len(enc.encode(m["content"])) for m in messages)

@dataclass
class OllamaProvider:
    model: str = "llama3"

    def complete(self, messages: list[dict], **kwargs) -> str:
        response = ollama.chat(model=self.model, messages=messages)
        return response["message"]["content"]

    def count_tokens(self, messages: list[dict]) -> int:
        # Approximate: ~4 chars per token for most models
        return sum(len(m["content"]) // 4 for m in messages)
```

### Context Assembly Pattern

```python
def assemble_context(
    chunks: list[dict],
    query: str,
    max_tokens: int,
    provider: LLMProvider
) -> list[dict]:
    """
    Assemble RAG context within token budget.
    """
    system = """You are a research assistant with access to the user's academic library.
Answer questions based on the provided context. Cite sources using citekeys like [@smith2020].
If the context doesn't contain relevant information, say so."""

    context_parts = []
    running_tokens = provider.count_tokens([
        {"role": "system", "content": system},
        {"role": "user", "content": query}
    ])

    for chunk in chunks:
        chunk_text = f"[{chunk['citekey']}] {chunk['content']}"
        chunk_tokens = len(chunk_text.split()) * 1.3  # Rough estimate

        if running_tokens + chunk_tokens > max_tokens * 0.8:  # Leave room for response
            break

        context_parts.append(chunk_text)
        running_tokens += chunk_tokens

    context = "\n\n---\n\n".join(context_parts)

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}
    ]
```

---

## 5. Citation Tooling

### The Problem

Academic workflow integration: suggest citations for claims, real-time autocomplete in Neovim, optionally verify citations and detect contradictions.

### Feature Assessment

| Feature | Complexity | Feasibility | Recommendation |
|---------|------------|-------------|----------------|
| **Citation Suggestion** | Low | Straightforward | **Build (MVP)** |
| **Triage-based "Verification"** | Low | Straightforward | **Build (MVP)** |
| **Triage-based "Contradiction"** | Low | Straightforward | **Build (MVP)** |
| **Neovim Autocomplete** | Medium | Straightforward | **Build (MVP)** |
| **CLI / HTTP API** | Low | Straightforward | **Build (MVP)** |
| **MCP Server** | Low-Medium | Straightforward* | **Build (MVP)** |
| **Full Automated Verification** | High | Needs Validation | **Defer** |
| **Full Contradiction Detection** | Very High | Research-Grade | **Defer** |

*MCP SDK is young with API churn; expect some maintenance.

**Key insight**: Triage-based verification/contradiction uses the same infrastructure as citation suggestion with different ranking. See Section 4.6 of the detailed citation tooling report.

### Recommendation: Suggestion + Triage MVP

**Why focus on Suggestion + Triage:**
1. **Citation suggestion solves 80% of the use case** ("I need a citation, what do I have?")
2. **Triage-based verification gets you the other 80%** — without the accuracy burden
3. **Immediate value**: Works on day one with standard RAG infrastructure
4. **Low risk**: No ML model accuracy concerns
5. **~1-2 weeks to functional system**

### The Triage Reframing (Key Insight)

The research phase revealed that NLI models achieve only ~77-78% accuracy on academic text (vs ~90%+ on general text), which initially suggested deferring verification/contradiction entirely. But this framing assumes the goal is **automated decision-making**.

The insight: if we reframe these features as **search space reducers for human review** rather than **automated verifiers**, the accuracy bar drops dramatically.

| Original Framing | Triage Framing |
|------------------|----------------|
| "Does this paper support this claim?" | "What papers are most related to this claim?" |
| "What contradicts this?" | "What's related but doesn't strongly support this?" |
| Requirement: High precision (>90%) | Requirement: Better than random (>50%) |
| Failure: False confidence in wrong answer | Failure: Human reviews a few irrelevant candidates |
| Risk: User trusts incorrect "SUPPORTED" label | Risk: User spends 30 extra seconds reviewing |

**Why this works**: 77-78% NLI accuracy is insufficient for "trust this label" but excellent for "here are the top candidates, ranked by likelihood." The infrastructure is identical — same embeddings, same NLI model (optional), same ranking logic. Only the UX and expectations change.

**The deeper insight**: Many "AI features" that seem blocked by accuracy concerns become viable when reframed as human-assistance rather than automation. The question isn't "can the system make the decision?" but "does the system make the human faster?" A 77% accurate ranker that surfaces 10 candidates for human review is useful; a 77% accurate automated verifier is dangerous.

**Triage commands** (same infrastructure as citation suggestion):
```bash
# "What in my library is related to this claim?"
cite-triage related "attention mechanisms improve sequence modeling"

# "What might not support this claim?"
cite-triage contradictions "transformers are always better than RNNs"
```

### Why NOT Full Verification/Contradiction (Yet)

1. **NLI accuracy problem**: Standard models achieve ~90% on general text but only ~77-78% on academic text
2. **Validation required**: You'd need to build a test set (50-100 labeled pairs) before knowing if it works
3. **2-4 weeks to validate**, with significant risk of "not good enough"

**If you still want full verification later**: See the detailed citation tooling report (Section 8.2) for the validation approach. Only pursue if you need automated workflows ("reject commits with unsupported citations").

### MVP Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                     CITATION MVP STACK                          │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                  CitationSuggester                         │ │
│  │  • Takes: claim text                                       │ │
│  │  • Returns: ranked citekeys + excerpts + scores           │ │
│  │  • Thresholds: strict (0.65), default (0.45), broad (0.30)│ │
│  └───────────────────────────────────────────────────────────┘ │
│                              │                                  │
│           ┌──────────────────┼──────────────────┐              │
│           ▼                  ▼                  ▼              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│  │     CLI     │    │  HTTP API   │    │ MCP Server  │        │
│  │  (typer)    │    │  (FastAPI)  │    │             │        │
│  └─────────────┘    └─────────────┘    └─────────────┘        │
│                              │                                  │
│                              ▼                                  │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │              Neovim Integration                            │ │
│  │  • Unix socket daemon (/tmp/citation-daemon.sock)         │ │
│  │  • nvim-cmp source (Lua)                                  │ │
│  │  • Trigger: [@                                            │ │
│  │  • Target: <200ms p50 latency                             │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### Latency Budget (Neovim Autocomplete)

| Component | Target | Notes |
|-----------|--------|-------|
| Socket overhead | ~10ms | Unix socket, not HTTP |
| Query embedding | ~30-50ms | Model warm in memory |
| Vector search | ~20-50ms | sqlite-vec brute-force |
| Response formatting | ~10ms | JSON serialization |
| **Total** | **70-120ms** | Well under 200ms target |

---

## 6. Integration Considerations

### Data Flow

```
PDF → Marker → Markdown → Chunker → Embeddings → sqlite-vec
                  │                      │
                  └──────────────────────┴──► SQLite (metadata, FTS5)
                                                    │
                                                    ▼
                                              Query Interface
                                                    │
                              ┌──────────────────────┼────────────────────┐
                              ▼                      ▼                    ▼
                         RAG Queries          Citation Tools         Neovim
```

### Metadata Schema (CSL-JSON Integration)

Ensure consistent citekey linking across all components:

```python
@dataclass
class Document:
    id: str                    # UUID
    citekey: str               # BetterBibTeX-style: smith2020attention
    zotero_key: str | None     # For Zotero interop
    csl_json: dict             # Full bibliographic metadata
    content_hash: str          # For change detection

@dataclass
class Chunk:
    id: str                    # UUID
    doc_id: str                # FK to Document
    citekey: str               # Denormalized for fast access
    content: str               # Chunk text
    embedding: list[float]     # 1024-dim vector
    section: str | None        # Heading/section name
    page: int | None           # Source page (if available)
```

### CLAUDE.md Update Required

Your project's CLAUDE.md references sqlite-vss, which is deprecated. Update to reference sqlite-vec:

```markdown
# Before
- **Vector storage**: sqlite-vss, or pgvector if moving to Postgres

# After
- **Vector storage**: sqlite-vec (successor to sqlite-vss)
```

---

## 7. Implementation Roadmap

### Phase 1: Foundation (2-3 weeks)

1. **PDF Extraction Pipeline**
   - Install Marker, test on sample PDFs
   - Build batch processor with progress tracking
   - Store extracted markdown alongside PDFs

2. **Embedding Pipeline**
   - Set up nomic-embed-text via sentence-transformers
   - Implement section-aware chunking
   - Create sqlite-vec schema
   - Process full corpus (~3 hours)

3. **Basic RAG Query**
   - Implement hybrid search (vector + FTS5)
   - Build custom LLM wrapper
   - Test with simple queries

### Phase 2: Citation MVP (1-2 weeks)

4. **Citation Suggester**
   - Implement core suggestion logic
   - Calibrate thresholds on 20 sample queries
   - Build CLI interface

5. **Neovim Integration**
   - Create Unix socket daemon
   - Write nvim-cmp source (Lua)
   - Test latency, optimize

6. **API Surface**
   - FastAPI endpoints
   - MCP server (if needed for Claude integration)

### Phase 3: Polish & Validation (1-2 weeks)

7. **Quality Validation**
   - Build test query set
   - Measure retrieval quality (Recall@5, Recall@10)
   - Tune chunking/embedding parameters if needed

8. **Integration Testing**
   - End-to-end workflow testing
   - Edge case handling (corrupted PDFs, Unicode issues)
   - Documentation

### Total: ~5-7 weeks to functional system

### Pending: Evaluation Framework

> **TODO**: A detailed evaluation framework needs to be researched and created before implementation begins. The v1 research (`v1_backport_content.md`) contains useful starter content including:
> - Test set design (50-100 stratified queries)
> - Quality targets (Precision@5 ≥60%, MRR ≥0.5, "I don't know" accuracy ≥80%)
> - Latency targets per operation
> - Evaluation code
>
> This framework should be adapted to our specific architecture (nomic-embed-text, sqlite-vec, hybrid search) and validated against actual library content before finalizing implementation decisions.

---

## 8. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Marker quality insufficient | Low | Medium | Nougat fallback for math-heavy PDFs |
| nomic-embed-text quality issues | Low | High | Easy to swap to OpenAI API if needed |
| sqlite-vec scale ceiling | Medium | Medium | Maintain Parquet exports, monitor growth |
| NLI verification not viable | High | Low | MVP focused on suggestion (verification deferred) |
| M1 performance surprises | Medium | Low | All recommendations validated on Apple Silicon |

---

## 9. Open Questions for Future Work

1. **Equation extraction**: If math-heavy papers matter, evaluate Nougat or olmOCR (via MLX) as secondary processors
2. **Multi-language support**: Some academic papers are non-English; nomic-embed-text handles this but may need validation
3. **Incremental re-embedding**: When embedding models improve, what's the re-processing strategy?
4. **SPECTER2 for metadata**: Consider using Semantic Scholar's SPECTER2 embeddings for papers with DOIs (query-time enrichment)
5. **LLM-based NLI**: If verification becomes important, test whether prompting Claude outperforms dedicated NLI models on academic text

---

## Appendix A: Component Report References

Detailed analysis for each component is available in:

- `RAG_background/pdf_extraction_tools_report.md`
- `RAG_background/embedding_approaches_report.md`
- `RAG_background/vector_storage_report.md`
- `RAG_background/llm_query_interface_report.md`
- `RAG_background/citation_tooling_report.md`

---

## Appendix B: Quick Start Commands

```bash
# 1. Install core dependencies
pip install marker-pdf sentence-transformers sqlite-vec anthropic openai ollama

# 2. Extract a PDF
marker_single paper.pdf --output_dir ./extracted/

# 3. Test embedding model
python -c "
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('nomic-ai/nomic-embed-text-v1.5', trust_remote_code=True)
emb = model.encode('search_document: test')
print(f'Embedding dims: {len(emb)}')
"

# 4. Initialize sqlite-vec
python -c "
import sqlite3
import sqlite_vec
db = sqlite3.connect('library.db')
db.enable_load_extension(True)
sqlite_vec.load(db)
print('sqlite-vec loaded successfully')
"
```

---

## Appendix C: Useful Links

- [Marker GitHub](https://github.com/VikParuchuri/marker)
- [nomic-embed-text on HuggingFace](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5)
- [sqlite-vec Documentation](https://alexgarcia.xyz/sqlite-vec/)
- [SQLite FTS5](https://www.sqlite.org/fts5.html)
- [Anthropic API Docs](https://docs.anthropic.com/)
- [nvim-cmp](https://github.com/hrsh7th/nvim-cmp)
