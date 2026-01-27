# CLI Review Workflow Design

## Summary

This design introduces a CLI-based workflow for reviewing and correcting metadata in documents flagged as NEEDS_REVIEW. The system currently extracts metadata from PDF text with confidence scoring, but low-confidence extractions require human verification. This workflow provides the commands needed to efficiently surface those documents, view their content, and edit their metadata.

The implementation builds on existing Typer/Rich CLI infrastructure with four new commands: an enhanced `list` for filtering by status, `open` for viewing document files, `update` for editor-based metadata editing with validation loops, and optionally `review` to combine these steps. All retrieval commands are extended to accept `@citekey` identifiers in addition to UUIDs, with fuzzy matching suggestions on lookup failures. The update command uses a JSON editing workflow similar to `git commit` or `kubectl edit`, presenting metadata in a temporary file, validating changes on save, and re-prompting with inline errors until the input is valid or the user aborts.

## Definition of Done

**Primary Deliverables:**

1. **Enhanced `list` command**: Displays id (truncated), citekey, status, title (truncated), authors (truncated); supports `--status` filter; defaults to 15 rows with count/hint; `--all` flag enables interactive pagination

2. **`open` command**: Opens document's markdown (default) or PDF (`--pdf`) or both (`--both`); uses nvim for markdown, system default for PDF; supports both UUID and `@citekey` lookup

3. **`update` command**: Launches `$EDITOR` with JSON file containing CSL-JSON + status + citekey; validates changes; re-indexes modified fields; prompts for citekey regeneration when relevant fields change; supports `@citekey` lookup

4. **`@citekey` convention**: All retrieval commands (`show`, `open`, `update`, `delete`) accept `@citekey` in addition to UUID; strict matching with "Did you mean?" suggestions on miss

5. **(Optional) `review` command**: Convenience command that opens markdown + PDF together then launches update flow

**Out of Scope:**
- Schema/model changes (using prompt-based citekey handling)
- Full-text search or filtering by title/author/date
- Web content ingestion or other milestone features

## Glossary

- **citekey**: BetterBibTeX-style unique identifier (e.g., `Smith2023Knowledge`) used for citations; generated from author/title/year metadata
- **CSL-JSON**: Citation Style Language JSON format, a standard schema for bibliographic metadata used by Zotero and citation processors
- **Levenshtein distance**: Edit distance metric measuring how many single-character edits are needed to transform one string into another; used for fuzzy matching
- **Typer**: Python CLI framework built on Click; provides type-driven argument parsing and command structure
- **Rich**: Python library for terminal formatting with tables, colors, pagination, and progress indicators
- **NEEDS_REVIEW**: Document status indicating metadata extraction had low confidence and requires human verification
- **UUID**: Universally Unique Identifier; primary key for documents in the system
- **pager**: Terminal utility (typically `less`) for scrolling through long output; Rich's `Console.pager()` delegates to system pager
- **COALESCE**: SQL function returning first non-null value from a list; used in partial updates to preserve unchanged fields

## Architecture

CLI enhancements for metadata review workflow, built on existing Typer/Rich infrastructure.

### Identifier Resolution

Centralized `resolve_identifier()` function in `cli/utils.py` handles all document lookups:

- Input starting with `@` → citekey lookup via `storage.get_document_by_citekey()`
- Other input → UUID lookup via existing `Library.get()` (full or partial)

On citekey miss, generates suggestions:
1. Prefix match: citekeys starting with input
2. Levenshtein fallback: top 3 closest matches (distance ≤ 3)

All retrieval commands (`show`, `open`, `update`, `delete`) use this resolver.

### List Command Enhancement

Enhanced table with columns: ID (8 chars), Citekey, Status, Title (truncated), Authors (truncated). Hash column removed.

Pagination behavior:
- Default: 15 rows with footer "Showing X of Y items. Use --all to see all."
- `--limit N`: Custom row count
- `--all`: Full table via `Console.pager()` (delegates to system `less`)

### Open Command

Opens document files for viewing:
- Default: Markdown in nvim (fallback: vim, then `$EDITOR`)
- `--pdf`: PDF in system viewer (`open` on macOS, non-blocking)
- `--both`: PDF first (non-blocking), then markdown (blocking)

### Update Command

Editor-based metadata editing workflow:

1. Build JSON with `_readonly` block (informational), plus editable `status`, `citekey`, `csl_json`
2. Write to temp file, launch `$EDITOR`
3. On save: parse, validate (status enum, citekey uniqueness, CSL-JSON schema)
4. If invalid: insert errors as comments at top, re-open editor
5. Loop until valid or abort (empty file)
6. If author/title/year changed AND citekey unchanged: prompt "Regenerate citekey? [y/N]"
7. Apply updates via `storage.update_document_metadata()`, re-index fields

### Review Command (Optional)

Convenience wrapper: opens PDF (non-blocking), opens markdown (blocking), then launches update workflow. PDF is fire-and-forget—no part of the workflow waits for or closes it.

## Existing Patterns

Investigation found existing CLI patterns in `src/local_library/cli/`:

**Table formatting** (`list.py`): Rich Table with colored status badges, truncated columns. This design follows the same approach with additional columns.

**Identifier lookup** (`show.py`, `delete.py`): Uses `Library.get()` with partial UUID support. This design centralizes lookup logic in `cli/utils.py` and extends to support `@citekey`.

**Error handling**: Commands catch domain exceptions (`LookupError`, `MetadataError`) and exit with appropriate codes. New commands follow this pattern.

**Storage layer** (`storage.py`): `get_document_by_citekey()` already exists but isn't exposed via CLI. `update_document_metadata()` supports partial updates with COALESCE. Both are used by new commands.

**Metadata validation** (`metadata.py`): `MetadataHandler.validate()` returns `(is_valid, issues)`. Used by update command's validation loop.

## Implementation Phases

### Phase 1: Identifier Resolution Infrastructure

**Goal:** Centralized identifier resolution with citekey support and suggestions

**Components:**
- `cli/utils.py` — new module with `resolve_identifier()` function
- Suggestion logic: prefix matching + Levenshtein distance calculation
- Integration with existing `Library` and `storage` layer

**Dependencies:** None (foundational)

**Done when:** `resolve_identifier()` correctly routes UUID vs `@citekey`, returns Document or raises LookupError with suggestions

### Phase 2: Enhanced List Command

**Goal:** Improved table display with new columns and pagination

**Components:**
- `cli/list.py` — modified table columns (ID, Citekey, Status, Title, Authors)
- Pagination logic: default row limit, count/hint footer, `--all` with `Console.pager()`
- `--limit` flag for custom row count

**Dependencies:** Phase 1 (for consistent patterns, though list doesn't use resolver)

**Done when:** List shows new columns, respects row limits, `--all` opens system pager

### Phase 3: Open Command

**Goal:** View document files (markdown and/or PDF)

**Components:**
- `cli/open.py` — new command module
- Editor detection: nvim → vim → `$EDITOR`
- System viewer integration: `subprocess.Popen(["open", path])` for PDF
- Uses `resolve_identifier()` for lookup

**Dependencies:** Phase 1 (identifier resolution)

**Done when:** `open @citekey` opens markdown, `--pdf` opens PDF, `--both` opens both

### Phase 4: Update Command

**Goal:** Editor-based metadata editing with validation loop

**Components:**
- `cli/update.py` — new command module
- JSON structure builder (readonly block + editable fields)
- Validation loop: parse → validate → re-open on error
- Citekey regeneration prompt
- Integration with `storage.update_document_metadata()`

**Dependencies:** Phase 1 (identifier resolution), Phase 3 (editor detection logic)

**Done when:** `update @citekey` launches editor, validates changes, applies updates, re-indexes fields

### Phase 5: Existing Command Updates

**Goal:** Retrofit `show` and `delete` to use centralized resolver

**Components:**
- `cli/show.py` — replace `library.get()` with `resolve_identifier()`
- `cli/delete.py` — same replacement

**Dependencies:** Phase 1 (identifier resolution)

**Done when:** `show @citekey` and `delete @citekey` work with suggestions on miss

### Phase 6: Review Command (Optional)

**Goal:** Convenience command combining open + update

**Components:**
- `cli/review.py` — new command module
- Orchestrates: PDF open (non-blocking) → markdown open (blocking) → update workflow

**Dependencies:** Phase 3 (open), Phase 4 (update)

**Done when:** `review @citekey` opens both files then launches update

## Additional Considerations

**Editor error handling:** If `$EDITOR` is unset and nvim/vim not found, exit with clear error message suggesting `export EDITOR=...`.

**Abort detection:** Empty file (or whitespace-only) after editor save treated as abort. Matches `git commit` convention.

**macOS-specific:** PDF opening uses `open` command. Linux support would need `xdg-open`; out of scope for initial implementation but structure allows easy extension.
