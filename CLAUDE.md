# CLAUDE.md

Last verified: 2026-03-06

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a personal knowledge management system that ingests diverse digital documents (web articles, PDFs, etc.), extracts content, manages bibliographic metadata, provides ML-based auto-tagging, and serves as a local RAG database. The system is self-sufficient but designed for interoperability with Zotero.

## Architectural Decisions

### System Philosophy
- **Self-sufficient with Zotero interoperability**: The system functions completely independently but can exchange data with Zotero
- Zotero is treated as a peer/data source, not as a substrate to extend
- The system owns what Zotero doesn't do well: web content ingestion, text extraction, embeddings, auto-tagging, and markdown note management
- Zotero remains valuable for academic PDF management via its browser connector and citation metadata

### Why Not a Zotero Plugin?
ML features (embeddings, RAG, auto-tagging) require Python infrastructure that cannot run in Zotero's JavaScript plugin environment. Once external Python infrastructure is necessary, it makes sense for that system to own all functionality beyond Zotero's strengths.

## Core Data Model

Each document record contains:

- **Identity**: UUID, citekey (BetterBibTeX-style), optional Zotero item key, DOI/URL/ISBN
- **Bibliographic metadata**: CSL-JSON blob (Zotero-compatible, citation-processor-ready) plus indexed fields
- **Content**: Path to original file, extracted plain text, content hash
- **Embeddings**: Vector embeddings for full doc or chunks (sqlite-vec, successor to deprecated sqlite-vss)
- **Tags**: Manual and auto-generated with source flag; confidence scores for auto-tags
- **Notes**: Path to markdown file with YAML frontmatter linking back to record

## Zotero Interoperability

### Reading from Zotero
- Direct SQLite access to `zotero.sqlite` for read operations
- Note: Zotero locks the database while running; copy file first if Zotero is active
- Query items, attachments, tags, and notes from stable schema

### Writing to Zotero
- **NEVER write to SQLite directly** (risk of corruption/sync conflicts)
- Use local API (HTTP server on port 23119) for tags and item modifications
- Alternatively use export/import via Zotero's translation architecture for bulk operations

### Sync Strategy
- Periodic scan for new/modified items in Zotero database
- Import PDFs and metadata for new items
- Push auto-generated tags back via local API
- Notes managed primarily in external system (bidirectional sync adds complexity)

## Build Approach

Development follows a **pipeline-first, layer-complete** approach documented in `build_philosophy.md`. The key insight: pipeline stages (vertical data flow) and architectural layers (horizontal concerns) are orthogonal. Build along the pipeline for rapid feedback; implement layers completely when touched.

### Current Status: M1-M7 + M3b Complete (Record Storage + Extraction + Metadata + Zotero Reader + Text Extraction + Embeddings + Retrieval + RAG Query)

Milestones M1 (record storage), M2 (PDF extraction), M3a (metadata validation), M3b (text-based metadata extraction), M4 (Zotero read-only access), M5 (embedding pipeline), M6 (retrieval), and M7 (RAG query interface) are implemented. The system can:
- Ingest local PDF files via CLI (`local-library add <path>`)
- Accept explicit CSL-JSON metadata (`--metadata <file>`)
- Extract text to markdown via Marker
- Validate metadata against CSL-JSON schema and generate citekeys
- **Extract metadata from PDF text** when no explicit metadata provided
- Set documents to NEEDS_REVIEW status when extraction confidence is low
- Optionally use LLM fallback (via LiteLLM) for low-confidence extractions
- **Chunk extracted text and compute vector embeddings** via nomic-embed-text-v1.5
- **Track embedding status** (PENDING/CURRENT/STALE) across the document lifecycle
- **Search documents** via hybrid (vector + FTS5 with RRF fusion), vector-only, or FTS-only modes
- **Ask natural language questions** and get RAG-generated answers with source citations (streaming or blocking)
- Store documents in content-addressable storage with SQLite metadata
- Query, list, search, and delete documents via CLI
- Read items, attachments, and metadata from Zotero library (via database or BetterBibTeX JSON export)

**Implemented:**
- PDF ingestion from local filesystem
- Text extraction via Marker with quality validation and markdown cleanup (HTML coercion, dehyphenation, paragraph reflow)
- CSL-JSON metadata validation with BetterBibTeX-style citekey generation
- Indexed field extraction (title, authors, issued_date)
- **Text-based metadata extraction**: heuristic extractors for title, authors, date, and document type with confidence scoring
- **NEEDS_REVIEW workflow**: documents with low-confidence extraction flagged for human review
- **Optional LLM fallback**: LLMClient injection with LiteLLM backend for re-extracting low-confidence fields
- **Embedding pipeline**: section-aware markdown chunking (~512 tokens, ~15% overlap), nomic-embed-text-v1.5 via sentence-transformers (768-dim vectors), sqlite-vec storage with FTS5
- **Embedding status tracking**: PENDING → CURRENT on embed, CURRENT → STALE on re-extraction, cascade deletion on document delete
- **Embed-on-add**: documents automatically embedded during `add` and `zotero import` (use `--skip-embed` to defer)
- **CLI `embed` command**: manual embedding/re-embedding with `--pending`, `--all`, `--force`, `--dry-run` options
- **Graceful degradation**: library functions without sqlite-vec for document storage; embedding operations fail clearly
- **Retrieval system**: VectorRetriever (cosine similarity), FTSRetriever (BM25 via FTS5), HybridRetriever (RRF fusion with configurable weights), **cross-encoder reranking** via RerankedRetriever decorator (enabled by default)
- **Retriever protocol**: Protocol-based extensibility; `Library.get_retriever()` factory method wires up dependencies; `Reranker` protocol for pluggable reranking
- **Cross-encoder reranking**: Document-aware CrossEncoderReranker groups candidates by document, limits chunks per document, scores via cross-encoder/ms-marco-MiniLM-L-12-v2, applies sigmoid normalization. RerankedRetriever wraps any Retriever with broadened candidate pool + reranking
- **CLI `search` command**: hybrid/vector/fts modes, document-scoped search (--doc), JSON output (--json), configurable result limit (--limit), reranking on by default (--no-rerank to disable)
- **Retrieval evaluation framework**: IR metrics (Precision@k, Recall@k, MRR, NDCG@k), seed query set (test_queries.json), automated evaluation harness, reranker benchmark script
- **LLM abstraction layer**: LLMClient protocol with LiteLLMClient implementation; provider-agnostic LLM access with error mapping to ErrorCode hierarchy
- **RAG query interface**: RAGInterface orchestrates context assembly, prompt construction, and LLM generation; RAGStream supports streaming with token accumulation; pre-LLM gate skips API call when no context retrieved
- **CLI `ask` command**: streaming answers with Rich Live display, --no-stream, --json, --model, --mode, --doc, --limit, --no-rerank options; source citations with citekey attribution
- SQLite storage with content-addressable file layout (schema v3)
- CLI interface (add, list, show, delete, open, update, review, embed, search, ask commands)
- @citekey identifier support with fuzzy matching suggestions
- Pagination support (--limit, --all flags on list command)
- Zotero read-only access: ZoteroReader facade with database and JSON export backends, BetterBibTeX citekey mapping, attachment resolution, collection and library filtering
- **Batch import from Zotero**: `zotero import` command with library/collection filtering, dry-run mode, progress tracking, and continue-on-error (defaults to personal library)

**Next milestones:** Post-M7 evaluation pass (end-to-end RAG quality assessment, pipeline improvements, full Zotero corpus import, evaluation query expansion to 50-100). See `build_plan.md` § "Post-M7: Pipeline Evaluation and Corpus Scaling" for rationale.

**Deferred to later phases:** M3b (metadata extraction is functionally complete, but does not yet hit benchmarks; that has been deferred), M3c (API metadata enrichment), web content ingestion, Zotero sync, citation tooling, auto-tagging, note management, Neovim plugin. See `future_roadmap.md` for full details.

### Architectural Layers

Five horizontal concerns cut across the system:

1. **Storage**: SQLite schema, CRUD operations, sqlite-vec, FTS5
2. **Ingestion**: Content acquisition, extraction (Marker), metadata handling
3. **Embeddings + Retrieval**: Chunking, nomic-embed-text, similarity operations, FTS5 search, hybrid retrieval (RRF fusion), cross-encoder reranking
4. **LLM + RAG**: LLMClient protocol, LiteLLM provider abstraction, context assembly, prompt construction, answer generation
5. **Interface**: CLI, (later) daemon, Neovim plugin, HTTP API

## Key Libraries and Tools

- **Web extraction**: trafilatura, readability-lxml
- **PDF extraction**: Marker (primary), olmOCR (for scanned historical documents on remote GPU)
- **Embeddings**: nomic-embed-text-v1.5 (local, 768 dims, 8192 context) via sentence-transformers
- **Reranking**: cross-encoder/ms-marco-MiniLM-L-12-v2 via sentence-transformers CrossEncoder
- **Metadata**: CrossRef API, GROBID (for academic PDFs), Open Graph tags (for web)
- **Vector storage**: sqlite-vec (v0.1.6+), SQLite FTS5 for hybrid search
- **LLM interface**: Custom RAGInterface + LiteLLM for provider abstraction
- **Citations**: citeproc-py against CSL-JSON

## RAG System Design Decisions

Comprehensive research on the RAG pipeline is documented in `RAG_background/`. The final summary (`00_final_summary_report.md`) is the authoritative reference. Key decisions:

### Embedding Model: nomic-embed-text-v1.5
- **MTEB score**: 62.28% (matches OpenAI text-embedding-3-small)
- **Critical**: Requires task-specific prefixes:
  - `search_query:` for user queries
  - `search_document:` for document chunks (RAG)
  - `clustering:` for auto-tagging embeddings (if using dual embeddings)
- For dual-use (RAG + auto-tagging), maintain two embedding sets per document

### Vector Storage: sqlite-vec + FTS5
- Single-file portability prioritized over native hybrid search (LanceDB)
- Brute-force search is adequate for ~100K vectors; scale ceiling ~250K
- Hybrid search implemented via RRF fusion combining sqlite-vec + FTS5 (see `embeddings/retrieval.py`)

### PDF Extraction: Marker + Selective olmOCR
- Marker for primary processing (proven M1 support, ~4s/page)
- olmOCR on remote NVIDIA GPU for scanned historical documents only
- Benchmark claims between tools are contested; Marker is the conservative choice

### Reranking: Document-Aware Cross-Encoder
- **Model**: cross-encoder/ms-marco-MiniLM-L-12-v2 (~50 MB, ~33M params)
- Selected via benchmark against 5 candidates; best balance of NDCG@10 improvement and latency
- **Document-aware grouping**: Prevents single document from monopolizing top results; limits chunks per document before scoring
- **Decorator pattern**: RerankedRetriever wraps any Retriever, broadens candidate pool (default 100 or 3x k), reranks to final k
- **Enabled by default**: `Library.get_retriever(rerank=True)` is the default; CLI `--no-rerank` flag to disable
- **Lazy loading**: Model loaded on first rerank call, not at Library init
- **Sigmoid normalization**: Raw cross-encoder logits mapped to [0, 1] for interpretable scores
- See `docs/benchmarks/2026-03-06-reranker-model-selection.md` for model comparison data

### Citation Tooling: Triage over Automated Verification
- NLI models achieve only ~77-78% accuracy on academic text (vs ~90%+ general)
- Reframe verification as "triage for human review" rather than "automated decision"
- Same infrastructure, lower accuracy bar, immediate utility

### Evaluation Framework (Initial)
A retrieval evaluation framework has been implemented in `tests/eval/`. Current state:
- **IR metrics**: `retrieval_eval.py` provides Precision@k, Recall@k, MRR, NDCG@k with unit tests (`test_retrieval_metrics.py`)
- **Seed query set**: `test_queries.json` contains 12 labeled test queries across 5 categories (factual, conceptual, comparative, methodology, adversarial)
- **Comparative harness**: Runs all three retriever modes (vector, FTS, hybrid) with per-category breakdowns
- **Reranker benchmark**: `reranker_benchmark.py` evaluates cross-encoder models across retriever modes with NDCG@10 and latency metrics; results in `reranker_results.json`
- **Planned expansion (post-M7)**: Query set expansion to 50-100 queries, quality targets, latency benchmarks, and end-to-end RAG evaluation are planned for after M7 — see `build_plan.md` § "Post-M7: Pipeline Evaluation and Corpus Scaling" for rationale and sequencing

### What Would Change These Decisions
- Scale beyond 250K vectors → migrate to LanceDB
- Need native hybrid search → migrate to LanceDB
- Need automated verification workflows → invest in NLI validation (see citation report Section 8.2)

## Design Principles

- Use CSL-JSON for bibliographic metadata (standard, Zotero-compatible)
- Generate citekeys by default for all documents
- Markdown notes with YAML frontmatter for portability and interoperability
- System must function fully without Zotero installed
- Duplicate storage (e.g., PDFs in both systems) is acceptable for independence
- Prioritize easy ingestion: adding a blog post should require only a URL

## Python Tooling

**Always** use uv for package management, ruff for linting, and ty for type checking. Invoke the relevant skill via `astral:uv`, `astral:ruff`, or `astral:ty` when needed.

## Commands

All commands accepting document IDs support both UUID (full or partial) and @citekey identifiers (e.g., `@Smith2023`).

- `uv run local-library add <path>` - Add a PDF to the library (embeds by default; use `--skip-embed` to defer)
- `uv run local-library add <path> --metadata <csl-json-file>` - Add with bibliographic metadata
- `uv run local-library add <path> --llm-extract` - Add with LLM-enhanced PDF extraction (requires GEMINI_API_KEY)
- `uv run local-library list` - List all documents (use `--limit N` for pagination, `--all` for unlimited)
- `uv run local-library show <id>` - Show document details
- `uv run local-library delete <id>` - Delete a document (cascades to embeddings)
- `uv run local-library open <id>` - Open extracted markdown in editor (use `--pdf` for PDF, `--both` for both)
- `uv run local-library update <id>` - Edit document metadata in editor with validation loop
- `uv run local-library review <id>` - Combined open + update workflow for NEEDS_REVIEW documents
- `uv run local-library embed <id>` - Embed a specific document
- `uv run local-library embed --pending` - Embed all PENDING/STALE documents
- `uv run local-library embed --all --force` - Re-embed all READY documents
- `uv run local-library search "<query>"` - Search documents (hybrid mode by default; use `--mode vector` or `--mode fts`)
- `uv run local-library search "<query>" --doc @Author2023` - Search within a specific document
- `uv run local-library search "<query>" --limit 20 --json` - Get more results as JSON
- `uv run local-library search "<query>" --no-rerank` - Search without cross-encoder reranking
- `uv run local-library ask "<question>"` - Ask a question and get a RAG-generated answer (streams by default, reranked by default)
- `uv run local-library ask "<question>" --model anthropic/claude-3-haiku` - Use a specific LLM model
- `uv run local-library ask "<question>" --doc @Author2023` - Scope to a specific document
- `uv run local-library ask "<question>" --json` - Get structured JSON output (implies --no-stream)
- `uv run local-library ask "<question>" --no-stream` - Wait for full answer before displaying
- `uv run local-library ask "<question>" --no-rerank` - Disable cross-encoder reranking
- `uv run local-library zotero import` - Batch import from Zotero (embeds by default; use `--skip-embed` to defer; `--library NAME`, `--collection NAME`, `--dry-run`)
- `uv run local-library zotero collections` - List Zotero collections (personal library by default; use `--library NAME` or `--all-libraries`)
- `uv run local-library zotero libraries` - List available Zotero libraries (personal and group)
- `uv run pytest` - Run tests
- `uv run ruff check` - Lint code
- `uv run ruff format` - Format code

## Package Structure

```
src/local_library/
├── __init__.py          # Package root
├── config.py            # XDG-compliant path configuration
├── core/                # Domain: models, storage, orchestration
│   ├── models.py        # Document, EmbeddingStatus, result types (Functional Core)
│   ├── errors.py        # Exception hierarchy with ErrorCode (Functional Core)
│   ├── storage.py       # SQLite CRUD operations, schema v3 (Imperative Shell)
│   ├── library.py       # Library orchestrator (Imperative Shell)
│   └── vec_extension.py # sqlite-vec extension loading and availability checking
├── embeddings/          # Domain: chunking, embedding computation, vector storage, retrieval, reranking
│   ├── base.py          # Chunk, ChunkEmbedding, SearchResult dataclasses; Chunker, Embedder, Retriever, Reranker protocols
│   ├── chunking.py      # MarkdownChunker (section-aware markdown splitting)
│   ├── nomic.py         # NomicEmbedder (nomic-embed-text-v1.5 via sentence-transformers)
│   ├── reranking.py     # CrossEncoderReranker, RerankedRetriever, _group_by_document, _normalize_scores
│   ├── retrieval.py     # VectorRetriever, FTSRetriever, HybridRetriever, _rrf_fuse
│   └── storage.py       # EmbeddingStorage (sqlite-vec CRUD, FTS5 search, status functions)
├── llm/                 # Domain: LLM provider abstraction
│   ├── base.py          # LLMClient protocol (Functional Core)
│   └── litellm_client.py # LiteLLMClient implementation (Imperative Shell)
├── rag/                 # Domain: RAG query pipeline
│   └── interface.py     # RAGInterface, RAGStream, assemble_context, build_messages
├── ingestion/           # Domain: content acquisition and extraction
│   ├── base.py          # Protocols: ContentAcquirer, ContentExtractor
│   ├── file.py          # FileAcquirer implementation
│   ├── pdf.py           # PdfExtractor (Marker wrapper)
│   ├── metadata.py      # MetadataHandler (CSL-JSON validation, citekey generation)
│   ├── text_extraction.py  # TextMetadataExtractor (heuristic + LLM metadata extraction)
│   ├── markdown_cleanup.py # Post-processing: HTML coercion, dehyphenation, paragraph reflow (Functional Core)
│   └── zotero.py        # ZoteroReader facade (database + JSON backends, citekey mapping)
└── cli/                 # CLI interface (Typer/Rich)
    ├── main.py          # Entry point, command registration
    ├── add.py           # Add command (--skip-embed flag)
    ├── ask.py           # Ask command (RAG queries with streaming, --no-rerank)
    ├── list.py          # List command (pagination with --limit/--all, embed status column)
    ├── show.py          # Show command (@citekey support)
    ├── delete.py        # Delete command (@citekey support)
    ├── embed.py         # Embed command (--pending, --all, --force, --dry-run)
    ├── search.py        # Search command (--limit, --mode, --doc, --json, --no-rerank)
    ├── open.py          # Open command (markdown/PDF viewing)
    ├── update.py        # Update command (editor-based metadata editing)
    ├── review.py        # Review command (combined open + update)
    ├── utils.py         # Shared utilities (identifier resolution, fuzzy matching)
    └── zotero.py        # Zotero commands (import with --skip-embed, collections, libraries)
```

See `src/local_library/core/CLAUDE.md`, `src/local_library/llm/CLAUDE.md`, `src/local_library/rag/CLAUDE.md`, `src/local_library/ingestion/CLAUDE.md`, `src/local_library/embeddings/CLAUDE.md`, and `src/local_library/cli/CLAUDE.md` for domain contracts.

## Background Documentation

### Build Planning
- `build_plan.md`: Milestone overview and layer responsibilities
- `build_philosophy.md`: Pipeline-first, layer-complete development approach
- `future_roadmap.md`: Deferred features with context and implementation notes
- `docs/implementation-plans/2025-01-20-m1-m2-record-storage-extraction/`: Detailed implementation plans for M1-M2 (8 phases)

### RAG System Research (authoritative for implementation details)
- `RAG_background/00_final_summary_report.md`: Consolidated recommendations — code patterns, schemas, library configuration
- `RAG_background/pdf_extraction_tools_report.md`: Marker, Docling, olmOCR analysis
- `RAG_background/embedding_approaches_report.md`: nomic-embed-text, chunking strategies, dual embeddings
- `RAG_background/vector_storage_report.md`: sqlite-vec vs LanceDB, hybrid search patterns
- `RAG_background/llm_query_interface_report.md`: Custom wrapper architecture, context assembly
- `RAG_background/citation_tooling_report.md`: Suggestion, triage-based verification, Neovim integration

### Project History
- `background/chat_transcript.md`: Full verbatim transcript of initial planning conversation
- `background/chat_summary.md`: Concise summary of architectural decisions and data model
- `RAG_report_guidance.md`: Original requirements and evaluation criteria for RAG research
- `summary_logs/rag_research_process_2.md`: Meta-documentation of research process
- `README.md`: Project goals and development philosophy
