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
- **Embeddings**: Vector embeddings for full doc or chunks (sqlite-vss or similar)
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

## Implementation Layers (Build Order)

1. **Storage layer**: SQLite schema + filesystem layout for documents and notes
2. **Ingestion layer**: Handlers for web URLs (trafilatura) and PDFs (marker/PyMuPDF)
3. **Zotero import**: Read Zotero database, map to internal schema
4. **Note management**: Generate markdown stubs, maintain frontmatter links
5. **Embedding pipeline**: Chunk documents, compute embeddings, store vectors
6. **Auto-tagging**: Nearest-neighbor tag suggestion or LLM classification
7. **RAG interface**: Query interface feeding relevant chunks to LLM
8. **Zotero export**: Push tags back, optional note sync

Layers 1-4 yield a functional knowledge base. Layers 5-7 add ML features. Layer 8 closes the Zotero loop.

## Key Libraries and Tools

- **Web extraction**: trafilatura, readability-lxml
- **PDF extraction**: marker, PyMuPDF
- **Metadata**: CrossRef API, GROBID (for academic PDFs), Open Graph tags (for web)
- **Vector storage**: sqlite-vss, or pgvector if moving to Postgres
- **Citations**: citeproc-py against CSL-JSON

## Design Principles

- Use CSL-JSON for bibliographic metadata (standard, Zotero-compatible)
- Generate citekeys by default for all documents
- Markdown notes with YAML frontmatter for portability and interoperability
- System must function fully without Zotero installed
- Duplicate storage (e.g., PDFs in both systems) is acceptable for independence
- Prioritize easy ingestion: adding a blog post should require only a URL

## Background Documentation

- `background/chat_transcript.md`: Full verbatim transcript of initial planning conversation
- `background/chat_summary.md`: Concise summary of architectural decisions and data model
- `README.md`: Project goals and development philosophy
