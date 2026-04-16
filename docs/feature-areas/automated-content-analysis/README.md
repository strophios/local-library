# Automated Content Analysis

Last updated: 2026-04-16

## Vision

Use the library's embeddings and (optionally) LLMs to automatically organize and analyze documents: suggest tags, detect thematic clusters, and surface relationships between documents. The goal is to make a large library navigable without requiring manual curation of every document.

This area has the most prerequisites and the longest path to value — it needs a populated library, working embeddings, and ideally some manually-tagged seed documents. It's lower priority for now but has significant long-term potential.

## Current State

No automated analysis exists. The embedding pipeline (M5) and retrieval system (M6) provide the foundation: every document has vector embeddings, and similarity search works. Tags exist in the data model but no documents are tagged.

## Near-Term (next to explore)

### Auto-Tagging

The most concrete near-term capability: suggest tags for documents based on content.

**Approaches to evaluate:**
- **Nearest-neighbor**: Find similar already-tagged documents, aggregate their tags as suggestions
  - Pro: Simple, interpretable, no additional models
  - Con: Requires a seed set of manually-tagged documents; cold-start problem
- **LLM classification**: Given the document text (or summary) and an existing tag vocabulary, ask an LLM to suggest tags
  - Pro: Works without seed data; can generate new tag categories
  - Con: API cost, latency, less deterministic
- **Clustering-based**: Cluster document embeddings, identify themes per cluster, assign tags
  - Pro: Discovers structure organically
  - Con: Cluster labels need interpretation; less precise than supervised approaches

**Prerequisites:**
- A populated library (post-Phase-1 corpus import)
- Some manually-tagged documents as seed/evaluation data (for nearest-neighbor approach)
- Tag vocabulary: should there be a controlled vocabulary, or free-form tags?

### Zotero Tag Export

Push auto-generated tags back to Zotero via the local API (HTTP on port 23119).

- NEVER write to Zotero's SQLite directly (corruption/sync risk)
- Namespace auto-tags (e.g., prefix with `auto:`) to distinguish from manual tags
- See `CLAUDE.md` § "Writing to Zotero" for the integration constraints

## Longer-Term Ideas

### Dual Embeddings (RAG + Clustering)
- Maintain a second set of embeddings using the `clustering:` prefix for nomic-embed-text
- Only pursue if tagging quality measurably suffers with RAG embeddings
- Storage overhead: ~6KB per document (~185MB for 1400 docs) — not a concern
- See `RAG_background/embedding_approaches_report.md` § dual embedding strategy

### Triage-Based Verification
- "What in my library might not support this claim?" — loosely related to auto-tagging in that both use document similarity
- Actually lives closer to the Neovim Citation Workflow area; listed there as a longer-term mode
- The underlying insight: 77-78% NLI accuracy is insufficient for automated decisions but excellent for search space reduction

### Document Relationship Mapping
- Automatically identify which documents cite each other (from reference sections)
- Build a citation graph within the library
- Surface: "documents frequently co-cited with this one," "documents that cite this one"

### Thematic Clustering
- Group documents into thematic clusters based on embedding similarity
- Visualize the library's conceptual landscape
- Identify gaps in coverage

### Full Automated Claim Verification (vs. Triage)
Triage-based verification (narrowing the search space for a human) is the near-term design. Fully automated NLI-based verification — "reject commits with unsupported citations" or similar — is a different problem with a much higher accuracy bar. Out of reach with off-the-shelf NLI models (~77-78% on academic text), and probably not worth chasing unless an automated workflow specifically requires it. The path if we ever need it: build a labeled test set of 50-100 claim/source pairs, validate accuracy on academic content, potentially fine-tune. Roughly 2-4 weeks of work with meaningful risk that the result still isn't good enough. See `RAG_background/citation_tooling_report.md` § 8.2.

## Open Questions

- What tag vocabulary to use? Controlled vs. free-form has significant implications for the approach
- How to bootstrap without seed data? LLM classification is the most natural path but adds cost
- Should auto-tags have confidence scores visible to the user? (The system already supports confidence scoring for metadata extraction)
- When does this become a priority? Probably after the library is populated and in active use — the value of organization scales with library size

## Dependencies

**Provides to other areas:**
- Tags for Neovim Citation Workflow (tag-aware search)
- Tags for Zotero export
- Document relationships for richer search results

**Needs from other areas:**
- Populated library (Phase 1 quality gate complete)
- Some manual tags as seed data (user action, not a feature area deliverable)
- RAG Pipeline Improvements — embedding quality affects clustering/similarity quality

## References

- `RAG_background/embedding_approaches_report.md` — embedding strategies, dual embedding discussion
- `RAG_background/citation_tooling_report.md` § triage reframing + § 8.2 — verification approaches, NLI validation
- `CLAUDE.md` § "Writing to Zotero" — Zotero export constraints
