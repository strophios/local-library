"""Retriever implementations wrapping search backends.

VectorRetriever and FTSRetriever wrap EmbeddingStorage's search methods
and return protocol-compliant SearchResult objects enriched with document
metadata. HybridRetriever (Phase 4) composes these two via RRF fusion.
"""

# pattern: Mixed — _rrf_fuse is Functional Core (pure computation);
#          retrievers are Imperative Shell (I/O via storage)

import logging
import sqlite3
from uuid import UUID

from local_library.core.errors import FTSQueryError
from local_library.embeddings.base import Embedder, SearchResult
from local_library.embeddings.storage import EmbeddingStorage

logger = logging.getLogger(__name__)


def _lookup_doc_metadata(
    conn: sqlite3.Connection,
    doc_ids: set[UUID],
) -> dict[UUID, tuple[str | None, str | None]]:
    """Batch lookup document title and citekey.

    Args:
        conn: Database connection
        doc_ids: Set of document UUIDs to look up

    Returns:
        Dict mapping doc_id to (title, citekey) tuples.
        Missing documents are omitted from the result.
    """
    if not doc_ids:
        return {}
    placeholders = ",".join("?" * len(doc_ids))
    cursor = conn.execute(
        f"SELECT id, title, citekey FROM documents WHERE id IN ({placeholders})",
        [str(d) for d in doc_ids],
    )
    return {UUID(row[0]): (row[1], row[2]) for row in cursor.fetchall()}


def _rrf_fuse(
    vector_results: list[SearchResult],
    fts_results: list[SearchResult],
    k: int,
    rrf_k: int = 60,
    vector_weight: float = 1.0,
    fts_weight: float = 1.0,
) -> list[SearchResult]:
    """Fuse ranked lists via Reciprocal Rank Fusion.

    Each result's RRF score is: weight / (rrf_k + rank), summed across lists.
    Results appearing in both lists get combined scores and merged search_methods.

    This is a pure function (Functional Core) — no I/O, fully testable.

    Args:
        vector_results: Ranked results from vector search (score descending)
        fts_results: Ranked results from FTS search (score descending)
        k: Maximum number of results to return
        rrf_k: Smoothing constant (default 60, standard value)
        vector_weight: Weight multiplier for vector scores
        fts_weight: Weight multiplier for FTS scores

    Returns:
        Fused list of SearchResult, sorted by RRF score descending, limited to k
    """
    # Track scores and metadata by chunk_id
    scores: dict[str, float] = {}
    results_by_id: dict[str, SearchResult] = {}
    methods_by_id: dict[str, set[str]] = {}

    # Score vector results
    for rank, result in enumerate(vector_results, start=1):
        cid = result.chunk.chunk_id
        scores[cid] = scores.get(cid, 0.0) + vector_weight / (rrf_k + rank)
        # Vector results processed first; metadata from first-seen result is kept.
        # Both retrievers query the same database, so metadata is identical in practice.
        results_by_id[cid] = result
        methods_by_id.setdefault(cid, set()).update(result.search_methods)

    # Score FTS results
    for rank, result in enumerate(fts_results, start=1):
        cid = result.chunk.chunk_id
        scores[cid] = scores.get(cid, 0.0) + fts_weight / (rrf_k + rank)
        # Only store FTS result if not already present from vector results.
        # Vector results processed first; metadata from first-seen result is kept.
        if cid not in results_by_id:
            results_by_id[cid] = result
        methods_by_id.setdefault(cid, set()).update(result.search_methods)

    # Build fused results sorted by RRF score descending
    sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:k]

    fused = []
    for cid in sorted_ids:
        original = results_by_id[cid]
        fused.append(
            SearchResult(
                chunk=original.chunk,
                score=scores[cid],
                doc_title=original.doc_title,
                doc_citekey=original.doc_citekey,
                search_methods=frozenset(methods_by_id[cid]),
            )
        )

    return fused


class VectorRetriever:
    """Retriever using vector similarity search.

    Wraps EmbeddingStorage.search_similar() with query embedding
    and metadata enrichment. Converts cosine distance to similarity
    score (1.0 - distance) so higher = more relevant.
    """

    def __init__(self, storage: EmbeddingStorage, embedder: Embedder) -> None:
        """Initialize with storage backend and embedder for query encoding.

        Args:
            storage: EmbeddingStorage instance for vector search
            embedder: Embedder instance for converting queries to vectors
        """
        self._storage = storage
        self._embedder = embedder

    def retrieve(
        self,
        query: str,
        k: int = 10,
        doc_ids: list[UUID] | None = None,
    ) -> list[SearchResult]:
        """Search for chunks by vector similarity.

        Embeds the query using the embedder, searches for similar vectors,
        and enriches results with document metadata.

        Args:
            query: Natural language search query
            k: Maximum number of results
            doc_ids: Optional document ID filter

        Returns:
            List of SearchResult sorted by score descending (higher = more relevant)
        """
        query_embedding = self._embedder.embed_query(query)
        raw_results = self._storage.search_similar(query_embedding, limit=k, doc_ids=doc_ids)

        if not raw_results:
            return []

        # Batch lookup metadata for all unique doc_ids
        unique_doc_ids = {chunk.doc_id for chunk, _ in raw_results}
        metadata = _lookup_doc_metadata(self._storage._conn, unique_doc_ids)

        results = []
        for chunk, distance in raw_results:
            title, citekey = metadata.get(chunk.doc_id, (None, None))
            results.append(
                SearchResult(
                    chunk=chunk,
                    score=1.0 - distance,
                    doc_title=title,
                    doc_citekey=citekey,
                    search_methods=frozenset({"vector"}),
                )
            )

        return results


class FTSRetriever:
    """Retriever using FTS5 full-text search.

    Wraps EmbeddingStorage.search_fts() with metadata enrichment.
    Negates BM25 scores so higher = more relevant.
    """

    def __init__(self, storage: EmbeddingStorage) -> None:
        """Initialize with storage backend.

        Args:
            storage: EmbeddingStorage instance for FTS5 search
        """
        self._storage = storage

    def retrieve(
        self,
        query: str,
        k: int = 10,
        doc_ids: list[UUID] | None = None,
    ) -> list[SearchResult]:
        """Search for chunks by keyword match.

        Passes the query to FTS5 MATCH and enriches results with
        document metadata.

        Args:
            query: Search query text
            k: Maximum number of results
            doc_ids: Optional document ID filter

        Returns:
            List of SearchResult sorted by score descending (higher = more relevant)

        Raises:
            FTSQueryError: If query contains invalid FTS5 syntax
        """
        raw_results = self._storage.search_fts(query, limit=k, doc_ids=doc_ids)

        if not raw_results:
            return []

        # Batch lookup metadata for all unique doc_ids
        unique_doc_ids = {chunk.doc_id for chunk, _ in raw_results}
        metadata = _lookup_doc_metadata(self._storage._conn, unique_doc_ids)

        results = []
        for chunk, bm25_score in raw_results:
            title, citekey = metadata.get(chunk.doc_id, (None, None))
            results.append(
                SearchResult(
                    chunk=chunk,
                    score=-bm25_score,
                    doc_title=title,
                    doc_citekey=citekey,
                    search_methods=frozenset({"fts"}),
                )
            )

        return results


class HybridRetriever:
    """Retriever combining vector and FTS search via Reciprocal Rank Fusion.

    Composes VectorRetriever and FTSRetriever, retrieves candidates from both,
    and fuses results using RRF. Falls back to vector-only if FTS fails.
    """

    def __init__(
        self,
        vector_retriever: VectorRetriever,
        fts_retriever: FTSRetriever,
        rrf_k: int = 60,
        vector_weight: float = 1.0,
        fts_weight: float = 1.0,
        candidate_multiplier: int = 3,
    ) -> None:
        """Initialize with sub-retrievers and RRF parameters.

        Args:
            vector_retriever: VectorRetriever instance
            fts_retriever: FTSRetriever instance
            rrf_k: RRF smoothing constant (default 60)
            vector_weight: Weight for vector results in RRF
            fts_weight: Weight for FTS results in RRF
            candidate_multiplier: Retrieve k * multiplier candidates per method
        """
        self._vector = vector_retriever
        self._fts = fts_retriever
        self._rrf_k = rrf_k
        self._vector_weight = vector_weight
        self._fts_weight = fts_weight
        self._candidate_multiplier = candidate_multiplier

    def retrieve(
        self,
        query: str,
        k: int = 10,
        doc_ids: list[UUID] | None = None,
    ) -> list[SearchResult]:
        """Search using both vector and FTS, fuse results via RRF.

        Retrieves k * candidate_multiplier candidates from each method,
        then fuses to top k via RRF. If FTS fails with a query syntax error,
        falls back to vector-only results with a warning.

        Args:
            query: Natural language search query
            k: Maximum number of results
            doc_ids: Optional document ID filter

        Returns:
            List of SearchResult sorted by RRF score descending
        """
        candidate_k = k * self._candidate_multiplier

        # Always run vector search
        vector_results = self._vector.retrieve(query, k=candidate_k, doc_ids=doc_ids)

        # Try FTS search, fall back to vector-only on syntax error
        fts_results: list[SearchResult] = []
        try:
            fts_results = self._fts.retrieve(query, k=candidate_k, doc_ids=doc_ids)
        except FTSQueryError:
            logger.warning(
                "FTS query failed for '%s', falling back to vector-only results",
                query,
            )

        return _rrf_fuse(
            vector_results,
            fts_results,
            k=k,
            rrf_k=self._rrf_k,
            vector_weight=self._vector_weight,
            fts_weight=self._fts_weight,
        )
