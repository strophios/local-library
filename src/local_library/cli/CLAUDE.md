# CLI Domain

Last verified: 2026-04-25

## Purpose

Command-line interface for the local-library system. Provides user-facing commands for document management, viewing, and metadata editing. All commands support both UUID and @citekey identifiers.

## Contracts

- **Exposes**: CLI commands (add, ask, list, show, delete, open, update, review, reextract, embed, search), daemon command group (start, stop, status, restart, run), zotero command group (import, collections), identifier resolution utilities
- **Guarantees**:
  - All commands accepting document IDs support UUID (full or partial) and @citekey syntax
  - Failed citekey lookups provide fuzzy match suggestions (Levenshtein distance + prefix matching)
  - Validation errors in update/review re-open editor with error comments (no silent failures)
  - Editor detection: nvim > vim > $EDITOR fallback
  - PDF opens non-blocking; markdown opens blocking
  - Both `--llm` and `--llm-extract` flags validate GEMINI_API_KEY early, warn and disable if missing
  - embed command requires sqlite-vec; fails gracefully with helpful error if unavailable
  - search command requires sqlite-vec; fails gracefully with helpful error if unavailable
  - search command validates --mode against (hybrid, vector, fts) before executing
  - search --doc supports UUID and @citekey identifiers for document-scoped search
  - FTS query syntax errors caught and reported with suggestion to use --mode vector
  - --no-rerank flag available on search and ask to disable cross-encoder reranking (reranking enabled by default)
  - --skip-embed flag available on add and zotero import for batch workflows
  - ask command requires sqlite-vec; fails gracefully with helpful error if unavailable
  - ask command validates --mode against (hybrid, vector, fts) before executing
  - ask command supports --doc for document-scoped queries (UUID and @citekey)
  - ask command streams by default; --json implies --no-stream
  - ask command catches LLMError, RAGError, EmbeddingError, LookupError with mode-appropriate messages
  - reextract command re-runs extraction pipeline on stored PDFs; overwrites extracted markdown and marks embeddings STALE
  - reextract supports single document (UUID/@citekey) or --all for bulk re-extraction
  - reextract --all targets READY and NEEDS_REVIEW documents; continues on per-document errors
  - list command accepts --year (integer), --year-missing (flag), --author-contains (string), --title-contains (string), --citekey-prefix (string) filters that combine with AND semantics
  - list --year and --year-missing are mutually exclusive; passing both raises error
  - list substring filters (--author-contains, --title-contains) are case-insensitive; wildcard characters (%, _) are matched literally rather than as patterns
  - list --citekey-prefix is case-insensitive prefix match
- **Expects**: Library context manager for database access; editor available for update/review/open commands

## Dependencies

- **Uses**: `core.Library`, `core.models` (Document, DocumentStatus, MetadataSource, RAGResponse), `core.errors` (LookupError, EmbeddingError, FTSQueryError, LLMError, RAGError), `core.storage` (get_connection, get_unique_citekey), `core.vec_extension` (is_vec_available), `ingestion.metadata` (MetadataHandler), `embeddings.base` (SearchResult), `daemon.pid_file`, `daemon.server` (for daemon subcommand group)
- **Used by**: Entry point (`local-library` command)
- **Boundary**: CLI MUST NOT be imported by core or ingestion

## Key Decisions

- **Identifier resolution in utils**: `resolve_identifier()` centralizes UUID/@citekey dispatch with fuzzy suggestions
- **Editor validation loop**: update command re-opens editor with errors as comments until valid
- **Review as composition**: review command combines open --both + update (not separate implementation)
- **Pagination via --limit/--all**: list defaults to 20 items; --all disables limit
- **Non-blocking PDF opens**: Uses platform-native commands (open/xdg-open/start) via subprocess.Popen
- **Early API key validation**: `--llm` and `--llm-extract` check GEMINI_API_KEY before Library instantiation; warn and gracefully disable features if missing
- **Zotero import as command group**: `zotero` subcommand groups Zotero-related operations; `import` subcommand handles batch import with progress tracking, `collections` lists available collections
- **Library-scoped import**: All import helper functions (`_handle_dry_run`, `_import_items`, `_import_items_rich`, `_import_items_json`, `_item_has_pdf`, `_process_single_item`) accept and thread `library_id: int` to ZoteroReader calls. Defaults to 1 (personal library) when CLI `--library` not specified. Prevents cross-library citekey collisions during item resolution.
- **Citekey-based skip logic**: Batch import skips items whose citekey already exists in local-library (fast check); hash-based deduplication catches any that slip through. Citekey listing is library-scoped via `list_citekeys_in_library()`.
- **Zotero citekey preservation**: Import passes Zotero's citekey to Library.add() to preserve BetterBibTeX citekeys; enables accurate deduplication on subsequent imports
- **Metadata source tagging**: add command passes MetadataSource.EXPLICIT when --metadata provided; zotero import passes MetadataSource.ZOTERO. Bare paths default to FILENAME (handled by Library).
- **Progress callback in zotero import**: `_make_console_progress_callback()` factory creates Rich Console callback for extraction events (pre-check, heartbeat, completion, fallback). Wired into `_import_items_rich()`. JSON mode uses logger fallback.
- **Batched Library recreation**: Import recreates Library every EXTRACTION_BATCH_SIZE (50) extractions to release Marker's native resources (PyTorch, multiprocessing). Defensive measure for very large imports
- **Zotero directory detection**: Uses ZOTERO_DIR env var or platform-specific defaults (~/Zotero)
- **Embed command modes**: Three orthogonal modes (single doc, --pending, --all) with mutual exclusivity validation; --force re-embeds existing; --dry-run non-destructive
- **Skip embed flags**: --skip-embed on add/zotero import defers embedding to separate batch operation for faster ingestion; allows bulk embedding in single batch call
- **Batch error logging**: Batch embedding catches exceptions and logs them to stderr per-document for visibility; --json output suppresses per-document logs but includes final count
- **Search command**: `search` command delegates to `Library.get_retriever()` factory; supports hybrid/vector/fts modes, document-scoped search via --doc, JSON output, and --no-rerank to disable cross-encoder reranking
- **Search error handling**: Three error types caught (LookupError for --doc resolution, FTSQueryError for syntax, EmbeddingError for sqlite-vec); each provides mode-appropriate error messages
- **Search output formats**: Rich table (default) shows rank, score, source, methods, text preview; --json outputs structured array for programmatic use
- **Ask command streaming**: Uses Rich Live display for token-by-token streaming; graceful Ctrl+C shows partial answer; sources footer printed after stream completes
- **Ask command JSON output**: --json implies --no-stream (must collect full response for structured output); outputs question, answer, model, retrieval_mode, and aggregated sources with chunk counts
- **Ask command model override**: --model flag passed to Library via `rag_model` parameter; overrides default "gemini/gemini-2.0-flash"
- **Ask command error handling**: Four error types caught (LookupError, EmbeddingError, RAGError, LLMError); JSON mode outputs error with code, non-JSON prints styled error
- **Reranking opt-out pattern**: Both search and ask use `--no-rerank` (negated boolean) because reranking is on by default. Forwarded as `rerank=not no_rerank` to Library methods
- **Reextract command**: Re-runs extraction pipeline (Marker + cleanup) on existing documents without modifying metadata. Marks embeddings STALE so `embed --pending` picks them up. Uses `embed_on_add=False` to avoid auto-embedding during re-extraction.
- **Daemon subcommand group**: `daemon` subcommand groups process lifecycle operations; `start` spawns detached, `stop` sends SIGTERM, `status` reports pid/uptime/resident, `restart` is stop-then-start, `run` is foreground entry point. Resolves running PID via pid_file.read_pid() + is_process_alive() check. Uses psutil.Process() for status queries.

## Invariants

- @citekey identifiers always start with `@` character
- Suggestions list never exceeds 3 items
- Editor temp files cleaned up even on validation failure
- Empty file in editor = abort (no changes applied)

## Key Files

- `main.py` - Entry point, command registration
- `utils.py` - `resolve_identifier()`, `suggest_citekeys()`, `levenshtein_distance()`, `LibraryProtocol`
- `add.py` - Add command with --metadata flag
- `ask.py` - Ask command with streaming, --no-stream, --json, --model, --mode, --doc, --limit, --no-rerank options
- `list.py` - List command with --limit/--all pagination
- `show.py` - Show command with @citekey support
- `delete.py` - Delete command with @citekey support
- `open.py` - Open command with --pdf/--both flags, `find_editor()`
- `update.py` - Update command with editor-based validation loop
- `review.py` - Review command (open --both + update composition)
- `embed.py` - Embed command with --pending, --all, --force, --dry-run options
- `reextract.py` - Reextract command with single-doc and --all modes, progress tracking, continue-on-error
- `search.py` - Search command with --limit, --mode, --doc, --json, --no-rerank options
- `daemon.py` - Daemon command group with start/stop/status/restart/run subcommands
- `zotero.py` - Zotero command group with `import` (batch import with progress, progress callback), `collections` (list collections), `_make_console_progress_callback()` factory

## Gotchas

- `find_editor()` returns None if no editor found (caller must handle)
- Validation errors are inserted as `//` comments in JSON (JSON doesn't support comments; stripped on parse)
- Citekey uniqueness checked against all_citekeys before save
- update_metadata() extracts indexed fields from CSL-JSON automatically
- Review command requires extracted_path to exist (fails early if missing)
- **Rich + Marker conflict**: Rich's progress bar must be stopped during PDF extraction. Marker's multiprocessing conflicts with Rich's terminal state on macOS, causing Objective-C runtime errors or heap corruption. Import stops progress before extraction, restarts after.
