# Library List Filters Design

## Summary

This document describes a set of additions to `Library.list()` and its two consumers (the `local-library list` CLI command and the MCP `list_documents` tool) that make document discovery genuinely useful. The current listing surface filters only on `status`, which makes both interfaces essentially an ordering tool rather than a query tool — for Claude Code in particular, "show me docs by Zippel" or "show me my 2023 docs" are natural discovery questions that cannot be satisfied today.

The change adds four new filter parameters (`year`, `author_contains`, `title_contains`, `citekey_prefix`) combined with AND semantics, plus a way to explicitly filter for documents with missing year information. The `year` filter requires a schema change: we add a derived `issued_year INTEGER` column to the `documents` table, populated at write time from `csl_json["issued"]`, and indexed for efficient range and equality queries. All existing denormalized indexed columns (title, authors, issued_date) follow this same pattern, so this is additive rather than architectural.

The schema migration from v3 to v4 uses the existing migration framework in `storage.py` (precedent: `_migrate_v1_to_v2` added title/authors/issued_date columns; `_migrate_v2_to_v3` added embeddings infrastructure). Auto-migration happens on library startup with informative logging so users understand any delay. Backfill populates `issued_year` from the already-normalized `issued_date` text column via prefix extraction, with NULL for documents whose date is missing or malformed.

This design deliberately **does not** bundle in the roadmap's other pending schema work (extraction metadata persistence — duration, device, fallback tracking). That work has open design questions that would block or rush this work; keeping them separate means shipping filters promptly and doing the extraction metadata work with its own design pass when ready.

## Definition of Done

- **`Library.list()`** accepts five optional filter parameters: `status`, `year`, `year_missing`, `author_contains`, `title_contains`, `citekey_prefix`. Multiple filters combine with AND semantics.
- **`year`** matches documents where `issued_year` equals the given integer. Mutually exclusive with `year_missing`.
- **`year_missing=True`** matches documents where `issued_year IS NULL`. Mutually exclusive with `year`.
- **`author_contains`** matches documents where the `authors` text column contains the given substring, case-insensitive.
- **`title_contains`** matches documents where the `title` text column contains the given substring, case-insensitive.
- **`citekey_prefix`** matches documents whose `citekey` starts with the given string, case-insensitive.
- **Schema v4 migration** adds `issued_year INTEGER` column and `idx_documents_issued_year` index to the `documents` table.
- **Backfill** populates `issued_year` for all existing documents where possible (`int(issued_date[:4])` with try/except), NULL otherwise.
- **Write path** (`_extract_indexed_fields()` in `library.py`) populates `issued_year` alongside the existing indexed fields (title, authors, issued_date).
- **Year parsing** is extracted to a shared utility function in `metadata.py`, consumed by both the existing citekey year extraction (`_extract_year_for_citekey`) and the new indexed-field extraction.
- **CLI `local-library list`** gains `--year`, `--year-missing`, `--author-contains`, `--title-contains`, `--citekey-prefix` flags with helpful descriptions in `--help`.
- **MCP `list_documents` tool** gains corresponding keyword parameters with updated tool description so Claude knows what filters are available.
- **Migration messaging**: library startup logs an informational message when a migration runs ("Migrating database from schema v3 to v4...") and a meaningful error message with remediation hints if migration fails.
- **Tests**: migration test (create v3 DB, run migration, verify v4 schema + backfilled data), filter combination tests, NULL-year handling, edge cases (empty strings, non-numeric years, missing CSL-JSON fields).
- **Documentation**: `core/CLAUDE.md` updated with new filter contract; `mcp/CLAUDE.md` updated with new tool parameters; `CLAUDE.md` (root) Commands section updated.

**Out of scope**: extraction metadata persistence (duration/device/fallback — separate work, future v5); additional derived columns beyond `issued_year` (e.g., primary author surname — defer until demonstrated need); tag-based filtering (requires separate tag schema design); filter on CSL-JSON JSON path expressions; SQL-like query DSL or free-text query syntax.

## Glossary

- **Derived column**: A column whose value is computed at write time from a source of truth elsewhere in the record. Here, `issued_year` is derived from `csl_json["issued"]`. The source of truth remains the CSL-JSON blob; the derived column is a denormalized copy for indexed queries.
- **Denormalized indexed fields**: Columns added to the `documents` table specifically so SQL indexes can serve common queries. Existing examples: `title`, `authors`, `issued_date`. All are populated by `_extract_indexed_fields()` in `library.py`.
- **CSL-JSON `issued` field**: The bibliographic date, represented in one of several shapes: `{"date-parts": [[2023, 6, 15]]}`, `{"date-parts": [[2023]]}`, `{"literal": "Spring 2023"}`, or `{"raw": "2023-06"}`. Our year extraction handles `date-parts` primarily (the common case produced by Zotero and our metadata pipeline); other shapes yield NULL.
- **Schema migration**: A function that advances the database schema from one version to the next. `storage.py` has `migrate_schema()` that dispatches to `_migrate_vN_to_vN+1()` functions; `init_schema()` auto-runs pending migrations on library startup. `SCHEMA_VERSION` is the current target version.
- **Backfill**: The part of a migration that populates new columns for pre-existing rows. For `issued_year`, backfill parses `issued_date` text (which is already normalized to "YYYY", "YYYY-MM", or "YYYY-MM-DD" format by the existing metadata pipeline) and extracts the leading 4 digits.
- **NULL year semantics**: Documents where year extraction fails (missing `issued`, unparseable shape, malformed `issued_date`) have `issued_year = NULL`. These are excluded from `year=YYYY` filters and included only via the explicit `year_missing=True` flag. This prevents silently hiding documents the user may want to fix.

## Architecture

### Schema v4

Single column addition to `documents`:

```sql
-- Added in _migrate_v3_to_v4
ALTER TABLE documents ADD COLUMN issued_year INTEGER;
CREATE INDEX idx_documents_issued_year ON documents(issued_year);
```

Backfill in the same migration:

```sql
-- Populate from already-normalized issued_date
UPDATE documents
SET issued_year = CAST(SUBSTR(issued_date, 1, 4) AS INTEGER)
WHERE issued_date IS NOT NULL
  AND issued_date GLOB '[0-9][0-9][0-9][0-9]*';
```

The `GLOB` pattern ensures we only parse `issued_date` values that start with four digits (which covers the normalized "YYYY", "YYYY-MM", "YYYY-MM-DD" outputs of `_extract_issued_date()` in `metadata.py`). Malformed values (legacy literals, partial dates like "XXXX", etc.) stay NULL.

### Year extraction utility

Refactor `_extract_year_for_citekey()` in `metadata.py` (currently lines 228-246) by extracting the core parsing into a new shared function:

```python
def extract_year_from_csl(csl_json: dict) -> int | None:
    """Extract the publication year from a CSL-JSON blob.

    Handles the common CSL-JSON issued shapes:
    - {"date-parts": [[2023, ...]]} → 2023
    - {"date-parts": [[2023]]} → 2023
    - {"date-parts": [[]]} or {"date-parts": []} → None

    Other shapes ({"literal": "..."}, {"raw": "..."}) return None
    rather than attempting ambiguous regex parsing.

    Returns:
        Year as integer, or None if not extractable.
    """
```

`_extract_year_for_citekey()` becomes a thin wrapper that calls `extract_year_from_csl()` and converts the int to the string format citekeys want (or empty string on None). This preserves existing tests and behavior.

### Write path: `_extract_indexed_fields()`

Current signature in `library.py:1103-1114` (approximate) extracts title, authors, issued_date. Extend to also extract `issued_year` using the new utility:

```python
def _extract_indexed_fields(csl_json: dict) -> dict:
    # existing: title, authors, issued_date
    issued_year = extract_year_from_csl(csl_json)  # int | None
    return {
        "title": ...,
        "authors": ...,
        "issued_date": ...,
        "issued_year": issued_year,
    }
```

All three write paths (`Library.add()`, `_attempt_metadata_upgrade()`, `update_metadata()`) already go through this function, so no drift is possible.

### `update_document_metadata()` storage signature

Current signature accepts `title`, `authors`, `issued_date`. Add `issued_year: int | None = None`:

```python
def update_document_metadata(
    conn: sqlite3.Connection,
    doc_id: UUID,
    csl_json: dict,
    citekey: str | None = None,
    title: str | None = None,
    authors: str | None = None,
    issued_date: str | None = None,
    issued_year: int | None = None,  # NEW
    metadata_source: MetadataSource | None = None,
) -> None:
    ...
    UPDATE documents
    SET csl_json = ?,
        citekey = COALESCE(?, citekey),
        title = COALESCE(?, title),
        authors = COALESCE(?, authors),
        issued_date = COALESCE(?, issued_date),
        issued_year = COALESCE(?, issued_year),  -- NEW
        ...
```

The COALESCE pattern is consistent with existing fields: partial updates don't clobber existing values with NULL.

### `Library.list()` signature

Current:

```python
def list(self, status: DocumentStatus | None = None) -> list[Document]:
```

New:

```python
def list(
    self,
    status: DocumentStatus | None = None,
    year: int | None = None,
    year_missing: bool = False,
    author_contains: str | None = None,
    title_contains: str | None = None,
    citekey_prefix: str | None = None,
) -> list[Document]:
```

Behavior:
- All filters optional; multiple filters combine with AND
- `year` and `year_missing` are mutually exclusive; passing both raises `ValueError` at the Python layer (fail fast, clear error)
- Substring filters (`author_contains`, `title_contains`) use case-insensitive `LIKE '%...%'` with proper escaping of `%` and `_` in the input
- `citekey_prefix` uses case-insensitive `LIKE 'prefix%'` with escaping
- Ordering unchanged: `created_at DESC`

### SQL query construction

The query building in `list_documents()` in `storage.py` currently uses a single optional WHERE clause. Extend to a dynamic WHERE clause built from a list of predicates:

```python
predicates = []
params = []

if status is not None:
    predicates.append("status = ?")
    params.append(status.value)

if year_missing:
    predicates.append("issued_year IS NULL")
elif year is not None:
    predicates.append("issued_year = ?")
    params.append(year)

if author_contains:
    predicates.append("LOWER(authors) LIKE ? ESCAPE '\\'")
    params.append(f"%{_escape_like(author_contains.lower())}%")

# ... similar for title_contains, citekey_prefix

where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
query = f"SELECT ... FROM documents {where} ORDER BY created_at DESC"
```

The `_escape_like()` helper escapes `%`, `_`, and `\` in user input to prevent accidental wildcard injection from innocent queries (e.g., `author_contains="O'Connor & 50%"` shouldn't match everything).

### CLI surface

`local-library list` gains:

```
--year YEAR                    Filter to documents issued in YEAR (e.g., 2023)
--year-missing                 Filter to documents with no known year
--author-contains TEXT         Filter to authors containing TEXT (case-insensitive)
--title-contains TEXT          Filter to titles containing TEXT (case-insensitive)
--citekey-prefix TEXT          Filter to citekeys starting with TEXT (case-insensitive)
```

Existing flags (`--status`, `--limit`, `--all`, `--json`) are unchanged. `--help` text is updated to describe all filters and mention they combine with AND.

### MCP tool surface

`list_documents` gains corresponding keyword parameters:

```python
def list_documents(
    status: str | None = None,
    year: int | None = None,
    year_missing: bool = False,
    author_contains: str | None = None,
    title_contains: str | None = None,
    citekey_prefix: str | None = None,
    limit: int = 20,
) -> str:
```

Tool description updated to enumerate the filter parameters so Claude has visibility into what's queryable. Limit remains clamped 1-100.

### Migration messaging

`migrate_schema()` currently has minimal logging. Enhance so that:

- **On migration start**: `logger.info(f"Migrating database from schema v{current} to v{target}...")`
- **On each step**: `logger.info(f"Running _migrate_v{n}_to_v{n+1}...")`
- **On success**: `logger.info(f"Database migration complete (now at schema v{target})")`
- **On failure**: raise `StorageError` with code `SCHEMA_MIGRATION_FAILED` and a message describing what step failed and suggesting the user back up `library.db` before retrying

The CLI-level error wrapping will surface this cleanly; the MCP context will have it in stderr.

### Testing strategy

Tests live in `tests/unit/test_storage.py` (migration) and `tests/unit/test_library.py` (list filters):

**Migration tests**:
- Create a v3 database with hand-crafted documents (variety of `issued_date` formats, including NULL, "2023", "2023-06-15", "XXXX", "Spring 2023")
- Run `init_schema()` (which auto-invokes `migrate_schema()`)
- Assert schema version is 4
- Assert `issued_year` column exists and has expected values per row
- Assert `idx_documents_issued_year` index exists
- Assert existing data unchanged (title, authors, etc.)

**List filter tests** (combinations, not exhaustive cross-product):
- `year=2023` returns only documents with `issued_year = 2023`
- `year_missing=True` returns only documents with `issued_year IS NULL`
- `year` + `year_missing` raises ValueError
- `author_contains="Zippel"` is case-insensitive, matches substring, doesn't match unrelated authors
- `author_contains="50%"` is treated literally, doesn't match all documents
- `title_contains` similar
- `citekey_prefix="Bourdieu"` matches `@Bourdieu1984`, `@BourdieuPasseron1970`
- Multiple filters combine with AND
- Empty result set returns empty list, not error

## Implementation Phases

This work fits into a single phase — the surface is small and cohesive. Implementation plan will break it into tasks, but there is no natural cut point for a phase boundary.

### Phase 1: Schema migration + filter expansion

All changes land together:

1. **Schema migration** (`_migrate_v3_to_v4` in `storage.py`): add column, add index, backfill via SQL UPDATE
2. **Year extraction utility** (`extract_year_from_csl` in `metadata.py`): new shared function; refactor `_extract_year_for_citekey` to use it
3. **Write path** (`_extract_indexed_fields` in `library.py`): populate `issued_year`
4. **Storage write signature** (`update_document_metadata` in `storage.py`): accept `issued_year` parameter
5. **Storage query** (`list_documents` in `storage.py`): dynamic WHERE clause with escaping
6. **Library.list() signature**: new filter parameters, mutual exclusion check
7. **CLI flags** (`cli/list.py`): new options, help text
8. **MCP tool parameters** (`mcp/server.py`): new kwargs, updated tool description
9. **Tests**: migration, filter combinations, NULL handling, edge cases
10. **Docs**: `core/CLAUDE.md`, `mcp/CLAUDE.md`, root `CLAUDE.md`
11. **Migration logging**: informational messages via existing `logger`

## Additional Considerations

### Interaction with extraction metadata persistence

The roadmap carries a separate polish item: "Extraction metadata persistence — schema v4 migration for duration/device/fallback tracking in the DB." That work was deferred to a separate design pass by the extraction-resilience design (explicit decision in `docs/design-plans/2026-04-15-extraction-resilience-and-metadata-pipeline.md`). It has open design questions (column layout vs. separate table, device representation, reextract semantics) that would bottleneck this work. The filter work claims v4 first; the extraction metadata work will take v5 when it's designed.

### Schema version numbering drift

No conflict exists: v4 is currently unassigned, and the two pending schema changes can be done in sequence. If the extraction metadata work happens to be designed before this plan executes, the numbering can be swapped — there's nothing intrinsically "first" about either.

### Future filter extensions

The named-parameter approach will scale comfortably to a few more fields (primary author surname, collection membership, has-notes flag) without becoming unwieldy. If the filter surface grows to ~10+ parameters or acquires more expressive operators (greater-than, regex, OR combinations), revisit with a filter-object or query-DSL design at that point. Premature abstraction would be worse than the current direct approach.

### Tag filtering

Not covered here. Tags require a separate many-to-many schema (tags table + document_tags junction) and filter semantics (AND vs. OR across tags, source filter for auto-tags, confidence threshold). That work belongs to the Automated Content Analysis feature area and will get its own design pass.

### Full-text vs. substring

`author_contains` and `title_contains` use LIKE, not FTS5. Reasons:
- LIKE is fine for this use case (bounded to one column, short text, case-insensitive) and doesn't require schema changes
- FTS5 already indexes chunk text for full-content search; reusing it for metadata filtering would conflate two concerns
- If substring matching becomes too slow at corpus scale (~1400 docs, unlikely to matter), we can add a `documents_meta_fts` virtual table as a follow-up without breaking the filter API

### CLI flag ergonomics

Using `--author-contains` with a space-separated value feels verbose but is explicit and unambiguous. Alternatives considered and rejected:
- Positional argument (`list Zippel`): ambiguous — is it title, author, citekey?
- Unified `--query TEXT` that searches across fields: makes behavior harder to predict
- Shortened flag (`-a TEXT`): `-a` is too close to `--all` (already reserved for pagination)

The explicit form is what we ship.
