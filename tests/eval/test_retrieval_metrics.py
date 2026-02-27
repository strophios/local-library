"""Tests for retrieval evaluation metric computation."""

# pattern: Functional Core

import pytest

from tests.eval.retrieval_eval import (
    EvalReport,
    QueryResult,
    evaluate_query,
    mean_reciprocal_rank,
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
