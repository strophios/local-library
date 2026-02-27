"""Retriever implementations wrapping search backends.

VectorRetriever and FTSRetriever wrap EmbeddingStorage's search methods
and return protocol-compliant SearchResult objects enriched with document
metadata. HybridRetriever (Phase 4) composes these two via RRF fusion.
"""

# pattern: Imperative Shell

import sqlite3
from uuid import UUID

from local_library.embeddings.base import Chunk, Embedder, SearchResult
from local_library.embeddings.storage import EmbeddingStorage


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
