"""JSON-RPC method handlers for the daemon.

# pattern: Mixed — handlers orchestrate Library calls (Imperative); the
# serialization helpers (_serialize_search_result, etc.) are pure (Functional Core).

The Library is passed in as an argument rather than imported globally so that
unit tests can inject a mock Library without needing the real Library
constructed. The server-side wiring (server.py:build_dispatcher) provides the
Library singleton at registration time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from local_library.core.errors import ErrorCode, LocalLibraryError
from local_library.daemon import protocol

if TYPE_CHECKING:
    from local_library.core.library import Library
    from local_library.core.models import Document
    from local_library.embeddings.base import SearchResult

VALID_MODES = {"hybrid", "vector", "fts"}


# Note: `search` and `get_document` are plain sync functions, not coroutines.
# They run on the library executor thread (no real awaits inside). The
# dispatcher's executor wrapper (server.build_dispatcher) bridges sync ↔
# async at the executor boundary; keeping the handlers themselves sync
# avoids spinning up a per-request event loop via `asyncio.run`.


def search(
    *,
    library: Library,
    query: str,
    mode: str = "hybrid",
    limit: int = 10,
    rerank: bool = True,
    doc_id: str | None = None,
    boost_citekeys: list[str] | None = None,
) -> dict[str, Any]:
    """Run a retrieval search and return the wire-shape result.

    Hook semantics (per design doc §"Structural hooks"):
    - `doc_id` (loud-error): non-null raises NOT_IMPLEMENTED so the client
      can surface "scoping not yet available" rather than silently returning
      whole-corpus results.
    - `boost_citekeys` (silent-inert): accepted and ignored. The plugin
      passes it routinely so a future daemon-side rollout requires no plugin
      change.
    """
    if not query or not query.strip():
        raise protocol.InvalidParams("'query' must be a non-empty string")
    if mode not in VALID_MODES:
        raise protocol.InvalidParams(f"'mode' must be one of {sorted(VALID_MODES)} (got {mode!r})")
    if not isinstance(limit, int) or limit < 1 or limit > 100:
        raise protocol.InvalidParams("'limit' must be an integer in [1, 100]")

    if doc_id is not None:
        raise LocalLibraryError(
            "document-scoped search is not yet implemented",
            ErrorCode.NOT_IMPLEMENTED,
            details={"hook": "doc_id"},
        )
    _ = boost_citekeys  # silent-inert

    retriever = library.get_retriever(mode=mode, rerank=rerank)
    results = retriever.retrieve(query=query, k=limit, doc_ids=None)

    serialized = [
        _serialize_search_result(library=library, result=r, reranked=rerank) for r in results
    ]
    return {
        "results": serialized,
        "total_candidates": len(serialized),
        "reranked": rerank,
    }


def _serialize_search_result(
    *,
    library: Library,
    result: SearchResult,
    reranked: bool,
) -> dict[str, Any]:
    """Project a (SearchResult, joined Document) pair to the RPC wire shape."""
    doc = library.get(str(result.chunk.doc_id))
    payload: dict[str, Any] = {
        "chunk_id": result.chunk.chunk_id,
        "doc_id": str(result.chunk.doc_id),
        "citekey": doc.citekey or "",
        "document_title": doc.title or "",
        "document_authors": _split_authors(doc.authors),
        "document_year": doc.issued_year,
        "score": float(result.score),
        "chunk_text": result.chunk.text,
        "chunk_section_heading": result.chunk.section or None,
        "extracted_markdown_path": doc.extracted_path or "",
    }
    if reranked:
        # NB: rerank_score mirrors score intentionally — the current Library
        # API overwrites the pre-rerank score in place, so we don't have a
        # distinct value to expose. Preserving both is a deferred enhancement.
        payload["rerank_score"] = float(result.score)
    return payload


def _split_authors(authors: str | None) -> list[str]:
    """The Document model stores authors as 'Last, First; Last, First' strings.
    Wire shape is a list. Empty string → empty list.
    """
    if not authors:
        return []
    return [a.strip() for a in authors.split(";") if a.strip()]


def get_document(
    *,
    library: Library,
    identifier: str,
) -> dict[str, Any]:
    """Return full metadata for a document, including its CSL-JSON entry.

    The plugin uses this to populate the bibliography auto-append on insert.
    Identifier is either a UUID (full) or '@citekey'.
    """
    if not identifier or not identifier.strip():
        raise protocol.InvalidParams("'identifier' must be a non-empty string")

    if identifier.startswith("@"):
        doc = library.get_by_citekey(identifier[1:])
    else:
        doc = library.get(identifier)

    return _serialize_document(library, doc)


def _serialize_document(library: Library, doc: Document) -> dict[str, Any]:
    # chunk_count lives on Library (Library.get_chunk_count), not on the
    # Document dataclass. Best-effort: 0 if the call fails (e.g., document
    # has not been embedded yet).
    try:
        chunk_count = int(library.get_chunk_count(doc.id))
    except Exception:  # noqa: BLE001 — degrade gracefully on any storage failure
        chunk_count = 0
    return {
        "doc_id": str(doc.id),
        "citekey": doc.citekey or "",
        "csl_json": doc.csl_json or {},
        "title": doc.title or "",
        "authors": _split_authors(doc.authors),
        "year": doc.issued_year,
        "extracted_markdown_path": doc.extracted_path or "",
        "chunk_count": chunk_count,
        "status": doc.status.value if hasattr(doc.status, "value") else str(doc.status),
    }
