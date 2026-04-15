# Core Domain

Last verified: 2026-04-15

## Purpose

Owns the document lifecycle: what a document IS (models), how it's persisted (storage), and how operations are orchestrated (Library). All other domains depend on core for document identity.

## Contracts

- **Exposes**: Document, DocumentStatus (PENDING, READY, FAILED, NEEDS_REVIEW), EmbeddingStatus (PENDING, CURRENT, STALE), MetadataSource (ZOTERO, EXPLICIT, FILENAME, TEXT_EXTRACTED), RAGResponse, AddResult, FieldExtraction, TextExtractionResult, ErrorCode hierarchy (including EXTRACTION_FALLBACK, MetadataError, ZoteroError, EmbeddingError, LLMError, RAGError), Library class (with get_by_citekey, get_all_citekeys, update_metadata, embed, embed_all, get_retriever, query, query_stream; reranking enabled by default), storage functions, vec_extension module
- **Guarantees**:
  - Document.id is UUID, globally unique
  - Document.content_hash is SHA-256, content-addressable
  - AddResult returns existing document on duplicate (idempotent adds)
  - All errors inherit LocalLibraryError with ErrorCode for programmatic handling
  - Library dispatches to appropriate handler via `can_handle()` protocol
  - Library.add() accepts optional CSL-JSON metadata; validates and stores with collision-free citekeys
  - Library.add() accepts optional citekey parameter to preserve external citekeys (e.g., from Zotero); bypasses citekey generation when provided
  - Library.add() accepts optional metadata_source parameter (MetadataSource enum) for provenance tracking
  - Library.add() persists preliminary metadata BEFORE extraction — FAILED documents retain citekey and basic metadata
  - Library.add() uses parse_filename_metadata() for bare paths (no explicit metadata) to generate best-effort CSL-JSON
  - Library.add() conditionally upgrades FILENAME-sourced metadata after extraction via text extraction pipeline
  - ZOTERO/EXPLICIT metadata is authoritative and never upgraded by text extraction
  - Metadata upgrades that would change the citekey flag NEEDS_REVIEW instead of auto-applying (citekey stability)
  - Documents with low-confidence extraction are set to NEEDS_REVIEW status
  - Documents using pdftext fallback are set to NEEDS_REVIEW with EXTRACTION_FALLBACK error code
  - Library accepts `pdf_llm_enabled` parameter to enable Marker LLM-enhanced extraction for PDFs
  - Library accepts `progress_callback` parameter, forwarded to default PdfExtractor for extraction progress events
  - EmbeddingStatus tracks embedding lifecycle (PENDING → CURRENT, CURRENT → STALE on re-extraction, STALE → CURRENT on re-embed)
  - sqlite-vec extension loaded conditionally; library functions without it for document storage (graceful degradation)
  - Library.embed() computes and stores embeddings, updates status to CURRENT
  - Library.embed_all() processes all PENDING/STALE documents
  - Library.delete() cascades to remove embeddings
  - Library.add() embeds by default when embed_on_add=True and sqlite-vec available
  - Library.get_retriever(mode, rerank=True) factory method returns Retriever protocol-compliant instances; wraps with RerankedRetriever by default (cross-encoder reranking)
  - Library.query(rerank=True) retrieves context chunks and generates a RAG answer (blocking); returns RAGResponse
  - Library.query_stream(rerank=True) retrieves context chunks and returns RAGStream for token-by-token answer generation
  - Library accepts `rag_model` parameter (default: "gemini/gemini-2.0-flash") for RAG query LLM selection
  - RAGInterface lazily initialized on first query() or query_stream() call
- **Expects**: Sources handled by at least one registered acquirer; files handled by at least one extractor

## Dependencies

- **Uses**: `config` (paths), `ingestion` (ContentAcquirer, ContentExtractor protocols, MetadataHandler, TextMetadataExtractor, cleanup_markdown, clean_artifacts), `embeddings` (MarkdownChunker, NomicEmbedder, EmbeddingStorage, CrossEncoderReranker, RerankedRetriever), `llm` (LLMClient, LiteLLMClient), `rag` (RAGInterface, RAGStream)
- **Used by**: `cli`, `embeddings` (retrieval module imports from core.errors), `rag` (imports RAGResponse, ErrorCode)
- **Boundary**: Core MUST NOT import from cli

## Key Decisions

- **Frozen dataclasses**: Document and result types are immutable (Functional Core pattern)
- **ErrorCode enum**: Machine-parseable error codes enable retry logic and user feedback
- **Idempotent adds**: Duplicate detection by path AND hash prevents data duplication
- **Status lifecycle**: PENDING -> READY, FAILED, or NEEDS_REVIEW tracks extraction state. NEEDS_REVIEW indicates extraction succeeded but confidence is low.
- **Handler injection**: Library accepts `acquirers` and `extractors` lists via constructor (defaults: FileAcquirer, PdfExtractor)
- **PDF LLM extraction config**: Library accepts `pdf_llm_enabled` parameter (default False) passed to default PdfExtractor. Custom extractors (passed via constructor) are not affected.
- **Protocol dispatch**: `_find_acquirer()` and `_find_extractor()` iterate handlers, first `can_handle()` wins
- **Lazy Library import**: `core.__init__` uses `__getattr__` to defer Library import until first access. Breaks circular dependency: `core.__init__` -> `core.library` -> `ingestion.pdf` -> `core.errors`. Eager imports for models/errors remain since they don't cause cycles.
- **Citekey collision handling**: `get_unique_citekey()` appends suffixes (a, b, c...) to ensure uniqueness
- **Citekey preservation**: Library.add() accepts optional `citekey` parameter that bypasses generation. Used when importing from external systems (Zotero) to preserve existing citekeys for deduplication
- **Metadata pipeline reordering**: Library.add() persists preliminary metadata before extraction via `_persist_preliminary_metadata()`. For bare paths, uses `parse_filename_metadata()`. After extraction, `_attempt_metadata_upgrade()` conditionally upgrades FILENAME-sourced metadata via text extraction. ZOTERO/EXPLICIT metadata is authoritative — never upgraded.
- **MetadataSource tracking**: `_metadata_source` field in CSL-JSON tracks provenance (ZOTERO, EXPLICIT, FILENAME, TEXT_EXTRACTED). Determines whether text extraction should attempt metadata upgrade.
- **Citekey stability**: If metadata upgrade would change an existing citekey, the document is flagged NEEDS_REVIEW instead of auto-applying the change. Preserves referential stability.
- **Two-stage cleanup in add()**: Library.add() applies `clean_artifacts()` then `cleanup_markdown()` between Marker extraction and disk write. Artifact removal first (content quality), formatting second (markdown structure). Cleaned text is used for both the stored markdown file and metadata extraction
- **Citekey lookup**: Library.get_by_citekey() returns Document or None; Library.get_all_citekeys() returns all non-null citekeys
- **Metadata updates**: Library.update_metadata() allows updating status, citekey, and csl_json with automatic indexed field extraction
- **EmbeddingStatus enum**: Tracks embedding state separately from DocumentStatus (orthogonal concerns)
- **Conditional sqlite-vec**: Extension loaded only when available; graceful degradation allows library to function for document storage even without vector search
- **Cascade deletion**: Chunks and embeddings deleted via ON DELETE CASCADE foreign key when parent document deleted
- **Embedding integration**: Library orchestrates chunking→embedding→storage pipeline; graceful failure on add (document usable, just not vector-searchable)
- **embed_on_add config**: Defaults to True; controlled via Library constructor parameter
- **LLMClient injection**: Library creates LLMClient at Library level for text extraction (if enabled) and RAG queries. TextMetadataExtractor receives LLMClient via constructor injection rather than managing its own LiteLLM dependency
- **Lazy RAG initialization**: RAGInterface and its LLMClient created on first query()/query_stream() call, avoiding unnecessary LLM client setup when only doing document management
- **Reranking by default**: get_retriever(rerank=True) wraps base retriever with RerankedRetriever; _get_reranker() lazily initializes CrossEncoderReranker on first use. Cross-encoder model loaded on first rerank call, not at Library construction
- **Rerank parameter forwarding**: query() and query_stream() accept rerank parameter, forwarded to get_retriever()
- **RAGResponse dataclass**: Frozen dataclass capturing question, answer, context_chunks (tuple of SearchResult), model, and retrieval_mode for display and serialization

## Invariants

- Every Document has exactly one status (PENDING, READY, FAILED, or NEEDS_REVIEW)
- content_hash uniquely identifies file content (no two documents share a hash)
- storage_path follows Git-style layout: `ab/cd/abcdef...ext`
- All timestamps are UTC
- Handler dispatch order matters: first matching handler wins
- NEEDS_REVIEW status implies extraction succeeded but needs human verification

## Key Files

- `models.py` - Document, AcquisitionResult, ExtractionResult, AddResult, FieldExtraction, TextExtractionResult, RAGResponse, EmbeddingStatus, MetadataSource
- `errors.py` - ErrorCode enum, exception hierarchy (includes ACQUISITION_*, EXTRACTION_* (incl. EXTRACTION_FALLBACK), METADATA_*, ZOTERO_*, EMBEDDING_*, RAG_*, LLM_* codes; LLMError, RAGError exceptions)
- `storage.py` - SQLite CRUD (get_connection, init_schema, create/get/update/delete), schema v3 with chunks and FTS5
- `library.py` - Library orchestrator (add, get, get_by_citekey, get_all_citekeys, list, delete, embed, embed_all, update_metadata, get_retriever, query, query_stream) with handler dispatch, preliminary metadata persistence, conditional metadata upgrade, lazy RAG initialization, and lazy cross-encoder reranking
- `vec_extension.py` - sqlite-vec extension loading, vec0 table creation, availability checking

## Gotchas

- Library.add() re-raises ExtractionError after creating FAILED record (caller sees both)
- Library.add() raises MetadataError if provided metadata fails validation (before updating record)
- get_documents_by_partial_id() is case-sensitive UUID prefix match
- storage.py functions require explicit connection parameter (no global state)
- No matching acquirer raises ACQUISITION_UNSUPPORTED_SOURCE; no matching extractor raises EXTRACTION_UNSUPPORTED_FORMAT
- `from local_library.core import Library` works but is lazy-loaded; `from local_library.core.library import Library` is direct but may trigger circular import issues if called at module level
- Library constructor accepts text_extraction_* parameters to configure automatic metadata extraction behavior; LLMClient created at Library level and injected into TextMetadataExtractor
- Library.add() persists preliminary metadata before extraction; bare paths parsed via parse_filename_metadata(). FAILED documents retain citekey and metadata.
- Library.add() accepts metadata_source parameter: ZOTERO/EXPLICIT are authoritative (never upgraded), FILENAME triggers conditional upgrade after extraction
- `_attempt_metadata_upgrade()` replaces the former `_process_text_extraction()` — only upgrades FILENAME-sourced metadata, checks citekey stability
- Library.query() and query_stream() raise RAGError on LLM generation failure and EmbeddingError if sqlite-vec unavailable
- RAGInterface lazy init means LiteLLM import only happens when RAG queries are actually used
- `pdf_llm_enabled` only affects the default PdfExtractor; custom extractors must configure LLM mode themselves
- Library.embed() raises EmbeddingError if sqlite-vec unavailable or document not READY
- Embedding failure in add() is non-fatal; document created but embedding_status stays PENDING
- embed_on_add respects sqlite-vec availability; disabled automatically if extension unavailable
- Library.get_retriever() raises EmbeddingError if sqlite-vec unavailable; factory method handles embedder lazy-init for vector/hybrid modes
- Library.get_retriever(rerank=True) is the default; callers must pass rerank=False explicitly to disable. Cross-encoder model (~50 MB) downloaded on first rerank call
- _get_reranker() is a private method; external callers should use get_retriever(rerank=True) rather than accessing the reranker directly
