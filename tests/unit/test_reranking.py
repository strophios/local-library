"""Tests for cross-encoder reranking components."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from local_library.embeddings.base import Chunk, SearchResult
from local_library.embeddings.reranking import _group_by_document, _normalize_scores


def _make_result(
    doc_id: UUID | None = None,
    chunk_index: int = 0,
    text: str = "Test text",
    score: float = 0.5,
    search_methods: frozenset[str] | None = None,
) -> SearchResult:
    """Create a SearchResult for testing."""
    if doc_id is None:
        doc_id = uuid4()
    chunk = Chunk.create(doc_id, chunk_index, text)
    return SearchResult(
        chunk=chunk,
        score=score,
        doc_title=None,
        doc_citekey=None,
        search_methods=search_methods or frozenset({"vector"}),
    )


class TestGroupByDocument:
    """Tests for _group_by_document helper."""

    def test_empty_input_returns_empty(self) -> None:
        """Empty result list returns empty list."""
        assert _group_by_document([], max_chunks_per_doc=3) == []

    def test_limits_chunks_per_document(self) -> None:
        """Limits chunks per document to max_chunks_per_doc."""
        doc_id = uuid4()
        results = [
            _make_result(doc_id=doc_id, chunk_index=i, score=1.0 - i * 0.1)
            for i in range(5)
        ]
        grouped = _group_by_document(results, max_chunks_per_doc=3)
        assert len(grouped) == 3

    def test_keeps_highest_scoring_chunks(self) -> None:
        """Within each document, keeps the highest-scoring chunks."""
        doc_id = uuid4()
        results = [
            _make_result(doc_id=doc_id, chunk_index=0, score=0.1),
            _make_result(doc_id=doc_id, chunk_index=1, score=0.9),
            _make_result(doc_id=doc_id, chunk_index=2, score=0.5),
        ]
        grouped = _group_by_document(results, max_chunks_per_doc=2)
        scores = [r.score for r in grouped]
        assert 0.9 in scores
        assert 0.5 in scores
        assert 0.1 not in scores

    def test_multiple_documents_each_limited(self) -> None:
        """Each document independently limited to max_chunks_per_doc."""
        doc_a = uuid4()
        doc_b = uuid4()
        results = [
            _make_result(doc_id=doc_a, chunk_index=i, score=1.0 - i * 0.1)
            for i in range(4)
        ] + [
            _make_result(doc_id=doc_b, chunk_index=i, score=0.8 - i * 0.1)
            for i in range(4)
        ]
        grouped = _group_by_document(results, max_chunks_per_doc=2)
        doc_a_results = [r for r in grouped if r.chunk.doc_id == doc_a]
        doc_b_results = [r for r in grouped if r.chunk.doc_id == doc_b]
        assert len(doc_a_results) == 2
        assert len(doc_b_results) == 2

    def test_fewer_than_max_returns_all(self) -> None:
        """If a document has fewer than max_chunks_per_doc, returns all."""
        doc_id = uuid4()
        results = [_make_result(doc_id=doc_id, chunk_index=0, score=0.5)]
        grouped = _group_by_document(results, max_chunks_per_doc=3)
        assert len(grouped) == 1


class TestNormalizeScores:
    """Tests for sigmoid normalization of logit scores."""

    def test_zero_maps_to_half(self) -> None:
        """Sigmoid of 0 is exactly 0.5."""
        assert _normalize_scores([0.0]) == pytest.approx([0.5])

    def test_large_positive_maps_near_one(self) -> None:
        """Large positive logits map close to 1.0."""
        result = _normalize_scores([10.0])
        assert result[0] > 0.999

    def test_large_negative_maps_near_zero(self) -> None:
        """Large negative logits map close to 0.0."""
        result = _normalize_scores([-10.0])
        assert result[0] < 0.001

    def test_empty_input_returns_empty(self) -> None:
        """Empty list returns empty list."""
        assert _normalize_scores([]) == []

    def test_preserves_relative_ordering(self) -> None:
        """Higher logits produce higher normalized scores."""
        logits = [-2.0, 0.0, 3.0, -5.0, 1.0]
        scores = _normalize_scores(logits)
        sorted_by_logit = sorted(range(len(logits)), key=lambda i: logits[i])
        sorted_by_score = sorted(range(len(scores)), key=lambda i: scores[i])
        assert sorted_by_logit == sorted_by_score

    def test_output_bounded_zero_one(self) -> None:
        """All outputs are strictly between 0 and 1."""
        logits = [-100.0, -10.0, -1.0, 0.0, 1.0, 10.0, 100.0]
        scores = _normalize_scores(logits)
        for s in scores:
            assert 0.0 <= s <= 1.0

    def test_extreme_values_no_overflow(self) -> None:
        """Extreme logits don't cause overflow errors."""
        scores = _normalize_scores([-1000.0, 1000.0])
        assert scores[0] == pytest.approx(0.0, abs=1e-10)
        assert scores[1] == pytest.approx(1.0, abs=1e-10)
