# Personal Knowledge Library System: Project Summary

## Project Goal

Build a personal knowledge management system that can ingest diverse digital documents (web articles, PDFs, etc.), extract and store content, generate bibliographic metadata, auto-tag using ML/embeddings, create linked markdown notes, and serve as the basis for a local RAG instance.

## Architectural Decision: Hybrid with Zotero

The system will be **self-sufficient but Zotero-interoperable**. Zotero remains in use for academic PDF management (good browser connector, citation metadata), but the new system is the primary knowledge base. Zotero is a peer the system talks to, not a substrate it extends.

**Why not a Zotero plugin?** The ML features (embeddings, RAG, auto-tagging) require Python infrastructure that can't run in Zotero's JS plugin environment. Once you need an external Python process anyway, it makes sense for that system to own everything Zotero doesn't do well: web content ingestion, text extraction, embeddings, notes management.

## Core Data Model

Each document record contains:

- **Identity:** UUID, citekey (BetterBibTeX-style), optional Zotero item key, DOI/URL/ISBN
- **Bibliographic metadata:** CSL-JSON blob (Zotero-compatible, citation-processor-ready) plus indexed fields
- **Content:** Path to original file, extracted plain text, content hash
- **Embeddings:** Vector embeddings for full doc or chunks (sqlite-vss or similar)
- **Tags:** Manual and auto-generated with source flag; confidence scores for auto-tags
- **Notes:** Path to markdown file with YAML frontmatter linking back to record

## Zotero Interoperability

- **Read:** Direct SQLite access to `zotero.sqlite` (copy file first if Zotero running)
- **Write:** Use local API (port 23119) for tags and item modifications; never write SQLite directly
- **Sync:** Periodic scan for new/modified items; import PDFs and metadata; push auto-tags back

## Implementation Layers (Build Order)

1. **Storage layer:** SQLite schema + filesystem layout for documents and notes
2. **Ingestion layer:** Handlers for web URLs (trafilatura) and PDFs (marker/PyMuPDF)
3. **Zotero import:** Read Zotero database, map to internal schema
4. **Note management:** Generate markdown stubs, maintain frontmatter links
5. **Embedding pipeline:** Chunk documents, compute embeddings, store vectors
6. **Auto-tagging:** Nearest-neighbor tag suggestion or LLM classification
7. **RAG interface:** Query interface feeding relevant chunks to LLM
8. **Zotero export:** Push tags back, optional note sync

Layers 1-4 yield a functional knowledge base. Layers 5-7 add ML features. Layer 8 closes the Zotero loop.

## Key Libraries/Tools

- **Web extraction:** trafilatura, readability-lxml
- **PDF extraction:** marker, PyMuPDF
- **Metadata:** CrossRef API, GROBID (for academic PDFs), Open Graph tags (for web)
- **Vector storage:** sqlite-vss, or pgvector if moving to Postgres
- **Citations:** citeproc-py against CSL-JSON

## Design Principles

- CSL-JSON for bibliographic metadata (standard, Zotero-compatible)
- Generate citekeys by default for all documents
- Markdown notes with YAML frontmatter for portability
- System functions fully without Zotero installed
- Duplicate storage (PDFs in both systems) is acceptable for independence

## Next Step

Define the SQLite schema and filesystem directory structure.
