# Welcome to your Local Library!

A personal knowledge management system for the full lifecycle of digital documents: ingest from multiple sources (PDF today, web and other formats in progress), extract and validate content, manage bibliographic metadata, embed and search the corpus, and ask natural-language questions answered by RAG over your library.

You drive it three ways, all on the same shared core:

- a **CLI** for ingest, search, and ad-hoc queries
- a **Claude Code plugin** that exposes the library as MCP tools and ships skills for grounded writing and verification
- a **Neovim plugin** (with a long-running daemon) for claim-driven citation search inside the editor

Self-sufficient, with read-only interoperability with [Zotero](https://www.zotero.org). The core pipeline (PDF ingestion through RAG query) is implemented and functional; development continues across several parallel feature areas (see [Coming Next](#coming-next)).

## What It Does

- **Ingest PDFs** from local files or **batch-import from Zotero** with collection filtering
- **Extract text** via [Marker](https://github.com/VikParuchuri/marker) with quality validation, markdown cleanup (HTML coercion, dehyphenation, paragraph reflow), and OCR support; falls back to pdftext when Marker fails
- **Extract and validate metadata** against CSL-JSON schema; generate BetterBibTeX-style citekeys; heuristic extraction from PDF text with confidence scoring; optional LLM fallback for low-confidence fields
- **Compute vector embeddings** using nomic-embed-text-v1.5 (768-dim, local inference via sentence-transformers) with section-aware markdown chunking
- **Search** via hybrid retrieval (vector similarity + BM25 via FTS5, fused with reciprocal rank fusion), with optional cross-encoder reranking (ms-marco-MiniLM-L-12-v2)
- **Ask natural-language questions** and get RAG-generated answers with source citations, streaming output, and configurable LLM backend (via LiteLLM)

The whole pipeline is also accessible from outside the CLI — see [Interfaces](#interfaces) for how to drive it from Claude Code or Neovim.

## Interfaces

The system has a shared core (the document pipeline, storage, embedding, retrieval, and RAG) with three user-facing interfaces sitting on top of it.

### CLI

A full Typer/Rich command-line tool for ingesting documents, importing from Zotero, searching, asking questions, and managing the library. Most ad-hoc work happens here — adding documents, running searches, exploring the corpus, batch operations.

→ See [Quick Start](#quick-start) and [Usage](#usage) below.

### Claude Code

A bundled Claude Code plugin makes the library a first-class part of Claude Code sessions. It ships an **MCP server** (four read-only tools: search, show, list, get text) plus **six skills** covering library orientation, extraction-quality fallback, and three procedural composition skills (drafting with grounded sources, verifying claims against the library, checking implementations against papers). With the plugin installed, dropping a `@citekey` in a Claude Code conversation automatically prompts a library lookup; grounded writing and citation verification become the path of least resistance.

The MCP server is also usable on its own (without the plugin) by registering it in `.mcp.json` directly — useful if you want the tools without the skill scaffolding.

→ See [`skills/README.md`](skills/README.md) for install, the full skill set, and test-drive scenarios.

### Neovim

A Lua plugin (`local-library.nvim`) plus a long-running Python daemon for claim-driven citation search from inside the editor. Visual-select a sentence, press `<leader>c`, and a Telescope picker shows ranked chunks from the library; pick one to insert a citekey at cursor and auto-append the bibliography entry. Designed for academic writing where you have a claim in mind and need to find supporting sources.

The daemon (Unix domain socket, JSON-RPC) keeps embedding and reranking models warm, so picker latency is sub-second after the first query. The daemon is shared infrastructure — future clients (HTTP API, MCP server v2) can reuse it without changing the protocol surface.

→ See [`nvim/README.md`](nvim/README.md) for install, configuration, and keymap reference.

## Quick Start

### CLI

```bash
git clone https://github.com/strophios/local-library.git
cd local-library
uv sync
source .venv/bin/activate

local-library add path/to/paper.pdf
local-library search "retrieval augmented generation"
local-library ask "What are the main approaches to document chunking?"
```

### Claude Code plugin

After cloning and `uv sync` as above, in a Claude Code session anywhere on your machine:

```
/plugin marketplace add /absolute/path/to/local-library
/plugin install local-library@local-library
```

Then ask Claude something like *"What does @Smith2023 argue about X?"* — the plugin's orientation skill reaches for the library before answering.

→ Full install and scenarios in [`skills/README.md`](skills/README.md).

### Neovim plugin

After cloning and `uv sync` as above, add to your Neovim config (lazy.nvim shown):

```lua
{
  "strophios/local-library",
  dependencies = { "nvim-lua/plenary.nvim", "nvim-telescope/telescope.nvim" },
  config = function() require("local_library").setup({}) end,
}
```

Then `:LocalLibraryDaemon start`, visual-select a claim in a markdown file with `bibliography: refs.json` in the frontmatter, and press `<leader>c`.

→ Full install and configuration in [`nvim/README.md`](nvim/README.md).

## Usage

The CLI is the primary surface for managing the library. The Claude Code plugin and Neovim plugin have their own usage docs (linked above).

```bash
# Document management
local-library add <path>              # Ingest a PDF (extracts text, metadata, embeds)
local-library add <path> --skip-embed # Ingest without embedding
local-library list                    # List all documents
local-library show @citekey           # Show document details
local-library delete @citekey         # Remove a document
local-library open @citekey           # Open the original file
local-library review @citekey         # Editor-based review for low-confidence extractions
local-library reextract @citekey      # Re-run text extraction (after pipeline improvements)

# Zotero integration (read-only)
local-library zotero import                          # Import from personal library
local-library zotero import --collection "My Papers" # Import specific collection
local-library zotero import --dry-run                # Preview without importing
local-library zotero collections                     # List collections
local-library zotero libraries                       # List libraries

# Search and retrieval
local-library search "query"                  # Hybrid search (vector + FTS, reranked)
local-library search "query" --mode vector    # Vector-only search
local-library search "query" --mode fts       # Full-text search only
local-library search "query" --no-rerank      # Skip cross-encoder reranking
local-library search "query" --doc @citekey   # Scope to a specific document

# RAG queries
local-library ask "question"          # Streaming answer with source citations
local-library ask "question" --model anthropic/claude-sonnet-4-20250514
local-library ask "question" --json   # Machine-readable output

# Library daemon (used by the Neovim plugin; can run standalone)
local-library daemon start
local-library daemon status
local-library daemon stop
```

All commands accepting document IDs accept either a UUID (full or partial) or `@citekey`.

## How it works

This section is for readers who want to understand *why* the system is shaped the way it is, not just how to install it. If you're integrating, extending, or evaluating fit, this is the relevant content.

### Pipeline and layers

The system is built around two orthogonal organizing principles.

**Pipeline** (vertical) — the path a document takes from ingestion to queryable knowledge:

```
Ingest → Extract text → Validate metadata → Store → Embed → Retrieve → Generate answer
```

**Layers** (horizontal) — architectural concerns that cut across the pipeline:

| Layer | Responsibility | Key components |
|-------|---------------|----------------|
| Storage | SQLite (schema v4), content-addressable files, sqlite-vec, FTS5 | `core/storage.py`, `core/models.py` |
| Ingestion | PDF extraction (Marker + pdftext fallback), metadata handling, Zotero import | `ingestion/` |
| Embeddings + Retrieval | Chunking, nomic-embed-text, vector/FTS/hybrid search, cross-encoder reranking | `embeddings/` |
| LLM + RAG | LiteLLM provider abstraction, context assembly, prompt construction, answer generation | `llm/`, `rag/` |
| Interface | CLI (Typer + Rich), MCP server (FastMCP, stdio), library daemon (asyncio, UDS, JSON-RPC), Neovim plugin (Lua) | `cli/`, `mcp/`, `daemon/`, `nvim/` |

Development follows a **pipeline-first, layer-complete** approach: build along the pipeline for rapid feedback on the end-to-end experience; implement each architectural layer completely when touched. See [`build_philosophy.md`](build_philosophy.md) for the full rationale.

### Shared core, multiple interfaces

The core pipeline doesn't know about its consumers. The CLI, the MCP server, and the daemon are all clients of the same `Library` API in `src/local_library/core/library.py`. This isn't accidental — building the MCP server first validated the Library API surface against a real consumer before the daemon committed to a protocol; the daemon's protocol is the path through which the MCP server will eventually swap from in-process `Library()` to a socket client (without changing tool contracts).

Why three interfaces rather than one universal one? Each addresses a distinct workflow, with different latency tolerances and interaction patterns:

- **CLI** — ingest, batch operations, exploration, ad-hoc queries. Latency-tolerant; spins up cold.
- **Claude Code plugin** — research and writing happen inside a Claude session; the library should be a first-class tool there, with skills handling grounded retrieval, drafting, and verification rather than ad-hoc shell commands.
- **Neovim plugin** — citation insertion needs sub-second latency, so it's backed by a long-running daemon that keeps embedding and reranking models warm in memory.

The split also reflects path dependency. The CLI came first because a command-line surface is the simplest harness for the Library API; validating the API against a real consumer before committing to more complex interfaces was cheaper than the other order. There's no fundamental reason batch ingest *has* to live on the CLI rather than as a Claude Code tool — it just sensibly does, since routing batch operations through an LLM session would be friction without payoff. Each interface ended up where it did because of where the work actually happens.

The boundary between "shared core" and "interface" is also less fixed than the layer table suggests. The daemon currently sits on the Neovim side of the line — nothing else uses it yet — but if the MCP server later swaps to a daemon client (the planned v2 path), the daemon effectively migrates inward toward shared infrastructure. New functionality can be built either by extending an interface or by extending the shared core, and sometimes the latter subsumes things the interfaces previously handled separately. Useful to keep in mind when reasoning about where new code belongs.

### Self-sufficient with Zotero interoperability

The system functions completely independently of Zotero, but reads from a Zotero database when one is present (citekeys via Zotero 8's native field, CSL-JSON metadata via Better BibTeX export). Zotero is treated as a peer/data source, not as a substrate the system extends.

This is *not* a Zotero plugin. ML features (embeddings, RAG, auto-tagging, reranking) require Python infrastructure that can't run in Zotero's JavaScript plugin environment. Once external Python infrastructure is necessary, it makes sense for that system to own all the functionality beyond Zotero's strengths (web ingestion, text extraction, embeddings, auto-tagging, markdown notes). Zotero remains valuable in its own lane — academic PDF management via its browser connector and citation metadata — and we read from it rather than competing with it.

Writes to Zotero, when implemented, will go through the Zotero local API on port 23119, never directly to its SQLite (which would risk corruption or sync conflicts).

### Tech stack

- **Languages:** Python 3.10+, Lua (for the Neovim plugin)
- **Storage:** SQLite + [sqlite-vec](https://github.com/asg017/sqlite-vec) (vector storage) + FTS5 (full-text search)
- **PDF extraction:** [Marker](https://github.com/VikParuchuri/marker) (with OCR via Surya), pdftext fallback
- **Embeddings:** nomic-embed-text-v1.5 via [sentence-transformers](https://www.sbert.net/) (local inference, no API calls)
- **Reranking:** cross-encoder/ms-marco-MiniLM-L-12-v2 via sentence-transformers
- **LLM interface:** [LiteLLM](https://github.com/BerriAI/litellm) (provider-agnostic; works with Claude, GPT, local models)
- **CLI:** [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/)
- **MCP server:** [FastMCP](https://modelcontextprotocol.io/) (mcp SDK, stdio transport)
- **Library daemon:** asyncio, JSON-RPC 2.0 over Unix domain socket
- **Neovim plugin:** Lua, Telescope, plenary.async
- **Metadata:** CSL-JSON schema validation, BetterBibTeX-style citekeys
- **Package management:** [uv](https://github.com/astral-sh/uv)

### Project structure

```
local-library/
├── src/local_library/    # Python package: core pipeline + CLI + MCP server + daemon
│   ├── core/             # Library API, storage, models, error hierarchy
│   ├── ingestion/        # PDF extraction, metadata, Zotero import
│   ├── embeddings/       # Chunking, embedding, retrieval, reranking
│   ├── llm/              # LiteLLM abstraction
│   ├── rag/              # Context assembly, generation
│   ├── cli/              # Typer/Rich CLI commands
│   ├── mcp/              # FastMCP server (stdio)
│   └── daemon/           # Long-running daemon (UDS, JSON-RPC)
├── nvim/                 # Neovim plugin (Lua); has its own README and CLAUDE.md
│   ├── lua/              # Plugin code
│   ├── plugin/           # Auto-loaded user commands
│   └── doc/              # Vimdoc
├── skills/               # Claude Code plugin skills (six SKILL.md files); has its own README
├── .claude-plugin/       # Plugin manifest + marketplace entry
├── .mcp.json             # MCP server config (uses ${CLAUDE_PLUGIN_ROOT})
├── docs/                 # Design plans, implementation plans, RAG research, feature-area planning
└── tests/                # Unit, integration, eval, extraction-quality, skill verification
```

Top-level symlinks (`lua → nvim/lua`, `plugin → nvim/plugin`, `doc → nvim/doc`) make the Neovim plugin installable by any plugin manager that follows standard runtimepath conventions, without a `subdir` workaround.

The repo intentionally bundles three distributable units (Python package, Claude Code plugin, Neovim plugin). They share the underlying corpus and Library API, and shipping them together keeps versions aligned. If they ever outgrow the single repo, the boundaries are clean — `nvim/` and `skills/` already function as self-contained interface trees.

## Coming Next

Development continues across several parallel feature areas, each documented in `docs/feature-areas/`:

- **Content Ingestion** — `add <url>` for web articles via trafilatura; later EPUB and other formats, plus external metadata API enrichment (CrossRef, OpenAlex)
- **Note Management** — auto-generated markdown stubs with YAML frontmatter linked to library records
- **Automated Content Analysis** — ML-based auto-tagging, clustering, and triage-based verification across the full corpus
- **RAG Pipeline Improvements** — evaluation harness expansion, retrieval quality tuning, query decomposition (currently focused on eval re-annotation at corpus scale)

See [`roadmap.md`](roadmap.md) for current focus, sequencing, and dependencies.

## Development

This project was designed and built collaboratively with [Claude Code](https://docs.anthropic.com/en/docs/claude-code). I made all architectural and design decisions — the data model, pipeline architecture, retrieval strategy, Zotero interoperability approach, build methodology, and interface design. Claude Code served as the primary implementation collaborator, with me reviewing, testing, and directing the work.

The development process is documented:

- [`build_philosophy.md`](build_philosophy.md) — the pipeline-first, layer-complete development methodology
- [`roadmap.md`](roadmap.md) — current status and feature-area sequencing
- [`docs/development-history.md`](docs/development-history.md) — milestone narrative and project history
- `CLAUDE.md` files at project and subpackage level — technical context for working in the codebase
- `docs/design-plans/` and `docs/implementation-plans/` — point-in-time design and execution records

### Running Tests

```bash
uv run pytest                                    # Standard test suite
uv run pytest --run-extraction-quality           # Include extraction quality benchmarks
```

## License

MIT
