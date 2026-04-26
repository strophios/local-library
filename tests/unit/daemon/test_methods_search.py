"""Tests for the daemon's search method handler.

Uses a mocked Library so this tests handler logic + serialization without
loading the real embedder or sqlite-vec. The end-to-end smoke test against a
real corpus lives in tests/integration/daemon/test_methods.py (Task 4).
"""

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from local_library.core.errors import EmbeddingError, ErrorCode
from local_library.daemon import methods, protocol


def _fake_chunk(
    chunk_id: str = "c-1",
    doc_id: str = "00000000-0000-0000-0000-000000000001",
    text: str = "the quick brown fox",
    section: str = "Introduction",
) -> MagicMock:
    chunk = MagicMock()
    chunk.chunk_id = chunk_id
    chunk.doc_id = UUID(doc_id)
    chunk.text = text
    chunk.section = section
    return chunk


def _fake_search_result(
    chunk_id: str = "c-1",
    doc_id: str = "00000000-0000-0000-0000-000000000001",
    score: float = 0.9,
    title: str = "A Paper",
    citekey: str = "Smith2023",
) -> MagicMock:
    result = MagicMock()
    result.chunk = _fake_chunk(chunk_id=chunk_id, doc_id=doc_id)
    result.score = score
    result.doc_title = title
    result.doc_citekey = citekey
    return result


def _fake_document(
    doc_id: str = "00000000-0000-0000-0000-000000000001",
    citekey: str = "Smith2023",
    title: str = "A Paper",
    authors: str = "Smith, J.; Doe, A.",
    issued_year: int = 2023,
    extracted_path: str = "/tmp/extracted/ab/cd/foo.md",
) -> MagicMock:
    doc = MagicMock()
    doc.id = UUID(doc_id)
    doc.citekey = citekey
    doc.title = title
    doc.authors = authors
    doc.issued_year = issued_year
    doc.extracted_path = extracted_path
    doc.csl_json = {"id": citekey, "title": title}
    return doc


@pytest.fixture
def fake_library() -> MagicMock:
    lib = MagicMock()
    retriever = MagicMock()
    retriever.retrieve.return_value = [_fake_search_result()]
    lib.get_retriever.return_value = retriever
    lib.get.return_value = _fake_document()
    return lib


def _run(value):
    # Handlers are now plain sync functions; this shim stays for symmetry
    # with prior test code and so adding `async` later doesn't churn callers.
    return value


def test_search_happy_path_returns_well_shaped_result(fake_library: MagicMock) -> None:
    result = _run(methods.search(library=fake_library, query="hello"))
    assert result["total_candidates"] == 1
    assert result["reranked"] is True
    assert len(result["results"]) == 1
    r = result["results"][0]
    assert r["chunk_id"] == "c-1"
    assert r["doc_id"] == "00000000-0000-0000-0000-000000000001"
    assert r["citekey"] == "Smith2023"
    assert r["document_title"] == "A Paper"
    assert r["document_authors"] == ["Smith, J.", "Doe, A."]
    assert r["document_year"] == 2023
    assert r["score"] == pytest.approx(0.9)
    assert r["rerank_score"] == pytest.approx(0.9)
    assert r["chunk_text"] == "the quick brown fox"
    assert r["chunk_section_heading"] == "Introduction"
    assert r["extracted_markdown_path"] == "/tmp/extracted/ab/cd/foo.md"


def test_search_passes_mode_and_limit_through(fake_library: MagicMock) -> None:
    _run(methods.search(library=fake_library, query="q", mode="vector", limit=5))
    fake_library.get_retriever.assert_called_with(mode="vector", rerank=True)
    retriever = fake_library.get_retriever.return_value
    retriever.retrieve.assert_called_with(query="q", k=5, doc_ids=None)


def test_search_rerank_false_reflected_in_response(fake_library: MagicMock) -> None:
    result = _run(methods.search(library=fake_library, query="q", rerank=False))
    fake_library.get_retriever.assert_called_with(mode="hybrid", rerank=False)
    assert result["reranked"] is False
    assert "rerank_score" not in result["results"][0]


def test_search_invalid_mode_raises_invalid_params(fake_library: MagicMock) -> None:
    with pytest.raises(protocol.InvalidParams):
        _run(methods.search(library=fake_library, query="q", mode="bogus"))


def test_search_empty_query_raises_invalid_params(fake_library: MagicMock) -> None:
    with pytest.raises(protocol.InvalidParams):
        _run(methods.search(library=fake_library, query=""))


def test_search_doc_id_hook_returns_not_implemented(fake_library: MagicMock) -> None:
    """Loud-error hook: scoping by doc_id is not yet implemented."""
    from local_library.core.errors import LocalLibraryError

    with pytest.raises(LocalLibraryError) as exc_info:
        _run(methods.search(library=fake_library, query="q", doc_id="@Smith2023"))
    assert exc_info.value.code == ErrorCode.NOT_IMPLEMENTED


def test_search_boost_citekeys_silently_ignored(fake_library: MagicMock) -> None:
    """Silent-inert hook: boost_citekeys is accepted and ignored."""
    result_a = _run(methods.search(library=fake_library, query="q"))
    result_b = _run(methods.search(library=fake_library, query="q", boost_citekeys=["Smith2023"]))
    assert result_a == result_b


def test_search_propagates_embedding_extension_error(fake_library: MagicMock) -> None:
    fake_library.get_retriever.side_effect = EmbeddingError(
        "sqlite-vec missing", ErrorCode.EMBEDDING_EXTENSION_UNAVAILABLE
    )
    from local_library.core.errors import LocalLibraryError

    with pytest.raises(LocalLibraryError) as exc_info:
        _run(methods.search(library=fake_library, query="q"))
    assert exc_info.value.code == ErrorCode.EMBEDDING_EXTENSION_UNAVAILABLE


def test_search_authors_none_serializes_to_empty_list(fake_library: MagicMock) -> None:
    doc = _fake_document(authors=None)
    fake_library.get.return_value = doc
    result = _run(methods.search(library=fake_library, query="q"))
    assert result["results"][0]["document_authors"] == []


def test_search_year_none_serializes_to_null(fake_library: MagicMock) -> None:
    doc = _fake_document(issued_year=None)
    fake_library.get.return_value = doc
    result = _run(methods.search(library=fake_library, query="q"))
    assert result["results"][0]["document_year"] is None
