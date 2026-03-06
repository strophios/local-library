"""Cross-encoder reranking components.

Pure helper functions (_group_by_document, _normalize_scores) are Functional Core.
CrossEncoderReranker is Imperative Shell (ML model I/O).
"""

# pattern: Mixed (Functional Core helpers + Imperative Shell reranker)
# Justification: grouping and normalization are pure; CrossEncoderReranker loads ML model.

from __future__ import annotations

import math
from uuid import UUID

from local_library.core.errors import EmbeddingError, ErrorCode
from local_library.embeddings.base import Reranker, Retriever, SearchResult


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


def _normalize_scores(logits: list[float]) -> list[float]:
    """Sigmoid-normalize raw logits to the [0, 1] range.

    Cross-encoder models output unbounded logits. Sigmoid maps them to
    interpretable probabilities while preserving relative ordering.

    Uses a numerically stable formulation to avoid overflow for extreme values.
    """

    def _sigmoid(x: float) -> float:
        # Numerically stable: avoids exp(large_positive) overflow
        if x >= 0:
            z = math.exp(-x)
            return 1.0 / (1.0 + z)
        else:
            z = math.exp(x)
            return z / (1.0 + z)

    return [_sigmoid(x) for x in logits]


class CrossEncoderReranker:
    """Document-aware cross-encoder reranker with lazy model loading.

    Groups candidates by parent document, selects top chunks per document,
    scores via cross-encoder, and returns top-k by reranked score.
    """

    # pattern: Imperative Shell

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-12-v2",
        max_chunks_per_doc: int = 3,
        batch_size: int = 16,
        lazy_load: bool = True,
    ) -> None:
        self._model_name = model_name
        self._max_chunks_per_doc = max_chunks_per_doc
        self._batch_size = batch_size
        self._model = None
        if not lazy_load:
            self._load_model()

    def _load_model(self) -> None:
        """Load cross-encoder model on first use.

        Raises:
            EmbeddingError: If model loading fails
        """
        if self._model is not None:
            return

        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(
                self._model_name,
                trust_remote_code="bge" in self._model_name.lower(),
            )
        except ImportError as e:
            raise EmbeddingError(
                "sentence-transformers not installed",
                ErrorCode.EMBEDDING_MODEL_LOAD_FAILED,
            ) from e
        except Exception as e:
            raise EmbeddingError(
                f"failed to load cross-encoder model: {e}",
                ErrorCode.EMBEDDING_MODEL_LOAD_FAILED,
                details={"model_name": self._model_name},
            ) from e

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        k: int = 10,
    ) -> list[SearchResult]:
        """Rerank results using cross-encoder scoring with document-aware grouping.

        When results span multiple documents, groups by doc_id and selects
        top chunks per document before scoring. When all results share a
        single doc_id (e.g. --doc flag), grouping is bypassed.
        """
        if not results:
            return []

        self._load_model()

        # Single-document mode: skip grouping
        doc_ids = {r.chunk.doc_id for r in results}
        if len(doc_ids) == 1:
            candidates = results
        else:
            candidates = _group_by_document(results, self._max_chunks_per_doc)

        # Score via cross-encoder
        pairs = [(query, r.chunk.text) for r in candidates]
        raw_scores = self._model.predict(pairs, batch_size=self._batch_size, convert_to_numpy=True)
        scores = _normalize_scores(raw_scores.tolist())

        # Build new frozen SearchResult instances with reranked scores
        reranked = [
            SearchResult(
                chunk=r.chunk,
                score=s,
                doc_title=r.doc_title,
                doc_citekey=r.doc_citekey,
                search_methods=r.search_methods,
            )
            for r, s in zip(candidates, scores, strict=True)
        ]

        reranked.sort(key=lambda r: r.score, reverse=True)
        return reranked[:k]


class RerankedRetriever:
    """Retriever wrapper that applies cross-encoder reranking.

    Implements the Retriever protocol by delegating to an inner retriever
    with a broadened candidate pool, then passing results through a Reranker.
    """

    # pattern: Imperative Shell

    def __init__(
        self,
        inner: Retriever,
        reranker: Reranker,
        pool_size: int = 100,
        min_pool_ratio: int = 3,
    ) -> None:
        self._inner = inner
        self._reranker = reranker
        self._pool_size = pool_size
        self._min_pool_ratio = min_pool_ratio

    def retrieve(
        self,
        query: str,
        k: int = 10,
        doc_ids: list[UUID] | None = None,
    ) -> list[SearchResult]:
        """Retrieve and rerank results.

        Fetches a broadened candidate pool from the inner retriever,
        then applies the reranker to select the final top-k.
        """
        effective_pool = max(self._pool_size, k * self._min_pool_ratio)
        candidates = self._inner.retrieve(query, k=effective_pool, doc_ids=doc_ids)
        return self._reranker.rerank(query, candidates, k=k)
