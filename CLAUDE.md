# CLAUDE.md

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

### Current Phase: Phase 1 — PDF Pipeline

Phase 1 delivers a complete RAG pipeline for PDF documents imported from Zotero. See `build_plan.md` for milestones and detailed planning.

**Scope:**
- PDF ingestion via Zotero import
- Text extraction via Marker
- Embeddings via nomic-embed-text-v1.5
- Vector + full-text search via sqlite-vec + FTS5
- RAG queries via custom wrapper + LiteLLM
- CLI interface

**Deferred to later phases:** Web content ingestion, citation tooling, auto-tagging, note management, Zotero export, Neovim plugin. See `future_roadmap.md` for full details.

### Architectural Layers

Four horizontal concerns cut across the system:

1. **Storage**: SQLite schema, CRUD operations, sqlite-vec, FTS5
2. **Ingestion**: Content acquisition, extraction (Marker), metadata handling
3. **Embeddings**: Chunking, nomic-embed-text, similarity operations
4. **Interface**: CLI, RAG queries, (later) daemon, Neovim plugin, HTTP API

## Key Libraries and Tools

- **Web extraction**: trafilatura, readability-lxml
- **PDF extraction**: Marker (primary), olmOCR (for scanned historical documents on remote GPU)
- **Embeddings**: nomic-embed-text-v1.5 (local, 1024 dims, 8192 context)
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
- Hybrid search via manual RRF (~30 lines Python) combining sqlite-vec + FTS5

### PDF Extraction: Marker + Selective olmOCR
- Marker for primary processing (proven M1 support, ~4s/page)
- olmOCR on remote NVIDIA GPU for scanned historical documents only
- Benchmark claims between tools are contested; Marker is the conservative choice

### Citation Tooling: Triage over Automated Verification
- NLI models achieve only ~77-78% accuracy on academic text (vs ~90%+ general)
- Reframe verification as "triage for human review" rather than "automated decision"
- Same infrastructure, lower accuracy bar, immediate utility

### Pending: Evaluation Framework
A detailed evaluation framework with quality targets, test set design, and evaluation code needs to be researched and created. The v1 research contained useful starter content (see `RAG_background/v1_backport_content.md`), but a proper framework specific to our architecture and use case should be developed before implementation begins. Key elements needed:
- Stratified test query set (50-100 queries across factual, conceptual, comparative, methodology, and adversarial categories)
- Quality targets (Precision@5, Recall@10, MRR, "I don't know" accuracy)
- Latency targets per operation
- Evaluation code for automated measurement

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

## Background Documentation

### Build Planning (start here for implementation)
- `build_plan.md`: **Phase 1 implementation plan** — milestones, layer responsibilities, testing strategy
- `build_philosophy.md`: Pipeline-first, layer-complete development approach (generalizable)
- `future_roadmap.md`: Deferred features with context and implementation notes

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
