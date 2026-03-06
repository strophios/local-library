# Web Content Ingestion

Last updated: 2026-03-06

## Vision

Ingest web articles, blog posts, and other URL-based content into the library with the same ease as PDFs. Everything in the library gets a citekey and becomes searchable, citable, and queryable — regardless of whether it originated as a PDF or a web page.

The goal is that adding a blog post requires only a URL.

## Current State

The ingestion pipeline is built for PDFs: `FileAcquirer` copies files, `PdfExtractor` extracts via Marker, `MetadataHandler` validates CSL-JSON and generates citekeys. The architecture uses protocols (`ContentAcquirer`, `ContentExtractor` in `ingestion/base.py`), so adding new content types means implementing new protocol satisfiers, not modifying existing code.

No web-specific code exists yet.

## Near-Term (next to build)

### MVP Web Ingestion

A minimal but complete path: `add <url>` downloads, extracts, and ingests.

**Components:**
- **Web acquirer**: Download HTML content from URL. Options:
  - trafilatura (mentioned in CLAUDE.md as primary choice) — handles download + extraction in one step
  - Separate download (requests/httpx) + extraction (trafilatura or readability-lxml)
  - Consider: SingleFile CLI for JavaScript-heavy pages? (mentioned in `project_breakdown.md`)
- **Web extractor**: HTML → clean markdown. trafilatura does this natively. Quality is generally good for article-style content.
- **Metadata extraction**: Open Graph tags (`og:title`, `og:author`, `og:published_time`) are the primary source. Fall back to text-based extraction (existing `TextMetadataExtractor`) for pages without OG tags.
- **URL handling**: Normalization, deduplication (by normalized URL and by content hash)
- **Storage**: What to persist — the original HTML? Just the extracted markdown? Both?
- **Citekey generation**: Needs to work for web content (author + year + first title word, same pattern, but "author" might be a site name for unsigned content)

**Key design decisions to make:**
- Store original HTML or just extracted markdown? HTML enables re-extraction if the pipeline improves; markdown-only is simpler and smaller.
- CSL-JSON type for web content: `webpage`, `post-weblog`, `article-newspaper`? Or a generic type with optional user override?
- URL normalization strategy (strip tracking params, www prefix, etc.)
- Archive.org integration for link rot protection? (mentioned in `future_roadmap.md` — probably defer)

## Longer-Term Ideas

- **JavaScript-heavy pages**: SingleFile CLI or a headless browser for SPAs and dynamically-rendered content
- **Link rot protection**: Save to Archive.org on ingest, store archive URL as fallback
- **Batch URL import**: Add multiple URLs from a file or clipboard
- **RSS/feed monitoring**: Watch feeds and auto-ingest new articles
- **Reader mode improvements**: Better extraction for non-standard layouts (forums, documentation sites, etc.)

## Open Questions

- How well does trafilatura handle the kinds of content likely to be ingested? (Academic blog posts, tech blog posts, news articles, documentation pages) — worth a quick evaluation before committing
- Should web content go through the same embedding pipeline as PDFs, or does the typically shorter length of web articles suggest different chunking parameters?
- The existing `ContentExtractor` protocol returns markdown text. Does web extraction fit this interface cleanly, or does it need additional return values (e.g., extracted metadata alongside text)?

## Dependencies

**Provides to other areas:**
- Web content becomes searchable and citable (benefits Neovim Citation Workflow)
- Web content can have notes (benefits Note Management)

**Needs from other areas:**
- Phase 1 quality gate should be complete first (pipeline proven before extending to new content types)
- Existing ingestion protocols (`ContentAcquirer`, `ContentExtractor`) — already in place

## References

- `future_roadmap.md` § "Web Content Ingestion" — original description
- `project_breakdown.md` — early notes on web ingestion flow
- `RAG_background/00_final_summary_report.md` § Section 1 — extraction discussion (PDF-focused but relevant patterns)
- `src/local_library/ingestion/base.py` — protocol definitions
