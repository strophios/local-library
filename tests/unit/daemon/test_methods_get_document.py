"""Tests for the daemon's get_document method handler."""

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from local_library.core.errors import ErrorCode
from local_library.core.errors import LookupError as LibLookupError
from local_library.core.models import DocumentStatus
from local_library.daemon import methods, protocol


def _fake_doc() -> MagicMock:
    doc = MagicMock()
    doc.id = UUID("00000000-0000-0000-0000-000000000001")
    doc.citekey = "Smith2023"
    doc.title = "A Paper"
    doc.authors = "Smith, J."
    doc.issued_year = 2023
    doc.extracted_path = "/tmp/foo.md"
    doc.csl_json = {"id": "Smith2023", "title": "A Paper", "issued": {"date-parts": [[2023]]}}
    doc.status = DocumentStatus.READY
    return doc


def _fake_library_with(doc: MagicMock, chunk_count: int = 12) -> MagicMock:
    library = MagicMock()
    library.get.return_value = doc
    library.get_by_citekey.return_value = doc
    library.get_chunk_count.return_value = chunk_count
    return library


def test_get_document_happy_path() -> None:
    library = _fake_library_with(_fake_doc(), chunk_count=12)
    identifier = "00000000-0000-0000-0000-000000000001"
    result = methods.get_document(library=library, identifier=identifier)
    assert result["doc_id"] == "00000000-0000-0000-0000-000000000001"
    assert result["citekey"] == "Smith2023"
    assert result["csl_json"] == {
        "id": "Smith2023",
        "title": "A Paper",
        "issued": {"date-parts": [[2023]]},
    }
    assert result["title"] == "A Paper"
    assert result["authors"] == ["Smith, J."]
    assert result["year"] == 2023
    assert result["extracted_markdown_path"] == "/tmp/foo.md"
    assert result["chunk_count"] == 12
    assert result["status"] == "ready"


def test_get_document_resolves_citekey() -> None:
    library = _fake_library_with(_fake_doc())
    result = methods.get_document(library=library, identifier="@Smith2023")
    library.get_by_citekey.assert_called_with("Smith2023")
    assert result["doc_id"] == "00000000-0000-0000-0000-000000000001"


def test_get_document_propagates_not_found() -> None:
    library = MagicMock()
    library.get.side_effect = LibLookupError(
        "no such document",
        ErrorCode.NOT_FOUND,
        details={"identifier": "00000000-0000-0000-0000-deadbeefdead"},
    )
    library.get_chunk_count.return_value = 0
    from local_library.core.errors import LocalLibraryError

    with pytest.raises(LocalLibraryError) as exc_info:
        methods.get_document(library=library, identifier="00000000-0000-0000-0000-deadbeefdead")
    assert exc_info.value.code == ErrorCode.NOT_FOUND


def test_get_document_empty_identifier_raises_invalid_params() -> None:
    library = MagicMock()
    with pytest.raises(protocol.InvalidParams):
        methods.get_document(library=library, identifier="")


def test_get_document_csl_json_none_serializes_to_empty_object() -> None:
    doc = _fake_doc()
    doc.csl_json = None
    library = _fake_library_with(doc)
    identifier = "00000000-0000-0000-0000-000000000001"
    result = methods.get_document(library=library, identifier=identifier)
    assert result["csl_json"] == {}


def test_get_document_chunk_count_via_library_method() -> None:
    """chunk_count comes from Library.get_chunk_count, not from the Document."""
    library = _fake_library_with(_fake_doc(), chunk_count=42)
    identifier = "00000000-0000-0000-0000-000000000001"
    result = methods.get_document(library=library, identifier=identifier)
    assert result["chunk_count"] == 42
    library.get_chunk_count.assert_called_with(UUID("00000000-0000-0000-0000-000000000001"))


def test_get_document_unknown_citekey_raises_not_found() -> None:
    """Unknown @citekey should raise NOT_FOUND, not AttributeError."""
    from local_library.core.errors import LocalLibraryError

    library = MagicMock()
    library.get_by_citekey.return_value = None  # production reality: no doc found
    library.get_all_citekeys.return_value = ["Smith2023", "Doe2024"]

    with pytest.raises(LocalLibraryError) as exc_info:
        methods.get_document(library=library, identifier="@DoesNotExist")

    assert exc_info.value.code == ErrorCode.NOT_FOUND
