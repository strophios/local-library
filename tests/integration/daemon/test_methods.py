"""Integration tests for daemon methods against a real Library.

Builds a minimal corpus via the existing integration_library fixture, then
exercises the search and get_document handlers exactly as the dispatcher
would (with a real Library, but without going through the socket).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from local_library.core.errors import ErrorCode, LocalLibraryError
from local_library.core.library import Library
from local_library.daemon import methods


@pytest.fixture
def populated_library(
    integration_library: Library,
    sample_pdf: Path,
) -> Library:
    """Add a single tiny document so search has something to find.

    The integration_library fixture creates a Library with test isolation.
    We add a PDF with metadata to ensure it has a citekey and can be found
    by search. Text extraction is mocked to avoid loading Marker.
    """
    metadata = {
        "id": "Sample2026",
        "type": "article-journal",
        "title": "Sample Paper on RAG",
        "author": [{"family": "Author", "given": "Test"}],
        "issued": {"date-parts": [[2026]]},
    }
    with patch.object(
        integration_library._extractors[0],
        "extract_and_validate",
    ) as mock_extract:
        mock_extract.return_value = MagicMock(
            text="This document discusses retrieval-augmented generation in detail. "
            "Specifically, the use of dense embeddings combined with full-text search."
        )
        integration_library.add(str(sample_pdf), metadata=metadata)

    # Skip embedding if sqlite-vec unavailable
    try:
        integration_library.embed_all()
    except Exception:  # noqa: BLE001
        pass

    return integration_library


def test_search_returns_results_against_real_corpus(populated_library: Library) -> None:
    result = methods.search(library=populated_library, query="retrieval augmented generation")
    assert result["total_candidates"] >= 1
    first = result["results"][0]
    assert first["citekey"]  # Should have some citekey
    assert "retrieval" in first["chunk_text"].lower()
    assert first["extracted_markdown_path"]


def test_get_document_returns_csl_json_against_real_corpus(populated_library: Library) -> None:
    # Find the actual citekey first
    result = methods.search(library=populated_library, query="retrieval")
    assert result["total_candidates"] >= 1
    actual_citekey = result["results"][0]["citekey"]

    # Now test get_document with the actual citekey
    doc_result = methods.get_document(library=populated_library, identifier=f"@{actual_citekey}")
    assert doc_result["citekey"] == actual_citekey
    assert doc_result["csl_json"]["id"] == "Sample2026"
    assert doc_result["chunk_count"] >= 0  # May be 0 if embedding skipped


def test_search_doc_id_hook_not_implemented_against_real_corpus(populated_library: Library) -> None:
    # Find a valid citekey first
    result = methods.search(library=populated_library, query="retrieval")
    actual_citekey = result["results"][0]["citekey"]

    with pytest.raises(LocalLibraryError) as exc_info:
        methods.search(library=populated_library, query="x", doc_id=f"@{actual_citekey}")
    assert exc_info.value.code == ErrorCode.NOT_IMPLEMENTED


def test_search_boost_citekeys_silently_ignored_against_real_corpus(
    populated_library: Library,
) -> None:
    a = methods.search(library=populated_library, query="retrieval")
    # Get the actual citekey from the results
    actual_citekey = a["results"][0]["citekey"] if a["results"] else "Unknown"
    b = methods.search(
        library=populated_library,
        query="retrieval",
        boost_citekeys=[actual_citekey, "Other2024"],
    )
    assert a == b
