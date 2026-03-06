"""Tests for cross-encoder reranking components."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID, uuid4

import numpy as np
import pytest

from local_library.embeddings.base import Chunk, Reranker, Retriever, SearchResult
from local_library.embeddings.reranking import (
    CrossEncoderReranker,
    RerankedRetriever,
    _group_by_document,
    _normalize_scores,
)


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
            _make_result(doc_id=doc_id, chunk_index=i, score=1.0 - i * 0.1) for i in range(5)
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
            _make_result(doc_id=doc_a, chunk_index=i, score=1.0 - i * 0.1) for i in range(4)
        ] + [_make_result(doc_id=doc_b, chunk_index=i, score=0.8 - i * 0.1) for i in range(4)]
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


class TestCrossEncoderReranker:
    """Tests for CrossEncoderReranker."""

    @pytest.fixture()
    def mock_model(self) -> MagicMock:
        """Mock CrossEncoder model returning ascending scores as logits."""
        model = MagicMock()
        model.predict = MagicMock(
            side_effect=lambda pairs, **kwargs: np.array([float(i) for i in range(len(pairs))])
        )
        return model

    @pytest.fixture()
    def reranker(self, mock_model: MagicMock) -> CrossEncoderReranker:
        """CrossEncoderReranker with mock model injected."""
        r = CrossEncoderReranker(lazy_load=True)
        r._model = mock_model
        return r

    def test_satisfies_reranker_protocol(self) -> None:
        """CrossEncoderReranker satisfies the Reranker protocol."""
        r = CrossEncoderReranker(lazy_load=True)
        assert isinstance(r, Reranker)

    def test_reranks_by_cross_encoder_score(self, reranker: CrossEncoderReranker) -> None:
        """Results are reordered by cross-encoder scores."""
        doc_a, doc_b = uuid4(), uuid4()
        results = [
            _make_result(doc_id=doc_a, chunk_index=0, score=0.9, text="low relevance"),
            _make_result(doc_id=doc_b, chunk_index=0, score=0.1, text="high relevance"),
        ]
        reranked = reranker.rerank("test query", results, k=2)
        # Mock returns ascending logits [0.0, 1.0], so second result scores higher
        assert reranked[0].score > reranked[1].score

    def test_returns_at_most_k_results(self, reranker: CrossEncoderReranker) -> None:
        """Rerank returns at most k results."""
        results = [_make_result(doc_id=uuid4(), chunk_index=0, score=0.5) for _ in range(10)]
        reranked = reranker.rerank("query", results, k=3)
        assert len(reranked) <= 3

    def test_empty_results_returns_empty(self, reranker: CrossEncoderReranker) -> None:
        """Empty input returns empty output without calling model."""
        reranked = reranker.rerank("query", [], k=5)
        assert reranked == []
        reranker._model.predict.assert_not_called()

    def test_scores_are_sigmoid_normalized(self, reranker: CrossEncoderReranker) -> None:
        """Output scores are in [0, 1] range (sigmoid-normalized)."""
        results = [_make_result(doc_id=uuid4(), chunk_index=0, score=0.5) for _ in range(3)]
        reranked = reranker.rerank("query", results, k=3)
        for r in reranked:
            assert 0.0 <= r.score <= 1.0

    def test_preserves_search_methods(self, reranker: CrossEncoderReranker) -> None:
        """search_methods frozenset carries forward from original results."""
        methods = frozenset({"vector", "fts"})
        results = [_make_result(doc_id=uuid4(), score=0.5, search_methods=methods)]
        reranked = reranker.rerank("query", results, k=1)
        assert reranked[0].search_methods == methods

    def test_preserves_doc_metadata(self, reranker: CrossEncoderReranker) -> None:
        """doc_title and doc_citekey carry forward from original results."""
        chunk = Chunk.create(uuid4(), 0, "text")
        result = SearchResult(
            chunk=chunk,
            score=0.5,
            doc_title="Test Title",
            doc_citekey="Author2023",
            search_methods=frozenset({"vector"}),
        )
        reranked = reranker.rerank("query", [result], k=1)
        assert reranked[0].doc_title == "Test Title"
        assert reranked[0].doc_citekey == "Author2023"

    def test_single_document_skips_grouping(self, reranker: CrossEncoderReranker) -> None:
        """When all results share doc_id, grouping is bypassed."""
        doc_id = uuid4()
        results = [_make_result(doc_id=doc_id, chunk_index=i, score=0.5) for i in range(5)]
        reranked = reranker.rerank("query", results, k=5)
        # All 5 chunks scored (no max_chunks_per_doc cap applied)
        assert len(reranked) == 5

    def test_lazy_loading_defers_model(self) -> None:
        """With lazy_load=True, model is None until first rerank call."""
        r = CrossEncoderReranker(lazy_load=True)
        assert r._model is None

    def test_creates_new_frozen_instances(self, reranker: CrossEncoderReranker) -> None:
        """Reranked results are new SearchResult instances, not mutated originals."""
        results = [_make_result(doc_id=uuid4(), score=0.1)]
        reranked = reranker.rerank("query", results, k=1)
        assert reranked[0] is not results[0]
        assert reranked[0].score != results[0].score


class TestRerankedRetriever:
    """Tests for RerankedRetriever wrapper."""

    @pytest.fixture()
    def inner_results(self) -> list[SearchResult]:
        """Pre-built results the mock inner retriever returns."""
        return [
            _make_result(doc_id=uuid4(), chunk_index=0, score=0.5 + i * 0.05)
            for i in range(10)
        ]

    @pytest.fixture()
    def mock_inner(self, inner_results: list[SearchResult]) -> MagicMock:
        """Mock inner retriever returning pre-built results."""
        inner = MagicMock()
        inner.retrieve = MagicMock(return_value=inner_results)
        return inner

    @pytest.fixture()
    def reranked_results(self) -> list[SearchResult]:
        """Pre-built results the mock reranker returns."""
        return [
            _make_result(doc_id=uuid4(), chunk_index=0, score=0.9 - i * 0.1)
            for i in range(5)
        ]

    @pytest.fixture()
    def mock_reranker(self, reranked_results: list[SearchResult]) -> MagicMock:
        """Mock reranker returning pre-built results."""
        reranker = MagicMock()
        reranker.rerank = MagicMock(return_value=reranked_results)
        return reranker

    @pytest.fixture()
    def retriever(
        self, mock_inner: MagicMock, mock_reranker: MagicMock
    ) -> RerankedRetriever:
        """RerankedRetriever with mocked dependencies."""
        return RerankedRetriever(
            inner=mock_inner, reranker=mock_reranker, pool_size=100
        )

    def test_satisfies_retriever_protocol(
        self, mock_inner: MagicMock, mock_reranker: MagicMock
    ) -> None:
        """RerankedRetriever satisfies the Retriever protocol."""
        r = RerankedRetriever(inner=mock_inner, reranker=mock_reranker)
        assert isinstance(r, Retriever)

    def test_broadens_candidate_pool(
        self, retriever: RerankedRetriever, mock_inner: MagicMock
    ) -> None:
        """Inner retriever called with pool_size, not the requested k."""
        retriever.retrieve("query", k=10)
        mock_inner.retrieve.assert_called_once_with("query", k=100, doc_ids=None)

    def test_uses_k_multiplier_when_larger(
        self, mock_inner: MagicMock, mock_reranker: MagicMock
    ) -> None:
        """When k * min_pool_ratio > pool_size, uses the larger value."""
        r = RerankedRetriever(
            inner=mock_inner, reranker=mock_reranker,
            pool_size=100, min_pool_ratio=3,
        )
        r.retrieve("query", k=50)
        # k=50 * min_pool_ratio=3 = 150 > pool_size=100
        mock_inner.retrieve.assert_called_once_with("query", k=150, doc_ids=None)

    def test_delegates_to_reranker(
        self,
        retriever: RerankedRetriever,
        mock_reranker: MagicMock,
        inner_results: list[SearchResult],
    ) -> None:
        """Results from inner retriever passed to reranker."""
        retriever.retrieve("query", k=5)
        mock_reranker.rerank.assert_called_once_with("query", inner_results, k=5)

    def test_returns_reranker_output(
        self,
        retriever: RerankedRetriever,
        reranked_results: list[SearchResult],
    ) -> None:
        """retrieve() returns whatever the reranker produces."""
        results = retriever.retrieve("query", k=5)
        assert results == reranked_results

    def test_forwards_doc_ids(
        self, retriever: RerankedRetriever, mock_inner: MagicMock
    ) -> None:
        """doc_ids parameter forwarded to inner retriever."""
        doc_ids = [uuid4(), uuid4()]
        retriever.retrieve("query", k=5, doc_ids=doc_ids)
        mock_inner.retrieve.assert_called_once_with("query", k=100, doc_ids=doc_ids)

    def test_empty_inner_results(
        self, mock_inner: MagicMock, mock_reranker: MagicMock
    ) -> None:
        """When inner retriever returns empty, reranker still called."""
        mock_inner.retrieve.return_value = []
        mock_reranker.rerank.return_value = []
        r = RerankedRetriever(inner=mock_inner, reranker=mock_reranker)
        results = r.retrieve("query", k=5)
        assert results == []
        mock_reranker.rerank.assert_called_once()
