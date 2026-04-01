"""Storage operations for chunks and embeddings."""

# pattern: Imperative Shell

import re
import sqlite3
from datetime import datetime, timezone
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

from local_library.core.errors import EmbeddingError, ErrorCode, FTSQueryError
from local_library.core.models import EmbeddingStatus
from local_library.core.vec_extension import require_vec_extension
from local_library.embeddings.base import Chunk, ChunkEmbedding


def _sanitize_fts_query(query: str) -> str:
    """Sanitize a query string for FTS5 compatibility.

    Removes characters that are invalid in FTS5 query syntax while preserving
    alphanumeric words and hyphenated terms.

    Args:
        query: Raw query string (may contain punctuation and special chars)

    Returns:
        Cleaned query string safe for FTS5 MATCH clause

    Raises:
        FTSQueryError: If the sanitized query is empty
    """
    # Remove characters that FTS5 treats as syntax errors or special operators
    # Includes: ?!.,;:[]{}()^~\ and single quotes (FTS5 string delimiter)
    cleaned = re.sub(r"[?!.,;:\[\]{}()^~\\']", " ", query)

    # Replace all hyphens and plus signs with spaces.
    # FTS5's query parser interprets - as NOT and + as required-term operators.
    # The unicode61 tokenizer already splits on hyphens when indexing, so
    # "actor-network" is indexed as ["actor", "network"]. Replacing hyphens
    # with spaces in the query produces the correct implicit-AND match.
    cleaned = cleaned.replace("-", " ").replace("+", " ")

    # Handle unbalanced quotes by removing all quotes if count is odd
    # (FTS5 uses quotes for phrase matching, but unbalanced ones cause errors)
    if cleaned.count('"') % 2 != 0:
        cleaned = cleaned.replace('"', " ")

    # Collapse multiple spaces and strip
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        raise FTSQueryError(
            "query becomes empty after FTS5 sanitization",
            ErrorCode.EMBEDDING_FTS_QUERY_SYNTAX,
            details={"original_query": query},
        )

    return cleaned


class EmbeddingStorage:
    """Storage operations for chunks and embeddings.

    Handles CRUD operations for the chunks table, chunk_vectors vec0 table,
    and keeps FTS5 in sync. Uses the connection pattern from core/storage.py.

    Attributes:
        conn: SQLite connection with sqlite-vec loaded
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Initialize storage with database connection.

        Args:
            conn: SQLite connection (sqlite-vec will be loaded)

        Raises:
            EmbeddingError: If sqlite-vec extension cannot be loaded
        """
        self._conn = conn
        require_vec_extension(conn)

    def store_embeddings(self, embeddings: list[ChunkEmbedding]) -> None:
        """Store chunks and their embeddings.

        Inserts chunks into the chunks table and vectors into chunk_vectors.
        FTS5 is kept in sync via triggers.

        Args:
            embeddings: ChunkEmbedding objects to store

        Raises:
            EmbeddingError: If storage fails
        """
        if not embeddings:
            return

        try:
            # Import here to avoid circular dependency
            from sqlite_vec import serialize_float32

            for emb in embeddings:
                chunk = emb.chunk

                # Insert into chunks table
                self._conn.execute(
                    """
                    INSERT INTO chunks (
                        chunk_id, doc_id, chunk_index, text, section,
                        char_start, char_end, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk.chunk_id,
                        str(chunk.doc_id),
                        chunk.chunk_index,
                        chunk.text,
                        chunk.section,
                        chunk.char_start,
                        chunk.char_end,
                        chunk.created_at.isoformat(),
                    ),
                )

                # Insert into chunk_vectors vec0 table
                vector_blob = serialize_float32(emb.embedding)  # type: ignore[arg-type]  # numpy arrays accepted at runtime
                self._conn.execute(
                    """
                    INSERT INTO chunk_vectors (chunk_id, embedding)
                    VALUES (?, ?)
                    """,
                    (chunk.chunk_id, vector_blob),
                )

            self._conn.commit()

        except sqlite3.Error as e:
            self._conn.rollback()
            raise EmbeddingError(
                f"failed to store embeddings: {e}",
                ErrorCode.EMBEDDING_STORAGE_FAILED,
                details={"embedding_count": len(embeddings)},
            ) from e

    def delete_by_document(self, doc_id: UUID) -> int:
        """Delete all chunks and embeddings for a document.

        Uses cascade delete from foreign key constraint.

        Args:
            doc_id: Document UUID

        Returns:
            Number of chunks deleted

        Raises:
            EmbeddingError: If deletion fails
        """
        try:
            # Get chunk_ids for this document (needed for vec0 deletion)
            cursor = self._conn.execute(
                "SELECT chunk_id FROM chunks WHERE doc_id = ?",
                (str(doc_id),),
            )
            chunk_ids = [row[0] for row in cursor.fetchall()]

            if not chunk_ids:
                return 0

            # Delete from vec0 table (no cascade support)
            placeholders = ",".join("?" * len(chunk_ids))
            self._conn.execute(
                f"DELETE FROM chunk_vectors WHERE chunk_id IN ({placeholders})",
                chunk_ids,
            )

            # Delete from chunks table (FTS5 triggers handle chunks_fts)
            self._conn.execute(
                "DELETE FROM chunks WHERE doc_id = ?",
                (str(doc_id),),
            )

            self._conn.commit()
            return len(chunk_ids)

        except sqlite3.Error as e:
            self._conn.rollback()
            raise EmbeddingError(
                f"failed to delete embeddings: {e}",
                ErrorCode.EMBEDDING_STORAGE_FAILED,
                details={"doc_id": str(doc_id)},
            ) from e

    def get_chunks_by_document(self, doc_id: UUID) -> list[Chunk]:
        """Get all chunks for a document.

        Args:
            doc_id: Document UUID

        Returns:
            List of Chunk objects ordered by chunk_index
        """
        cursor = self._conn.execute(
            """
            SELECT chunk_id, doc_id, chunk_index, text, section,
                   char_start, char_end, created_at
            FROM chunks
            WHERE doc_id = ?
            ORDER BY chunk_index
            """,
            (str(doc_id),),
        )

        chunks = []
        for row in cursor.fetchall():
            chunk = Chunk(
                chunk_id=row[0],
                doc_id=UUID(row[1]),
                chunk_index=row[2],
                text=row[3],
                section=row[4] or "",
                char_start=row[5],
                char_end=row[6],
                created_at=datetime.fromisoformat(row[7]),
            )
            chunks.append(chunk)

        return chunks

    def get_chunk_count(self, doc_id: UUID) -> int:
        """Get number of chunks for a document.

        Args:
            doc_id: Document UUID

        Returns:
            Number of chunks
        """
        cursor = self._conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE doc_id = ?",
            (str(doc_id),),
        )
        return cursor.fetchone()[0]

    def has_embeddings(self, doc_id: UUID) -> bool:
        """Check if document has embeddings.

        Args:
            doc_id: Document UUID

        Returns:
            True if document has at least one embedding
        """
        return self.get_chunk_count(doc_id) > 0

    def search_similar(
        self,
        query_embedding: NDArray[np.float32],
        limit: int = 10,
        doc_ids: list[UUID] | None = None,
    ) -> list[tuple[Chunk, float]]:
        """Search for similar chunks using vector similarity.

        Args:
            query_embedding: 768-dimensional query vector
            limit: Maximum results to return
            doc_ids: Optional list of document IDs to filter by

        Returns:
            List of (Chunk, distance) tuples, sorted by distance ascending
        """
        from sqlite_vec import serialize_float32

        query_blob = serialize_float32(query_embedding)  # type: ignore[arg-type]  # numpy arrays accepted at runtime

        if doc_ids:
            # Filter by specific documents
            placeholders = ",".join("?" * len(doc_ids))
            cursor = self._conn.execute(
                f"""
                SELECT cv.chunk_id, cv.distance, c.doc_id, c.chunk_index,
                       c.text, c.section, c.char_start, c.char_end, c.created_at
                FROM chunk_vectors cv
                JOIN chunks c ON cv.chunk_id = c.chunk_id
                WHERE cv.embedding MATCH ? AND k = ?
                  AND c.doc_id IN ({placeholders})
                ORDER BY cv.distance
                """,
                [query_blob, limit] + [str(d) for d in doc_ids],
            )
        else:
            cursor = self._conn.execute(
                """
                SELECT cv.chunk_id, cv.distance, c.doc_id, c.chunk_index,
                       c.text, c.section, c.char_start, c.char_end, c.created_at
                FROM chunk_vectors cv
                JOIN chunks c ON cv.chunk_id = c.chunk_id
                WHERE cv.embedding MATCH ? AND k = ?
                ORDER BY cv.distance
                """,
                [query_blob, limit],
            )

        results = []
        for row in cursor.fetchall():
            chunk = Chunk(
                chunk_id=row[0],
                doc_id=UUID(row[2]),
                chunk_index=row[3],
                text=row[4],
                section=row[5] or "",
                char_start=row[6],
                char_end=row[7],
                created_at=datetime.fromisoformat(row[8]),
            )
            distance = row[1]
            results.append((chunk, distance))

        return results

    def search_fts(
        self,
        query: str,
        limit: int = 10,
        doc_ids: list[UUID] | None = None,
    ) -> list[tuple[Chunk, float]]:
        """Search for chunks using FTS5 full-text search with BM25 ranking.

        Args:
            query: Search query text (passed to FTS5 MATCH)
            limit: Maximum number of results to return
            doc_ids: Optional list of document IDs to filter by

        Returns:
            List of (Chunk, bm25_score) tuples sorted by relevance.
            BM25 scores are negative; more negative = better match.

        Raises:
            FTSQueryError: If query contains invalid FTS5 syntax or becomes empty
                after sanitization
        """
        # Sanitize query for FTS5 compatibility
        query = _sanitize_fts_query(query)

        try:
            if doc_ids:
                placeholders = ",".join("?" * len(doc_ids))
                cursor = self._conn.execute(
                    f"""
                    SELECT c.chunk_id, c.doc_id, c.chunk_index, c.text, c.section,
                           c.char_start, c.char_end, c.created_at, bm25(chunks_fts)
                    FROM chunks_fts
                    JOIN chunks c ON chunks_fts.rowid = c.rowid
                    WHERE chunks_fts MATCH ? AND c.doc_id IN ({placeholders})
                    ORDER BY bm25(chunks_fts)
                    LIMIT ?
                    """,
                    [query] + [str(d) for d in doc_ids] + [limit],
                )
            else:
                cursor = self._conn.execute(
                    """
                    SELECT c.chunk_id, c.doc_id, c.chunk_index, c.text, c.section,
                           c.char_start, c.char_end, c.created_at, bm25(chunks_fts)
                    FROM chunks_fts
                    JOIN chunks c ON chunks_fts.rowid = c.rowid
                    WHERE chunks_fts MATCH ?
                    ORDER BY bm25(chunks_fts)
                    LIMIT ?
                    """,
                    [query, limit],
                )
        except sqlite3.OperationalError as e:
            error_msg = str(e).lower()
            if (
                "fts5" in error_msg
                or "syntax" in error_msg
                or "parse" in error_msg
                or "unterminated" in error_msg
            ):
                raise FTSQueryError(
                    f"invalid FTS5 query syntax: {e}",
                    ErrorCode.EMBEDDING_FTS_QUERY_SYNTAX,
                    details={"query": query},
                ) from e
            raise

        results = []
        for row in cursor.fetchall():
            chunk = Chunk(
                chunk_id=row[0],
                doc_id=UUID(row[1]),
                chunk_index=row[2],
                text=row[3],
                section=row[4] or "",
                char_start=row[5],
                char_end=row[6],
                created_at=datetime.fromisoformat(row[7]),
            )
            score = row[8]
            results.append((chunk, score))

        return results


def update_embedding_status(
    conn: sqlite3.Connection,
    doc_id: UUID,
    status: EmbeddingStatus,
) -> None:
    """Update embedding status for a document.

    Args:
        conn: Database connection
        doc_id: Document UUID
        status: New embedding status
    """
    now = datetime.now(timezone.utc)
    conn.execute(
        """
        UPDATE documents
        SET embedding_status = ?, updated_at = ?
        WHERE id = ?
        """,
        (status.value, now.isoformat(), str(doc_id)),
    )
    conn.commit()


def get_documents_needing_embedding(
    conn: sqlite3.Connection,
    statuses: list[EmbeddingStatus] | None = None,
) -> list[UUID]:
    """Get document IDs that need embedding.

    Args:
        conn: Database connection
        statuses: Embedding statuses to filter by (default: PENDING, STALE)

    Returns:
        List of document UUIDs needing embedding
    """
    if statuses is None:
        statuses = [EmbeddingStatus.PENDING, EmbeddingStatus.STALE]

    placeholders = ",".join("?" * len(statuses))
    cursor = conn.execute(
        f"""
        SELECT id FROM documents
        WHERE embedding_status IN ({placeholders})
          AND status = 'ready'
        ORDER BY created_at
        """,
        [s.value for s in statuses],
    )

    return [UUID(row[0]) for row in cursor.fetchall()]
