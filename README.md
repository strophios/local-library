# Welcome to your Local Library!

A personal knowledge management system designed to handle the full lifecycle of digital documents: ingest from multiple sources (PDF today, web content and other formats in progress), extract and validate content, manage bibliographic metadata, auto-tag relative to everything else in the library, generate linked notes, and make the full collection queryable via RAG. Self-sufficient, with read-only interoperability with [Zotero](https://www.zotero.org).

The core pipeline (PDF ingestion through RAG query) is implemented and functional. Development is organized around five feature areas being built out incrementally toward the full vision (see [Coming Next](#coming-next)).

## What It Does

- **Ingest PDFs** from the local filesystem or **batch-import from Zotero** with collection filtering
- **Extract text** via [Marker](https://github.com/VikParuchuri/marker) with quality validation, markdown cleanup (HTML coercion, dehyphenation, paragraph reflow), and OCR support
- **Extract and validate metadata** against CSL-JSON schema; generate BetterBibTeX-style citekeys; heuristic extraction from PDF text with confidence scoring; optional LLM fallback for low-confidence fields
- **Compute vector embeddings** using nomic-embed-text-v1.5 (768-dim, local inference via sentence-transformers) with section-aware markdown chunking
- **Search** via hybrid retrieval (vector similarity + BM25 via FTS5, fused with reciprocal rank fusion), with optional cross-encoder reranking (ms-marco-MiniLM-L-12-v2)
- **Ask natural-language questions** and get RAG-generated answers with source citations, streaming output, and configurable LLM backend (via LiteLLM)
- **Manage documents** through a full CLI: add, list, show, delete, open, update, review, reextract, embed, search, ask

## Coming Next

Development is organized into five feature areas, each with documented plans in `docs/feature-areas/`:

- **Web Content Ingestion** - `add <url>` for web articles, blog posts, and other online content via trafilatura
- **Neovim Citation Workflow** - library daemon + Neovim plugin for visual-mode citation search from within your editor
- **Note Management** - auto-generated markdown stubs with YAML frontmatter linked to library records
- **Automated Content Analysis** - ML-based auto-tagging, clustering, and triage-based verification across the full corpus
- **RAG Pipeline Improvements** - evaluation harness, retrieval quality tuning, query decomposition

See `roadmap.md` for current progress and sequencing.


## Architecture

The system is built around two orthogonal organizing principles:

**Pipeline** (vertical): the path a document takes from ingestion to queryable knowledge.

```
Ingest → Extract text → Validate metadata → Store → Embed → Retrieve → Generate answer
```

**Layers** (horizontal): architectural concerns that cut across the pipeline.

| Layer | Responsibility | Key components |
|-------|---------------|----------------|
| Storage | SQLite (schema v3), content-addressable files, sqlite-vec, FTS5 | `core/storage.py`, `core/models.py` |
| Ingestion | PDF extraction (Marker), metadata handling, Zotero import | `ingestion/` |
| Embeddings + Retrieval | Chunking, nomic-embed-text, vector/FTS/hybrid search, cross-encoder reranking | `embeddings/` |
| LLM + RAG | LiteLLM provider abstraction, context assembly, prompt construction, answer generation | `llm/`, `rag/` |
| Interface | CLI (Typer + Rich) | `cli/` |

Development follows a **pipeline-first, layer-complete** approach: build along the pipeline for rapid feedback on the end-to-end experience; implement each architectural layer completely when touched. See `build_philosophy.md` for the full rationale.

## Tech Stack

- **Language:** Python 3.10+
- **Storage:** SQLite + [sqlite-vec](https://github.com/asg017/sqlite-vec) (vector storage) + FTS5 (full-text search)
- **PDF extraction:** [Marker](https://github.com/VikParuchuri/marker) (with OCR via Surya)
- **Embeddings:** nomic-embed-text-v1.5 via [sentence-transformers](https://www.sbert.net/) (local inference, no API calls)
- **Reranking:** cross-encoder/ms-marco-MiniLM-L-12-v2 via sentence-transformers
- **LLM interface:** [LiteLLM](https://github.com/BerriAI/litellm) (provider-agnostic; works with Claude, GPT, local models)
- **CLI:** [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/)
- **Metadata:** CSL-JSON schema validation, BetterBibTeX-style citekeys
- **Package management:** [uv](https://github.com/astral-sh/uv)

## Quick Start

```bash
# Clone and install
git clone https://github.com/strophios/local-library.git
cd local-library
uv sync
source .venv/bin/activate

# Add a document
local-library add path/to/paper.pdf

# Search your library
local-library search "retrieval augmented generation"

# Ask a question
local-library ask "What are the main approaches to document chunking?"
```

## Usage

```bash
# Document management
local-library add <path>              # Ingest a PDF (extracts text, metadata, embeds)
local-library add <path> --skip-embed # Ingest without embedding
local-library list                    # List all documents
local-library show @citekey           # Show document details
local-library delete @citekey         # Remove a document
local-library open @citekey           # Open the original file

# Zotero integration
local-library zotero import                          # Import from personal library
local-library zotero import --collection "My Papers" # Import specific collection
local-library zotero import --dry-run                # Preview without importing

# Search and retrieval
local-library search "query"          # Hybrid search (vector + FTS, reranked)
local-library search "query" --mode vector   # Vector-only search
local-library search "query" --mode fts      # Full-text search only
local-library search "query" --no-rerank     # Skip cross-encoder reranking

# RAG queries
local-library ask "question"          # Streaming answer with source citations
local-library ask "question" --model anthropic/claude-sonnet-4-20250514
local-library ask "question" --json   # Machine-readable output
```

## Project Structure

```
src/local_library/
├── cli/            # CLI commands (Typer + Rich)
│   ├── main.py     # App entrypoint and command registration
│   ├── add.py      # Document ingestion
│   ├── search.py   # Search interface
│   ├── ask.py      # RAG query interface
│   ├── zotero.py   # Zotero import commands
│   └── ...         # list, show, delete, embed, review, etc.
├── core/           # Data model, storage, error hierarchy
│   ├── library.py  # Library facade (main API surface)
│   ├── storage.py  # SQLite operations + schema management
│   ├── models.py   # Domain models (Document, Chunk, SearchResult, etc.)
│   └── errors.py   # Typed error hierarchy with ErrorCode enum
├── embeddings/     # Embedding pipeline + retrieval
│   ├── nomic.py    # nomic-embed-text embedding provider
│   ├── chunking.py # Section-aware markdown chunking
│   ├── retrieval.py# Vector, FTS, hybrid, and reranked retrievers
│   ├── reranking.py# Cross-encoder reranking
│   └── storage.py  # sqlite-vec operations
├── ingestion/      # Document acquisition + extraction
├── llm/            # LLM abstraction (LiteLLM backend)
├── rag/            # RAG pipeline (context assembly, generation)
└── config.py       # Configuration management
```

## Development

This project was designed and built collaboratively with [Claude Code](https://docs.anthropic.com/en/docs/claude-code). I made all architectural and design decisions — the data model, pipeline architecture, retrieval strategy, Zotero interoperability approach, and build methodology. Claude Code served as the primary implementation collaborator, with me reviewing, testing, and directing the development through ~490 commits.

The development process is documented in detail:
- `build_philosophy.md` — the pipeline-first, layer-complete development methodology
- `roadmap.md` — current status and planned feature areas
- `CLAUDE.md` files at project and subpackage level — detailed technical context

### Running Tests

```bash
uv run pytest                                    # Standard test suite
uv run pytest --run-extraction-quality           # Include extraction quality benchmarks
```

## License

MIT
