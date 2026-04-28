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

Development is organized into six feature areas, each with documented plans in `docs/feature-areas/`:

- **Content Ingestion** - `add <url>` for web articles, later EPUB and other formats, plus external metadata API enrichment
- **Claude Code Integration** - MCP server (built) exposing library operations as Claude Code tools; research skills layered on top
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


---

## Claude Code Plugin

This repo also ships as a Claude Code plugin: six skills bundled with the MCP server config Claude Code needs to talk to your local library. With the plugin installed, a citekey dropped in conversation prompts a library lookup automatically, and grounded writing/checking is the path of least resistance.

### What the plugin provides

- Two **orientation** skills (always-apply): teach Claude to notice library-adjacent cues and reach for `mcp__local-library__*` tools fluently; teach Claude to fall back to the original PDF when extracted markdown is garbled.
- One **shared grounding kernel**: atomic per-assertion retrieve → quote → synthesize → report cycle the procedural skills compose on.
- Three **procedural composition** skills: drafting with grounded sources (prose + audit appendix), implementation-check against papers (assertion table comparing code to method descriptions), verifying claims against the library (claim-by-claim status with quoted support).

The plugin works from any project where you have Claude Code running — the library doesn't have to be the project you're working on.

### Who this is for

Anyone using the local-library MCP server who wants Claude Code to:
- Treat citekeys as library handles, not topic labels
- Quote evidence by default, not paraphrase from training
- Tag claims with explicit support / contradict / partial / not-found rather than rubber-stamp them
- Read the PDF when extracted markdown can't be trusted (math, figures, tables)

### Plugin install

From a fresh checkout:

    git clone <this-repo>
    cd local-library
    uv sync

Then in a Claude Code session anywhere on your machine:

    /plugin marketplace add /absolute/path/to/local-library
    /plugin install local-library

The plugin's `.mcp.json` brings the MCP server with it (no separate registration), and the six skills auto-discover via Claude Code's plugin loader.

### Architectural overview

The plugin uses a three-layer architecture that separates concerns cleanly: orientation skills (always-apply) notice library-adjacent cues and reach for MCP tools fluently; a grounding kernel handles the atomic retrieve-quote-synthesize cycle per assertion; procedural composition skills decompose problems and orchestrate the kernel across multiple claims.

Why this split? Plugins can't ship a user-global CLAUDE.md, so orientation skills must be always-apply to catch citekeys and extraction problems automatically. The kernel is deliberately atomic—a single claim, one retrieve pass, evidence quoted and synthesized—because composing skills handle the decomposition. Without this split, the kernel would bias toward "one chunk answers the whole question," which short-changes multi-source synthesis and forces users to rephrase broad questions as narrow ones.

The plugin bundles with the repository for practical reasons: it travels with your library instance, is shareable (you can publish the repo and others add it from GitHub), and works from any project on your machine without global registration overhead.

Safety is built in. When the extraction-quality skill detects garbled math or broken figures in extracted markdown, it cross-invokes itself with a fallback: use the native Read tool on the PDF path provided by show_document. This keeps you grounded in the source when the text layer is unreliable.

End-to-end flow: A citekey appears in conversation, the orientation skill triggers show_document and quotes the abstract. You ask a question that decomposes into multiple claims. The procedural skill enumerates them. The kernel runs per-claim—retrieve relevant chunks, quote evidence, synthesize—and each result flows to the output formatter. The final result (prose with appendix, assertion table, claim table) is assembled per skill format.

### Skills at a glance

| Skill | Layer | What it does |
|---|---|---|
| `using-local-library-mcp` | Orientation | Reach for `mcp__local-library__*` tools when citekeys or library cues appear |
| `handling-extraction-quality` | Orientation | Fall back to `Read` on the PDF when extracted markdown is garbled |
| `grounding-against-library` | Kernel | Per-assertion retrieve → quote → synthesize → report; multi-source |
| `drafting-with-grounded-sources` | Procedural | Decompose into propositions; ground each via the kernel; produce prose + appendix |
| `implementation-check-against-papers` | Procedural | Decompose code into claims; ground against paper(s); produce assertion table |
| `verifying-claims-against-library` | Procedural | Enumerate citation-bearing claims; per-claim grounding; produce claim table |

### Test-drive scenarios

After installing, try these:

1. **Orientation triggers on bare citekey:**
   > "What does @<your-citekey> argue about <topic>?"
   Expected: Claude calls `show_document` (or `search_library`) before responding; quotes evidence rather than summarizing from training.

2. **Safety hatch triggers on garbled extraction:**
   > "Open @<your-mathy-citekey> and explain the main equation."
   Expected: Claude reads the PDF directly via `Read` if extracted markdown is garbled; cites page number.

3. **Kernel returns control on a broad request:**
   > "Tell me how the literature in my library handles <topic>."
   Expected: Claude declines to answer and proposes a decomposition.

4. **Drafting with appendix:**
   > "Write a short note on <topic> drawing from @<A> and @<B>."
   Expected: prose with inline citekeys + grounding-summary appendix at end.

5. **Verifying claims:**
   > "Check whether my library supports these:
   > 1. <claim> — per @<X>
   > 2. <claim> — per @<Y>"
   Expected: claim table with quoted support, statuses, summary line.

### Disabling / overriding plugin skills

To disable individual skills without uninstalling the plugin:
- Edit `~/.claude/settings.json` and add the skill name to the `disabledSkills` list (or use the `/plugin` UI).
- To narrow tool authorization for a single skill, edit the `allowed-tools` block in that skill's `SKILL.md` after installation (note: this edits the installed copy, not the source repo).

To uninstall:

    /plugin uninstall local-library
    /plugin marketplace remove local-library

### Where the plugin's pieces live

- Skills: `skills/<skill-name>/SKILL.md`
- Plugin manifest: `.claude-plugin/plugin.json`
- Marketplace advertisement: `.claude-plugin/marketplace.json`
- MCP server config: `.mcp.json` (uses `${CLAUDE_PLUGIN_ROOT}`)
- Design doc: `docs/design-plans/2026-04-24-local-library-claude-code-plugin.md`
- Implementation plan: `docs/implementation-plans/2026-04-24-local-library-claude-code-plugin/`
- RED baselines, GREEN/Tier-3 transcripts, smoke tests: `tests/skills/`
