"""Tests for retrieval evaluation metric computation."""

# pattern: Functional Core

import pytest

from tests.eval.retrieval_eval import (
    EvalReport,
    QueryResult,
    evaluate_query,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


class TestPrecisionAtK:
    """Tests for precision_at_k."""

    def test_all_relevant(self) -> None:
        """All top-k results are relevant."""
        retrieved = ["a", "b", "c"]
        relevant = {"a", "b", "c"}
        assert precision_at_k(retrieved, relevant, 3) == 1.0

    def test_none_relevant(self) -> None:
        """No top-k results are relevant."""
        retrieved = ["x", "y", "z"]
        relevant = {"a", "b", "c"}
        assert precision_at_k(retrieved, relevant, 3) == 0.0

    def test_partial_relevant(self) -> None:
        """Some top-k results are relevant."""
        retrieved = ["a", "x", "b", "y", "c"]
        relevant = {"a", "b", "c"}
        assert precision_at_k(retrieved, relevant, 5) == pytest.approx(3 / 5)

    def test_k_larger_than_results(self) -> None:
        """k exceeds number of retrieved results."""
        retrieved = ["a", "b"]
        relevant = {"a", "b"}
        # Only 2 results for k=5: 2/5 = 0.4
        assert precision_at_k(retrieved, relevant, 5) == pytest.approx(2 / 5)

    def test_k_zero(self) -> None:
        """k=0 returns 0."""
        assert precision_at_k(["a"], {"a"}, 0) == 0.0

    def test_empty_retrieved(self) -> None:
        """Empty retrieved list."""
        assert precision_at_k([], {"a"}, 5) == 0.0


class TestRecallAtK:
    """Tests for recall_at_k."""

    def test_all_found(self) -> None:
        """All relevant documents found in top-k."""
        retrieved = ["a", "b", "c", "x"]
        relevant = {"a", "b", "c"}
        assert recall_at_k(retrieved, relevant, 10) == 1.0

    def test_none_found(self) -> None:
        """No relevant documents in top-k."""
        retrieved = ["x", "y", "z"]
        relevant = {"a", "b"}
        assert recall_at_k(retrieved, relevant, 3) == 0.0

    def test_partial_found(self) -> None:
        """Some relevant documents found."""
        retrieved = ["a", "x", "y"]
        relevant = {"a", "b", "c"}
        assert recall_at_k(retrieved, relevant, 3) == pytest.approx(1 / 3)

    def test_empty_relevant(self) -> None:
        """No relevant documents exist."""
        assert recall_at_k(["a"], set(), 5) == 0.0

    def test_empty_retrieved(self) -> None:
        """Empty retrieved list."""
        assert recall_at_k([], {"a"}, 5) == 0.0


class TestMeanReciprocalRank:
    """Tests for mean_reciprocal_rank."""

    def test_first_result_relevant(self) -> None:
        """First result is relevant: MRR = 1.0."""
        assert mean_reciprocal_rank(["a", "b", "c"], {"a"}) == 1.0

    def test_second_result_relevant(self) -> None:
        """Second result is relevant: MRR = 0.5."""
        assert mean_reciprocal_rank(["x", "a", "b"], {"a"}) == 0.5

    def test_third_result_relevant(self) -> None:
        """Third result is relevant: MRR = 1/3."""
        assert mean_reciprocal_rank(["x", "y", "a"], {"a"}) == pytest.approx(1 / 3)

    def test_no_relevant_found(self) -> None:
        """No relevant result in list: MRR = 0."""
        assert mean_reciprocal_rank(["x", "y", "z"], {"a"}) == 0.0

    def test_empty_retrieved(self) -> None:
        """Empty retrieved list."""
        assert mean_reciprocal_rank([], {"a"}) == 0.0

    def test_multiple_relevant_takes_first(self) -> None:
        """MRR uses the first relevant result only."""
        assert mean_reciprocal_rank(["x", "a", "b"], {"a", "b"}) == 0.5


class TestNDCGAtK:
    """Tests for NDCG@k metric."""

    def test_perfect_ranking(self) -> None:
        """All relevant docs at top positions yields NDCG of 1.0."""
        retrieved = ["a", "b", "c", "d"]
        relevant = {"a", "b"}
        assert ndcg_at_k(retrieved, relevant, k=4) == pytest.approx(1.0)

    def test_reversed_ranking(self) -> None:
        """Relevant docs at bottom positions yields NDCG < 1.0."""
        retrieved = ["c", "d", "a", "b"]
        relevant = {"a", "b"}
        result = ndcg_at_k(retrieved, relevant, k=4)
        assert 0.0 < result < 1.0

    def test_no_relevant_found(self) -> None:
        """No relevant docs retrieved yields NDCG of 0.0."""
        retrieved = ["c", "d", "e"]
        relevant = {"a", "b"}
        assert ndcg_at_k(retrieved, relevant, k=3) == pytest.approx(0.0)

    def test_empty_retrieved(self) -> None:
        """Empty retrieved list yields NDCG of 0.0."""
        assert ndcg_at_k([], {"a", "b"}, k=5) == pytest.approx(0.0)

    def test_empty_relevant(self) -> None:
        """Empty relevant set yields NDCG of 0.0."""
        assert ndcg_at_k(["a", "b"], set(), k=5) == pytest.approx(0.0)

    def test_k_truncates(self) -> None:
        """Only first k results considered."""
        retrieved = ["c", "a", "b"]
        relevant = {"a", "b"}
        result_k1 = ndcg_at_k(retrieved, relevant, k=1)
        result_k3 = ndcg_at_k(retrieved, relevant, k=3)
        assert result_k1 == pytest.approx(0.0)
        assert result_k3 > 0.0

    def test_single_relevant_at_position_1(self) -> None:
        """Single relevant doc at position 1 yields NDCG of 1.0."""
        retrieved = ["a", "b", "c"]
        relevant = {"a"}
        assert ndcg_at_k(retrieved, relevant, k=3) == pytest.approx(1.0)

    def test_known_value(self) -> None:
        """Verify against hand-calculated NDCG@5 value."""
        # Positions: 1=irrel, 2=rel, 3=irrel, 4=rel, 5=irrel
        # DCG  = 0 + 1/log2(3) + 0 + 1/log2(5) = 0.6309 + 0.4307 = 1.0616
        # IDCG = 1/log2(2) + 1/log2(3) = 1.0 + 0.6309 = 1.6309
        # NDCG = 1.0616 / 1.6309 ≈ 0.6509
        retrieved = ["c", "a", "d", "b", "e"]
        relevant = {"a", "b"}
        assert ndcg_at_k(retrieved, relevant, k=5) == pytest.approx(0.6509, abs=0.001)


class TestEvaluateQuery:
    """Tests for evaluate_query."""

    def test_computes_all_metrics(self) -> None:
        """evaluate_query returns QueryResult with all metrics."""
        query = {
            "id": "q1",
            "text": "test query",
            "category": "factual",
            "relevant_docs": ["a", "b"],
        }
        retrieved = ["a", "x", "b", "y", "z"]

        result = evaluate_query(query, retrieved)

        assert isinstance(result, QueryResult)
        assert result.query_id == "q1"
        assert result.category == "factual"
        assert result.precision_at_5 == pytest.approx(2 / 5)
        assert result.recall_at_10 == 1.0  # Both found in top 5
        assert result.mrr == 1.0  # First result is relevant


class TestEvalReport:
    """Tests for EvalReport aggregate metrics."""

    def test_empty_report(self) -> None:
        """Empty report returns 0 for all metrics."""
        report = EvalReport()
        assert report.mean_precision_at_5 == 0.0
        assert report.mean_recall_at_10 == 0.0
        assert report.mean_mrr == 0.0

    def test_aggregate_metrics(self) -> None:
        """Report computes correct averages across queries."""
        report = EvalReport()
        report.add(
            QueryResult(
                query_id="q1",
                query_text="q1",
                category="factual",
                precision_at_5=0.8,
                precision_at_10=0.6,
                recall_at_10=1.0,
                mrr=1.0,
                retrieved_docs=[],
                relevant_docs=[],
            )
        )
        report.add(
            QueryResult(
                query_id="q2",
                query_text="q2",
                category="factual",
                precision_at_5=0.4,
                precision_at_10=0.3,
                recall_at_10=0.5,
                mrr=0.5,
                retrieved_docs=[],
                relevant_docs=[],
            )
        )

        assert report.mean_precision_at_5 == pytest.approx(0.6)
        assert report.mean_mrr == pytest.approx(0.75)

    def test_results_by_category(self) -> None:
        """Report groups results by category."""
        report = EvalReport()
        report.add(
            QueryResult(
                query_id="q1",
                query_text="q1",
                category="factual",
                precision_at_5=0.8,
                precision_at_10=0.6,
                recall_at_10=1.0,
                mrr=1.0,
                retrieved_docs=[],
                relevant_docs=[],
            )
        )
        report.add(
            QueryResult(
                query_id="q2",
                query_text="q2",
                category="conceptual",
                precision_at_5=0.4,
                precision_at_10=0.3,
                recall_at_10=0.5,
                mrr=0.5,
                retrieved_docs=[],
                relevant_docs=[],
            )
        )

        by_cat = report.results_by_category()
        assert "factual" in by_cat
        assert "conceptual" in by_cat
        assert len(by_cat["factual"]) == 1

    def test_format_summary(self) -> None:
        """format_summary produces human-readable output."""
        report = EvalReport()
        report.add(
            QueryResult(
                query_id="q1",
                query_text="q1",
                category="factual",
                precision_at_5=0.8,
                precision_at_10=0.6,
                recall_at_10=1.0,
                mrr=1.0,
                retrieved_docs=[],
                relevant_docs=[],
            )
        )

        summary = report.format_summary()
        assert "Precision@5" in summary
        assert "Recall@10" in summary
        assert "MRR" in summary

    def test_to_dict(self) -> None:
        """to_dict produces JSON-serializable output."""
        report = EvalReport()
        report.add(
            QueryResult(
                query_id="q1",
                query_text="q1",
                category="factual",
                precision_at_5=0.8,
                precision_at_10=0.6,
                recall_at_10=1.0,
                mrr=1.0,
                retrieved_docs=[],
                relevant_docs=[],
            )
        )

        d = report.to_dict()
        assert "total_queries" in d
        assert d["total_queries"] == 1
        assert "mean_precision_at_5" in d
        assert "by_category" in d
