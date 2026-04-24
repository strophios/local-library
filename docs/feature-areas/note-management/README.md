# Note Management

Last updated: 2026-04-16

## Vision

Every document in the library can have an associated markdown note with YAML frontmatter linking back to the document record. Notes are organized, portable, and accessible outside the library system (e.g., via a plain text editor, Neovim, or any markdown-aware tool).

The near-term goal is the infrastructure: auto-generated stubs, organized layout, easy access. The longer-term goal is for notes to participate in the knowledge system — searchable, embeddable, and usable as context for queries.

## Current State

No note management exists. The `CLAUDE.md` mentions "path to markdown file with YAML frontmatter linking back to record" as part of the core data model, but nothing has been built.

The `open` CLI command exists for viewing extracted markdown and PDFs. Notes would be a natural third target for `open`.

## Near-Term (next to build)

### MVP Note Stubs

Auto-generated markdown files with YAML frontmatter, organized in a discoverable filesystem layout.

**Components:**
- **Stub generation**: Create a markdown file with YAML frontmatter containing:
  - citekey, UUID, title, authors, issued date
  - Path to extracted text, path to original file
  - Document type
  - Any tags (when tagging exists)
- **Filesystem layout**: Where do notes live?
  - Option A: Alongside extracted content in the content-addressable store — consistent but less human-browsable
  - Option B: In a `notes/` directory, named by citekey (e.g., `notes/Smith2023Attention.md`) — human-browsable, easy to find
  - Option C: User-configurable location
- **CLI integration**:
  - `open <id> --note` (or `open <id> -n`) to open the note in `$EDITOR`
  - Auto-generate stub on first open if it doesn't exist
  - Or: generate stubs at add time (with option to skip)
- **Database tracking**: Store the note path in the document record so the system knows which documents have notes

**Key design decisions to make:**
- Generate at add time vs. on first access? On-first-access avoids creating hundreds of empty stubs during bulk import.
- Filename convention: citekey-based is most human-friendly but requires handling citekey changes
- Should the frontmatter include a "last modified" field maintained by the system?

## Longer-Term Ideas

- **Notes as search context**: Embed note content alongside (or instead of) extracted text chunks, so that user annotations and summaries influence search results
- **Note templates**: Different templates for different document types (journal article, book chapter, web article)
- **Backlink tracking**: Which notes reference which other documents (via citekey)?
- **Note search**: Search across note content specifically (separate from document content search)
- **Batch note generation**: Generate stubs for all documents that don't have notes yet
- **Note status tracking**: Has this document been read/annotated? (Could be as simple as "note modified since generation")
- **Note as metadata source**: Allow for modification of document metadata through editing the associated note's YAML header fields (likely not for all metadata values but, e.g., for tags or read/unread, etc.)
- **Bidirectional Zotero note sync**: Sync notes between local markdown files and Zotero. Conflict resolution is the hard part — two independent edit streams with no natural merge. Two simpler framings worth considering first: (a) one-way sync (local → Zotero only, treating local as authoritative), which sidesteps conflict resolution entirely; (b) treat the two stores as separate with manual reconciliation. Full bidirectional is a lot of complexity for a feature whose value is unclear until notes are actually in use.

## Open Questions

- Where should notes live on the filesystem? This is the most consequential design decision for the MVP.
- Should notes be tracked in the database (path stored in document record) or purely filesystem-based (derived from citekey)?
- How to handle citekey changes? If notes are named by citekey and the citekey changes, the note file needs to be renamed or the link broken.
- When auto-tagging exists, should tags be reflected in note frontmatter? (Nice for external tools that read YAML frontmatter)

## Dependencies

**Provides to other areas:**
- Neovim Citation Workflow: "open associated note" action
- Potentially: notes as additional context for RAG queries

**Needs from other areas:**
- None for MVP — notes can be built independently against the existing document model

## References

- `CLAUDE.md` § "Core Data Model" — notes as part of the data model
