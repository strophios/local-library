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
| **PDF Extraction** | Marker (primary) | Best M1 support, proven quality, ~24hrs for full corpus |
| **Chunking** | Section-aware, 512 tokens, 15% overlap | Respects academic structure, balances precision/context |
| **Embeddings** | nomic-embed-text (local)† | Zero cost, 8K context, high quality, M1-compatible |
| **Vector Storage** | sqlite-vec + FTS5 | Single-file portability, adequate for 100K vectors |
| **LLM Interface** | Custom wrapper (~200 lines) | Minimal dependencies, full control, 3 providers only |
| **Citation Tools** | Suggestion + Autocomplete MVP | Immediate value, verification deferred pending NLI validation |

†**Critical**: nomic-embed-text requires prefixes: `search_query:` for queries, `search_document:` for documents.

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

**Why Marker:**
- Best-documented M1 Pro support with native MPS acceleration
- Straightforward installation: `pip install marker-pdf`
- ~24 hours for full corpus (1,400 PDFs × ~15 pages avg × ~4s/page)
- Active development, good community support
- Reasonable quality for most academic content

**Known Limitation:** Equation handling is weaker than Nougat. For math-heavy papers, consider:
- Nougat as a secondary processor for flagged documents (note: ~40s/page, 10x slower)
- Or accept imperfect equation rendering if RAG is the primary use case

**Quality Validation Checklist** (run on 20 random PDFs before full batch):
- [ ] Markdown structure preserved (headings render correctly)
- [ ] Multi-column layouts handled (text in reading order)
- [ ] Tables extracted reasonably
- [ ] No obvious truncation or corruption

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

**Why nomic-embed-text:**
- **Zero ongoing cost**: ~$0 vs ~$0.28-$1.82 for OpenAI on full library
- **8192 token context**: Handles full paper sections without truncation
- **High quality**: Competitive with OpenAI on general benchmarks
- **Offline capable**: No API dependency, full privacy
- **M1 compatible**: Runs well via sentence-transformers or Ollama

**Critical Implementation Detail:**
```python
# nomic-embed-text requires prefixes!
query_text = "search_query: " + user_query
doc_text = "search_document: " + chunk_content
```

Missing these prefixes significantly degrades retrieval quality.

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

**Why sqlite-vec:**
- **Single-file portability**: `cp library.db backup.db` — done
- **Adequate performance**: Brute-force search is fast enough for ~100K vectors on M1 Pro (<100ms)
- **Production stable**: v0.1.0+ marked stable, transactional safety
- **SQLite ecosystem**: Combine with FTS5, JSON functions, existing tooling
- **SIMD acceleration**: Native NEON support on M1

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

### Recommendation: Custom Wrapper (~200 lines)

**Why custom wrapper over LiteLLM:**
- **Minimal dependencies**: anthropic, openai, ollama-python vs 50+ transitive deps
- **Full control**: Direct access to provider features (Claude's prompt caching, etc.)
- **No abstraction lag**: Provider SDKs get features first
- **Debuggable**: Your code only, no third-party internals
- **Appropriate scope**: LiteLLM is for 10+ providers; you have 3

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
| **Neovim Autocomplete** | Medium | Straightforward | **Build (MVP)** |
| **CLI / HTTP API** | Low | Straightforward | **Build (MVP)** |
| **MCP Server** | Low-Medium | Straightforward* | **Build (MVP)** |
| **Citation Verification** | High | Needs Validation | **Defer** |
| **Contradiction Detection** | Very High | Research-Grade | **Defer** |

*MCP SDK is young with API churn; expect some maintenance.

### Recommendation: Focus on Suggestion/Autocomplete MVP

**Why focus on MVP:**
1. **Citation suggestion solves 80% of the use case** ("I need a citation, what do I have?")
2. **Immediate value**: Works on day one with standard RAG infrastructure
3. **Low risk**: No ML model accuracy concerns
4. **~1-2 weeks to functional system**

**Why defer verification/contradiction:**
1. **NLI accuracy problem**: Standard models achieve ~90% on general text but only ~77-78% on academic text (SciNLI/MSciNLI benchmarks)
2. **High false positive rate**: Academic hedging, scope qualifications, and implicit assumptions confuse NLI models
3. **Validation required**: You'd need to build a test set (50-100 labeled pairs) and empirically measure accuracy before knowing if it's usable
4. **2-4 weeks just to validate**, with significant risk of "not good enough"

### What Would Make Verification/Contradiction Viable?

If you want these features later:

1. **Build validation set first**: 100 claim-citation pairs from your own papers, manually labeled
2. **Benchmark baseline**: Run cross-encoder/nli-deberta-v3-base, measure accuracy
3. **Decision gate**: If accuracy < 75%, either:
   - Fine-tune on SciNLI/MSciNLI (adds weeks)
   - Accept as "review aid" with explicit low-confidence warnings
   - Abandon the feature
4. **Consider LLM-based NLI**: Prompting Claude/GPT to classify entailment may outperform dedicated NLI models on academic text (untested hypothesis worth exploring)

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
