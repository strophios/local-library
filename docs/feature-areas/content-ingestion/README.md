# Content Ingestion

Last updated: 2026-04-16

## Vision

Everything in the library — PDFs, web articles, EPUBs, plain text — goes through a consistent pipeline: acquire, extract, extract metadata, embed. Each content type gets a citekey and becomes searchable, citable, and queryable. The ingestion protocols already support this polymorphism; this area is about filling in the handlers and enriching the metadata side.

The guiding principle: adding a new content type means implementing `ContentAcquirer` and `ContentExtractor`, not modifying the core pipeline.

## Current State

The ingestion pipeline works well for PDFs: `FileAcquirer` copies files, `PdfExtractor` extracts via Marker (with pre-check, dynamic timeout, and pdftext fallback), `MetadataHandler` validates CSL-JSON, and `TextMetadataExtractor` derives metadata from the extracted text when nothing explicit is provided. The `MetadataSource` provenance pipeline tracks where each document's metadata came from (ZOTERO, EXPLICIT, FILENAME, TEXT_EXTRACTED) so that upgrades are safe and citekey stability is preserved.

Web, EPUB, and other non-PDF content types aren't yet supported. Metadata extraction is heuristic + optional LLM; there's no external API enrichment (CrossRef, GROBID, OpenAlex).

## Near-Term (next to build)

### MVP web ingestion

A minimal but complete path: `add <url>` downloads, extracts, and ingests.

**Components:**
- **Web acquirer**: Download HTML from URL. Options:
  - trafilatura (primary choice per CLAUDE.md) — handles download + extraction in one step
  - Separate download (requests/httpx) + extraction (trafilatura or readability-lxml)
  - Consider SingleFile CLI for JavaScript-heavy pages (mentioned in `project_breakdown.md`)
  - See also: `~/bin/web2md.py`, an existing minimal script used for job descriptions
- **Web extractor**: HTML → clean markdown. trafilatura does this natively; quality is good for article-style content.
- **Metadata extraction**: Open Graph tags (`og:title`, `og:author`, `og:published_time`) first. Fall back to the existing `TextMetadataExtractor` for pages without OG tags.
- **URL handling**: Normalization, deduplication (by normalized URL and by content hash).
- **Storage**: Persist original HTML, extracted markdown, or both?
- **Citekey generation**: Same pattern as PDFs (author + year + first title word), but "author" may be a site name for unsigned content.

**Key design decisions to make:**
- Store original HTML or just extracted markdown? HTML enables re-extraction if the pipeline improves; markdown-only is simpler and smaller.
- CSL-JSON type for web content: `webpage`, `post-weblog`, `article-newspaper`? Or a generic type with user override?
- URL normalization strategy (strip tracking params, www prefix, etc.)

## External API Metadata Enrichment

Text-based metadata extraction (M3b) covers the common case. For documents where heuristics produce uncertain or incomplete results, external APIs would fill the gap. The pipeline can treat API enrichment as a conditional upgrade path, similar to the FILENAME → TEXT_EXTRACTED upgrade that already exists for filename-parsed metadata.

**Why this isn't built yet:** Text extraction was evaluated first to avoid adding network dependencies prematurely. Now that the corpus is imported at scale, it's clearer which documents have weak metadata and whether API enrichment would actually move the needle.

**Architecture sketch:**
```
Text extraction (M3b) → confidence score
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   High confidence     Medium confidence    Low confidence
   (use extracted)     (try API enrich)    (require API or manual)
                            │
                            ▼
                    ┌───────────────┐
                    │  API cascade  │
                    │ DOI → CrossRef│
                    │ else → GROBID │
                    │ else → OpenAlex│
                    └───────────────┘
```

**API candidates:**
- **CrossRef**: Lookup by DOI (reliable) or title/author query (fuzzy). Free, 50 req/sec polite pool.
- **GROBID**: Structured header extraction from PDFs. More accurate than heuristics but requires running a GROBID server locally or remote.
- **OpenAlex**: Open scholarly metadata, good coverage of recent publications.

**Design considerations:**
- Caching layer (by content hash or DOI) to avoid redundant calls
- Rate limiting per API
- Graceful degradation when APIs are unavailable
- Confidence thresholds: at what level to auto-accept vs. flag for review?
- Integration with `MetadataSource`: add an `API_ENRICHED` source? Or just update TEXT_EXTRACTED with higher confidence?

**Decision point:** Spot-check a sample of imported documents for metadata quality before committing. If text-based extraction achieves >85% accuracy on indexed fields (title, authors, date), API enrichment may be unnecessary for most use cases and can stay deferred.

## Longer-Term Ideas

### Additional content types

- **EPUB** — ebooklib or calibre's ebook-convert. Natural next step after web ingestion.
- **HTML files** (local) — reuse the web extractor without the download step.
- **Plain text** — pass-through, minimal work.
- **MOBI** — requires conversion, lower priority than EPUB.

Each new handler implements `ContentAcquirer` + `ContentExtractor`. No core changes needed.

### Web ingestion extensions

- **JavaScript-heavy pages**: SingleFile CLI or a headless browser for SPAs and dynamically-rendered content
- **Link rot protection**: Save to Archive.org on ingest, store archive URL as fallback
- **Batch URL import**: Add multiple URLs from a file or clipboard
- **RSS/feed monitoring**: Watch feeds and auto-ingest new articles
- **Reader mode improvements**: Better extraction for non-standard layouts (forums, documentation sites, etc.)

## Open Questions

- How well does trafilatura handle the content likely to be ingested? (Academic blog posts, tech blog posts, news articles, documentation pages) — worth a quick evaluation before committing.
- Should web content go through the same embedding pipeline as PDFs, or does the typically shorter length of web articles suggest different chunking parameters?
- The existing `ContentExtractor` protocol returns markdown text. Does web extraction fit this interface cleanly, or does it need additional return values (e.g., extracted metadata alongside text)?
- Is API metadata enrichment worth building, or is text-based extraction already good enough at corpus scale? Spot-checks on the imported corpus should inform this.

## Dependencies

**Provides to other areas:**
- Web content becomes searchable and citable (benefits Neovim Citation Workflow)
- Web content can have notes (benefits Note Management)
- API-enriched metadata improves search/display quality across the library

**Needs from other areas:**
- Phase 1 quality gate complete (done)
- Existing ingestion protocols (`ContentAcquirer`, `ContentExtractor`) — already in place
- Metadata provenance pipeline (done, as part of extraction resilience work)

## References

- `src/local_library/ingestion/base.py` — protocol definitions
- `src/local_library/ingestion/text_extraction.py` — `TextMetadataExtractor` (the piece API enrichment would supplement)
- `project_breakdown.md` — early notes on web ingestion flow
- `RAG_background/00_final_summary_report.md` § Section 1 — extraction discussion (PDF-focused but relevant patterns)
