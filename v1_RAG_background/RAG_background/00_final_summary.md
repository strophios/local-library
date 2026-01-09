# RAG System Implementation: Final Summary and Recommendations

## Executive Summary

This report synthesizes research across five components of a RAG (Retrieval-Augmented Generation) system for academic knowledge management:

1. **PDF to Markdown** - Converting PDFs to structured text
2. **Embeddings & Chunking** - Preparing text for semantic search
3. **Vector Storage** - Storing and querying embeddings efficiently
4. **LLM Querying** - Generating answers from retrieved context
5. **Citation Tooling** - Academic workflow integration

**Key constraints**:
- ~1400 Zotero items (growing)
- M1 Pro MacBook (local-first)
- Python preferred, Rust acceptable
- Self-sufficient with Zotero interoperability

---

## Critical Caveats (Read First)

Before diving into implementation paths, understand these cross-cutting concerns:

### Embedding Model Lock-in

**Once you embed your documents with a model, switching requires complete re-embedding.** For 1400 documents, this is 40-100 hours of processing. Choose your embedding model carefully:

- If you're uncertain, start with **all-mpnet-base-v2** (can be embedded quickly) to validate the pipeline
- Only invest in BGE-large embedding once you're confident in your chunking strategy
- Keep the original markdown files—they're your ability to re-embed later

### Marker Output Quality

Marker produces readable markdown, but **"readable" is not synonymous with "RAG-optimized."** Specifically:
- Headers/footers aren't always filtered perfectly
- Equation rendering can fail on complex notation
- Table preservation varies by document

Budget time for manual review of extraction quality on representative documents before committing to bulk processing.

### Zotero Database Access

**Never access `zotero.sqlite` while Zotero is running.** Either:
1. Close Zotero before running import scripts, OR
2. Copy the database file first: `cp ~/Zotero/zotero.sqlite ./zotero_copy.sqlite`

Accessing the locked database can corrupt Zotero's data.

### Backup Strategy

Before bulk processing, establish backups:
- **Source**: Original PDFs (ideally already backed up via Zotero sync)
- **Extracted markdown**: Version-controlled or backed up directory
- **Database**: Regular SQLite backups (`.backup` command or file copy)
- **Vectors**: If using LanceDB, it's directory-based—include in filesystem backups

Test restore from backup before relying on it.

---

## Two Implementation Paths

The previous "three paths" structure was misleading—Path 1 and Path 3 were really a single phased approach. Here are two genuinely distinct options:

### Path A: Phased Build (Recommended) — 4-6 weeks

Start simple, validate, then upgrade. This is the pragmatic approach for a first RAG system.

#### Phase 1: Prototype (Week 1-2)

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **PDF Extraction** | Marker | Good quality, single tool |
| **Embedding Model** | all-mpnet-base-v2 | Simple (no prefix), fast embedding |
| **Chunking** | LangChain RecursiveCharacterTextSplitter | Quick setup |
| **Vector Store** | Chroma | Easiest API |
| **LLM** | Ollama (llama3.1:8b) | Local, free |

**Goal**: Get end-to-end pipeline working. Run 50-100 test queries. Identify pain points.

**Code**:
```python
pip install marker-pdf sentence-transformers chromadb langchain-text-splitters

from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb

model = SentenceTransformer('all-mpnet-base-v2')
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
client = chromadb.PersistentClient(path="./chroma_db")
```

#### Phase 2: Production Quality (Week 3-4)

| Component | Upgrade To | Reason |
|-----------|------------|--------|
| **Embedding Model** | BGE-large-en-v1.5 | ~5-10% better retrieval quality |
| **Chunking** | Custom MarkdownChunker | Handles LaTeX, code blocks, preserves structure |
| **Vector Store** | sqlite-vss | Fits SQLite architecture, single-file simplicity |

**Re-embed all documents** once you're confident in the chunking strategy. This is a one-time cost.

**Important**: BGE requires query instruction prefixes:
```python
from FlagEmbedding import FlagModel

model = FlagModel(
    'BAAI/bge-large-en-v1.5',
    query_instruction_for_retrieval="Represent this sentence for searching relevant passages:",
    use_fp16=True
)

# Documents: embed WITHOUT prefix
doc_embeddings = model.encode(chunks)

# Queries: embed WITH instruction
query_embedding = model.encode_queries(["your search query"])
```

#### Phase 3: Integration (Week 5-6)

| Feature | Add |
|---------|-----|
| **Citation CLI** | typer-based command-line tool |
| **Neovim integration** | nvim-cmp source via Unix socket daemon |
| **LLM upgrade** | Claude 3.5 Haiku for production queries (~$0.25/1M tokens) |

**Defer**: Citation verification (needs validation on academic text), contradiction detection (requires reliable NLI).

#### Path A Tradeoffs

- ✅ Learn as you build
- ✅ Can stop at any phase with working system
- ✅ Avoids over-engineering
- ❌ Requires re-embedding when upgrading models
- ❌ 4-6 weeks before full functionality

---

### Path B: Maximum Quality — 10-14 weeks

For users who need the best possible retrieval quality and are willing to invest significant development time.

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **PDF Extraction** | Marker + GROBID | Best structure + academic metadata |
| **Embedding Model** | GTE-large-en-v1.5 | 8192 context, highest MTEB scores |
| **Chunking** | Custom hierarchical | Document → Section → Paragraph embeddings |
| **Vector Store** | LanceDB with HNSW | Best performance (~3ms queries) |
| **Search** | Hybrid (vector + BM25) + cross-encoder rerank | Maximum precision |
| **LLM** | Claude 3.5 Sonnet | Best reasoning |
| **Citation Tools** | Full stack (CLI + API + Neovim + MCP) | Complete integration |

**Additional features**:
- HyDE for conceptual queries
- Multi-query decomposition
- NLI-based citation verification (after validation)
- Conversation context with query rewriting

#### Path B Tradeoffs

- ✅ Best achievable quality
- ✅ Complete workflow integration
- ❌ GROBID requires Docker service
- ❌ Significant complexity and maintenance burden
- ❌ API costs (~$3/1M tokens for Sonnet)
- ❌ 10-14 weeks of development (realistic estimate, not the optimistic 6-8)

#### When to Choose Path B

Only if:
1. You've built RAG systems before and know what you need
2. You have specific quality requirements that Path A can't meet
3. You can maintain the additional infrastructure (GROBID, etc.)
4. The API costs are acceptable for your usage

---

## Integration Architecture

```
                         INGESTION FLOW
                         ══════════════
    ┌───────────┐      ┌──────────────┐      ┌─────────────┐
    │  Zotero   │─────►│    Marker    │─────►│  Chunker    │
    │ (PDFs)    │      │  Extraction  │      │             │
    └───────────┘      └──────────────┘      └──────┬──────┘
                              │                     │
                              ▼                     ▼
                       ┌─────────────┐      ┌─────────────┐
                       │   Failed    │      │  Embedder   │
                       │   Queue     │      │   (BGE)     │
                       │ (PyMuPDF)   │      └──────┬──────┘
                       └─────────────┘             │
                                                   ▼
                                           ┌─────────────┐
                                           │   Storage   │
                                           │  (SQLite +  │
                                           │   Vectors)  │
                                           └──────┬──────┘
                                                  │
                         QUERY FLOW               │
                         ══════════               │
    ┌───────────────────────────────────────────────────────────────┐
    │                        User Interfaces                         │
    ├───────────┬───────────┬───────────┬───────────┬───────────────┤
    │   CLI     │  Neovim   │ HTTP API  │MCP Server │   (Future)    │
    │  (typer)  │(nvim-cmp) │ (FastAPI) │ (agents)  │   Obsidian    │
    └─────┬─────┴─────┬─────┴─────┬─────┴─────┬─────┴───────────────┘
          │           │           │           │
          │      ┌────┴───────────┴───────────┘
          │      │    (HTTP / Unix Socket)
          ▼      ▼
    ┌─────────────────┐
    │    Services     │
    ├─────────────────┤
    │ • Query Handler │───► Embeds query, searches vectors, assembles context
    │ • Citation API  │───► Suggests citekeys for input text
    │ • Ingest API    │───► Add new documents on demand
    └────────┬────────┘
             │
    ┌────────┴────────┐
    │                 │
    ▼                 ▼
┌──────────┐   ┌──────────┐
│ Embedder │   │   LLM    │
│  (BGE)   │   │ (Claude/ │
│          │   │  Ollama) │
└────┬─────┘   └────┬─────┘
     │              │
     └──────┬───────┘
            ▼
    ┌─────────────────┐
    │     Storage     │
    ├─────────────────┤
    │ • SQLite        │ ◄── Metadata, chunks, sync state, content hashes
    │ • Vectors       │ ◄── sqlite-vss (embedded) or LanceDB (separate)
    │ • Files         │ ◄── PDFs, extracted markdown, notes
    └─────────────────┘
```

**Neovim Integration Detail**:
```
Neovim                          Citation Daemon
┌──────────────┐                ┌─────────────────────┐
│  nvim-cmp    │  Unix Socket   │  Background Process │
│  source      │◄──────────────►│  /tmp/cite.sock     │
│              │   JSON-RPC     │                     │
│  Trigger: [@ │                │  - Keeps BGE loaded │
└──────────────┘                │  - Memory-maps idx  │
                                └─────────────────────┘
```

---

## Bootstrap Strategy

### Processing Time Estimates

For 1400 academic PDFs on M1 Pro:

| Stage | Time | Notes |
|-------|------|-------|
| PDF extraction (Marker) | 40-80 hours | ~2-4 min/paper; varies by complexity |
| Embedding (BGE-large) | 1-2 hours | ~250ms/batch of 32 chunks |
| Total | 45-85 hours | Run in overnight batches |

**What drives the variance**:
- Scanned vs. native PDFs (scanned = 2-3x slower)
- Document length (20-page papers vs. 200-page dissertations)
- Thermal throttling under sustained load (M1 Pro will throttle after ~30 min continuous)

**Recommended duty cycle**: Process for 2-3 hours, rest for 30 minutes. Or run overnight batches of ~100 documents.

### Expected Failure Rate

Based on typical academic PDF diversity:

| Category | % of Corpus | Outcome |
|----------|-------------|---------|
| Native PDFs, standard layout | ~70% | Clean extraction |
| Native PDFs, complex layout | ~15% | Minor issues, usable |
| Scanned PDFs | ~10% | OCR quality varies |
| Problem documents | ~5% | Require manual review or PyMuPDF fallback |

For 1400 documents, expect ~70 to require some attention.

### Processing Pipeline

```python
import hashlib
from pathlib import Path

BATCH_SIZE = 50  # Smaller batches for thermal management
CHECKPOINT_FILE = Path("./processing_checkpoint.json")

def process_library(items: list[dict]):
    processed = load_checkpoint()
    failures = []

    for batch_num, batch in enumerate(chunked(items, BATCH_SIZE)):
        print(f"Batch {batch_num + 1}/{len(items) // BATCH_SIZE}")

        for item in batch:
            if item["id"] in processed:
                continue

            try:
                # Extract
                markdown = marker_extract(item["pdf_path"])
                content_hash = hashlib.sha256(markdown.encode()).hexdigest()[:16]

                # Chunk
                chunks = chunker.chunk_document(markdown, item["id"])

                # Embed (batch for efficiency)
                embeddings = embedder.encode([c.text for c in chunks])

                # Store
                store_document(item, markdown, content_hash, chunks, embeddings)
                processed.add(item["id"])

            except Exception as e:
                failures.append({"id": item["id"], "error": str(e)})
                log_failure(item["id"], e)

        # Checkpoint after each batch
        save_checkpoint(processed)
        print(f"  Completed. {len(failures)} failures so far.")

        # Thermal management pause
        if batch_num % 3 == 2:
            print("  Cooling pause (5 min)...")
            time.sleep(300)

    return failures
```

### Recovery from Interruption

If processing crashes at hour 40:

```python
# Resume from checkpoint
processed = load_checkpoint()
remaining = [item for item in all_items if item["id"] not in processed]
process_library(remaining)
```

---

## Evaluation Framework

### Test Set Design

Create **50-100 stratified queries** covering:

| Category | Example Queries | Count |
|----------|----------------|-------|
| **Factual lookup** | "What learning rate did BERT use?" | 15-20 |
| **Conceptual** | "How does attention relate to memory?" | 15-20 |
| **Comparative** | "How does GPT differ from BERT?" | 10-15 |
| **Methodology** | "What evaluation metrics are used for NER?" | 10-15 |
| **Adversarial** | Questions NOT answerable from corpus | 10-15 |

**Adversarial queries are critical** — they test whether the system correctly says "I don't know" vs. hallucinating.

### Quality Targets

For personal academic use, these thresholds are "good enough":

| Metric | Target | Notes |
|--------|--------|-------|
| Precision@5 | ≥ 60% | At least 3 of top 5 results relevant |
| Recall@10 | ≥ 70% | Find most relevant documents |
| MRR | ≥ 0.5 | Relevant doc typically in top 2 |
| "I don't know" accuracy | ≥ 80% | On adversarial queries |
| End-to-end latency | < 3 seconds | Query to answer |

If you're below these targets, investigate:
- Chunk size (too large = diluted relevance, too small = fragmented context)
- Embedding model mismatch (BGE with vs. without query prefix)
- Vector store configuration (HNSW parameters)

### Latency Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Embedding query | < 50ms | Single query embedding |
| Vector search | < 100ms | sqlite-vss at 100k vectors |
| LLM generation | < 2s | Claude Haiku |
| Total query | < 3s | User-acceptable for interactive use |
| Citation autocomplete | < 150ms | For smooth Neovim experience |

### Evaluation Code

```python
def evaluate_retrieval(test_set: list[dict], retriever, k: int = 10) -> dict:
    metrics = {"precision@k": [], "recall@k": [], "mrr": [], "idk_correct": []}

    for query in test_set:
        results = retriever.search(query["text"], k=k)
        retrieved_citekeys = [r.metadata["citekey"] for r in results]

        if query.get("unanswerable"):
            # Adversarial query — should return low confidence or empty
            is_correct = len(results) == 0 or results[0].score < 0.3
            metrics["idk_correct"].append(1 if is_correct else 0)
            continue

        relevant = set(query["relevant_docs"])
        retrieved = set(retrieved_citekeys[:k])

        precision = len(relevant & retrieved) / k
        recall = len(relevant & retrieved) / len(relevant) if relevant else 0

        # MRR
        mrr = 0
        for i, citekey in enumerate(retrieved_citekeys):
            if citekey in relevant:
                mrr = 1 / (i + 1)
                break

        metrics["precision@k"].append(precision)
        metrics["recall@k"].append(recall)
        metrics["mrr"].append(mrr)

    return {
        "precision@k": sum(metrics["precision@k"]) / len(metrics["precision@k"]),
        "recall@k": sum(metrics["recall@k"]) / len(metrics["recall@k"]),
        "mrr": sum(metrics["mrr"]) / len(metrics["mrr"]),
        "idk_accuracy": sum(metrics["idk_correct"]) / len(metrics["idk_correct"]) if metrics["idk_correct"] else None
    }
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| PDF extraction failures | Medium | Low | PyMuPDF fallback; flag for manual review |
| Retrieval quality below targets | Medium | High | Tune chunk size; evaluate early; add hybrid search |
| Citation verification unreliable | High | Medium | Treat as review aid only; validate on test set first |
| Embedding model obsolescence | Medium | Medium | Keep original markdown; budget for re-embedding |
| Dependency breaking changes | Medium | Medium | Pin versions; test updates in isolation |
| Zotero schema changes | Low | High | Abstract Zotero access; monitor Zotero releases |
| Processing time exceeds estimates | Medium | Low | Checkpoint frequently; process overnight |
| M1 thermal throttling | Medium | Low | Process in batches with cooling breaks |
| LLM API pricing changes | Low | Low | Can fall back to local models |
| False confidence from citations | High | High | Train user skepticism; always verify important claims |

**The highest-impact risk is false confidence**: The system can return authoritative-looking answers with correct citekeys that don't actually support the claims. Always verify important citations manually. Consider citation verification (once validated) as a way to flag suspicious outputs.

---

## Open Questions

### Deferred Decisions

1. **sqlite-vss vs LanceDB**: For Path A, default to sqlite-vss (simpler). Switch to LanceDB only if query latency becomes problematic at scale (>200k chunks).

2. **Section-level embeddings**: Defer until after basic system is working. Test whether coarse retrieval improves recall before investing in hierarchical indexing.

3. **Reference section handling**: Start by excluding reference sections from embeddings. They're typically noise for retrieval. Revisit if you find citation context is missing.

### Known Unknowns

1. **NLI on academic text**: Standard NLI models (trained on SNLI/MultiNLI) may perform poorly on academic language. Validate before trusting citation verification.

2. **Long-term maintenance**: How much ongoing effort to keep system running as dependencies update? Unknown until you've operated it for 6+ months.

3. **User interface fit**: Will CLI/Neovim integration actually fit your workflow, or will you need something different? Build MVP before investing in UI polish.

---

## Component Report Index

| Report | Focus |
|--------|-------|
| [01_pdf_to_markdown.md](./01_pdf_to_markdown.md) | PDF extraction tools, performance, fallback strategies |
| [02_embeddings_and_chunking.md](./02_embeddings_and_chunking.md) | Embedding models, chunking strategies, implementation |
| [03_vector_storage.md](./03_vector_storage.md) | Vector databases, hybrid search, schema design |
| [04_llm_querying.md](./04_llm_querying.md) | RAG pipeline, prompting, conversation handling |
| [05_citation_tooling.md](./05_citation_tooling.md) | Citation suggestion, verification, editor integration |

---

## Conclusion

A functional academic RAG system is achievable in 4-6 weeks with the phased approach (Path A):

**Phase 1** (prototype): Marker + all-mpnet + Chroma → validates pipeline
**Phase 2** (quality): BGE-large + sqlite-vss + custom chunker → production quality
**Phase 3** (integration): Citation CLI + Neovim + Claude Haiku → workflow integration

The primary risk is retrieval quality not meeting expectations. Mitigate by:
1. Building a proper test set (50-100 queries)
2. Evaluating early and often
3. Tuning chunk sizes based on results
4. Adding hybrid search if pure vector search underperforms

Start simple, measure, iterate. The system you need will become clearer as you use it.
