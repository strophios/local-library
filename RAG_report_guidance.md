# RAG System Report Guidance

This document captures the requirements, constraints, and priorities for building the RAG (Retrieval-Augmented Generation) system as part of the local-library project. It serves as the reference for evaluating options and making recommendations.

## Project Context

The RAG system is a core component of a personal knowledge management system that:
- Ingests diverse digital documents (primarily academic PDFs, but also web articles)
- Manages bibliographic metadata in CSL-JSON format (Zotero-compatible)
- Provides ML-based auto-tagging and semantic search
- Serves as a queryable knowledge base for LLM interactions

The system must be **self-sufficient** (functions without Zotero) while maintaining **Zotero interoperability** (can import from and export tags back to Zotero).

## RAG Pipeline Components

The system requires implementations for five sequential stages:

### 1. PDF → Markdown Extraction
**Goal**: Convert academic PDFs into well-structured markdown suitable for semantic processing.

**Quality requirements** (paramount):
- Accurate heading hierarchy (crucial for intelligent chunking)
- Clean separation of body content from headers/footers/page numbers
- Proper handling of references/bibliography sections (likely want to delimit or omit)
- Reasonable handling of tables and figures (at minimum, indicate their presence)
- Academic PDF features: equations, multi-column layouts, footnotes

**Scale**: ~1400 items currently, growing continuously. Many items 10k+ words. Eventually books.

### 2. Markdown → Embeddings
**Goal**: Convert extracted text into vector representations that capture semantic meaning.

**Considerations**:
- Chunking strategy: size, overlap, semantic boundaries (headings, paragraphs)
- Embedding model selection: local vs. API, dimensionality, domain specificity
- Metadata preservation: chunks must link back to source document, page, section

**Constraints**:
- API costs acceptable if quality justifies (budget ~$0.50-1.00 for full library embedding is reasonable)
- Must support re-embedding as models improve or library grows

### 3. Embedding Storage & Retrieval
**Goal**: Store vectors efficiently and retrieve them quickly via similarity search.

**Performance requirements**:
- < 500ms query latency (for interactive use cases like citation autocomplete)
- Efficient for library size: thousands of documents → potentially hundreds of thousands of chunks
- Must scale gracefully as library grows

**Technical preferences**:
- SQLite-based solutions preferred for portability (sqlite-vss mentioned in project docs)
- Single-file database ideal for backup/portability
- Must support metadata filtering (e.g., search only within certain tags, date ranges)

### 4. LLM Query Interface
**Goal**: Provide retrieved context to LLMs for augmented generation.

**Requirements**:
- LLM-agnostic: must work with Claude API, OpenAI, local models (Ollama/llama.cpp)
- Clean interface that other tools can consume
- Context assembly: intelligent selection and ordering of retrieved chunks
- Token budget management: fit within context windows of various models

### 5. Citation-Specific Tooling
**Goal**: Academic workflow integration beyond generic RAG.

**Use cases to support**:
1. **Citation suggestion**: Given a sentence/claim, find citable sources from the library
2. **Autocomplete integration**: Real-time citation suggestions in Neovim (< 500ms latency)
3. **Citation verification**: Check that cited works actually support the citing text
4. **Contradiction detection**: Flag library sources that contradict claims in a manuscript
5. **Bibliography awareness**: Understand citekeys, link to bibliographic metadata

**Note**: These are downstream applications. The core RAG infrastructure must be designed to enable them, but they're separate implementation concerns.

## Constraints & Priorities

### Hard Constraints
- **Portability**: Must be easy to backup, migrate, and run on different machines
- **Transparency**: Data formats should be inspectable and recoverable (no opaque binary blobs as sole storage)
- **Clean interface**: API/CLI that other tools can integrate with (Neovim, scripts, other agents)
- **Language**: Python or Rust (Python likely primary; Rust for performance-critical components if needed)

### Soft Constraints / Preferences
- **Local-first**: Prefer local processing and storage; API acceptable where quality gains justify
- **Single-file databases**: SQLite preferred over client-server databases for simplicity
- **Standard formats**: CSL-JSON for metadata, markdown for extracted content, standard embedding formats

### Performance Targets
- **Embedding**: Can be batch processed; speed not critical (overnight processing acceptable)
- **Retrieval**: < 500ms for interactive use
- **PDF extraction**: Quality over speed; minutes per document acceptable for high quality

### Hardware Context
- 2021 MacBook Pro, M1 Pro chip
- Local LLM inference possible but constrained (7B-13B models practical)
- Local embedding models feasible (sentence-transformers run well on M1)

## Evaluation Criteria for Options

When comparing approaches, evaluate on:

1. **Quality**: How good are the results? (extraction accuracy, embedding relevance, retrieval precision)
2. **Complexity**: How hard to implement, maintain, debug?
3. **Portability**: How easy to backup, migrate, share?
4. **Performance**: Does it meet latency/throughput requirements?
5. **Cost**: Ongoing API costs, compute requirements
6. **Extensibility**: How easy to swap components, add features, integrate with other tools?
7. **Ecosystem maturity**: Is the tooling stable? Actively maintained? Well-documented?

## Report Deliverables

The report should provide:

1. **Component-by-component analysis**: For each pipeline stage, survey available options
2. **Comparative evaluation**: Strengths, weaknesses, tradeoffs of each approach
3. **Three recommendations per component**:
   - **Easiest**: Lowest barrier to working system; may sacrifice some quality/features
   - **Best**: Highest quality regardless of effort; the "right" answer if time/effort unlimited
   - **Optimal ROI**: Best balance of effort vs. result for this specific use case
4. **Integration considerations**: How do component choices affect each other?
5. **Implementation sketch**: High-level architecture for the recommended path

## Open Questions to Address

- How much do embedding model choice and chunking strategy interact? (i.e., is there a best-practice pairing?)
- What's the state of the art in academic PDF extraction? Has it improved significantly recently?
- sqlite-vss vs. alternatives: is it production-ready? What are the tradeoffs?
- How do hybrid approaches (local + API) work in practice? Worth the complexity?
- What's the practical difference between embedding models? (Is OpenAI's ada-002 meaningfully better than local alternatives for this use case?)

## Integration with local-library

The RAG system is one layer of the broader architecture (per CLAUDE.md):

```
1. Storage layer         ← RAG database lives here alongside main SQLite schema
2. Ingestion layer       ← PDF extraction feeds into RAG pipeline
3. Zotero import         ← Source of initial documents
4. Note management       ← Notes could also be embedded
5. Embedding pipeline    ← Core RAG component
6. Auto-tagging          ← Consumes RAG for similarity-based suggestions
7. RAG interface         ← Query layer
8. Zotero export         ← Out of scope for RAG system
```

The RAG system should be designed as a coherent subsystem that integrates cleanly with the broader local-library architecture but could theoretically be extracted or replaced.
