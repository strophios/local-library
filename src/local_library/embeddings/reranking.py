"""Cross-encoder reranking components.

Pure helper functions (_group_by_document, _normalize_scores) are Functional Core.
CrossEncoderReranker is Imperative Shell (ML model I/O).
"""

# pattern: Mixed (Functional Core helpers + Imperative Shell reranker)
# Justification: grouping and normalization are pure; CrossEncoderReranker loads ML model.

from __future__ import annotations

from uuid import UUID

from local_library.embeddings.base import SearchResult


def _group_by_document(
    results: list[SearchResult],
    max_chunks_per_doc: int = 3,
) -> list[SearchResult]:
    """Group results by document, keeping top-N per document by original score.

    Within each document group, results are sorted by score descending and
    truncated to max_chunks_per_doc. This prevents a single highly-relevant
    document from monopolizing the candidate pool.
    """
    if not results:
        return []

    groups: dict[UUID, list[SearchResult]] = {}
    for result in results:
        doc_id = result.chunk.doc_id
        if doc_id not in groups:
            groups[doc_id] = []
        groups[doc_id].append(result)

    selected: list[SearchResult] = []
    for doc_results in groups.values():
        doc_results.sort(key=lambda r: r.score, reverse=True)
        selected.extend(doc_results[:max_chunks_per_doc])

    return selected
