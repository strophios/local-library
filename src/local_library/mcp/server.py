"""MCP server — wraps Library API for Claude Code integration."""

# pattern: Imperative Shell

import logging
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from local_library.cli.utils import resolve_identifier
from local_library.core.errors import EmbeddingError, FTSQueryError, LookupError
from local_library.core.library import Library
from local_library.core.models import DocumentStatus
from local_library.core.vec_extension import is_vec_available
from local_library.mcp.formatters import (
    format_document,
    format_document_list,
    format_document_text,
    format_search_results,
    format_tool_error,
    format_user_error,
)

logger = logging.getLogger(__name__)

# Valid search modes
VALID_MODES = ("hybrid", "vector", "fts")

# Valid document status filters
VALID_STATUSES = ("ready", "failed", "needs_review", "pending")

# Threshold for "short" documents (full text returned)
SHORT_DOC_THRESHOLD = 50

# Number of chunks to show in preview mode
PREVIEW_CHUNK_COUNT = 20

# FastMCP application
mcp = FastMCP("local-library")

# Library instance (created in main(), shared across tool calls)
_library: Library | None = None


@mcp.tool(
    description=(
        "Search the document library using semantic and keyword search. "
        "Returns markdown with ranked results including citekeys, scores, "
        "section headers, and chunk text. Use chunk indices for follow-up "
        "get_document_text calls. "
        "Errors prefixed with 'USER-FACING ERROR' should be reported to "
        "the user rather than worked around."
    )
)
def search_library(
    query: str,
    limit: int = 10,
    mode: str = "hybrid",
    doc_id: str | None = None,
    no_rerank: bool = False,
) -> str:
    """Search the document library.

    Args:
        query: Search query string (natural language or keywords)
        limit: Maximum results to return (1-100, default 10)
        mode: Search mode — "hybrid" (default), "vector", or "fts"
        doc_id: Optional UUID or @citekey to scope search to one document
        no_rerank: Disable cross-encoder reranking (default: False)
    """
    assert _library is not None, "Library not initialized"

    # Validate and clamp limit
    limit = max(1, min(limit, 100))

    # Validate mode
    if mode not in VALID_MODES:
        return format_tool_error(f"invalid mode: {mode}. Expected one of: {', '.join(VALID_MODES)}")

    # Check sqlite-vec availability (required for vector and hybrid modes, not FTS)
    if mode != "fts" and not is_vec_available():
        return format_user_error(
            "Vector search unavailable. The sqlite-vec extension is not loaded. "
            "This significantly impacts search quality. Please inform the user "
            "and suggest running `uv run local-library search` from the terminal "
            "to diagnose. You can still search using mode='fts' for keyword matching."
        )

    try:
        # Resolve document filter if provided
        doc_ids = None
        if doc_id:
            doc = resolve_identifier(doc_id, _library)
            doc_ids = [doc.id]

        # Get retriever and search
        retriever = _library.get_retriever(mode=mode, rerank=not no_rerank)
        results = retriever.retrieve(query, k=limit, doc_ids=doc_ids)

        return format_search_results(results, query)

    except LookupError as e:
        suggestions = e.details.get("suggestions", [])
        if suggestions:
            suggestion_text = ", ".join(f"@{s}" for s in suggestions)
            return format_tool_error(f"{e.message}. Did you mean {suggestion_text}?")
        return format_tool_error(e.message)
    except FTSQueryError as e:
        return format_tool_error(f"{e.message}. Try a different search query or use mode='vector'.")
    except EmbeddingError as e:
        return format_user_error(str(e))


@mcp.tool(
    description=(
        "Show metadata for a specific document. Returns citekey, title, "
        "authors, date, status, embedding status, chunk count, and "
        "CSL-JSON metadata fields. Accepts UUID (full or partial) or "
        "@citekey identifier. On identifier miss, returns fuzzy match "
        "suggestions. "
        "Errors prefixed with 'USER-FACING ERROR' should be reported to "
        "the user rather than worked around."
    )
)
def show_document(doc_id: str) -> str:
    """Show metadata for a specific document.

    Args:
        doc_id: UUID (full or partial) or @citekey identifier
    """
    assert _library is not None, "Library not initialized"

    try:
        doc = resolve_identifier(doc_id, _library)
        chunk_count = _library.get_chunk_count(doc.id)
        return format_document(doc, chunk_count)

    except LookupError as e:
        suggestions = e.details.get("suggestions", [])
        if suggestions:
            suggestion_text = ", ".join(f"@{s}" for s in suggestions)
            return format_tool_error(
                f"No document found matching '{doc_id}'. Did you mean {suggestion_text}?"
            )
        return format_tool_error(f"No document found matching '{doc_id}'.")


@mcp.tool(
    description=(
        "List documents in the library. Returns a markdown table with "
        "citekey, title, authors, status, and embedding status. "
        "Errors prefixed with 'USER-FACING ERROR' should be reported to "
        "the user rather than worked around."
    )
)
def list_documents(
    status: str | None = None,
    limit: int = 20,
) -> str:
    """List documents in the library.

    Args:
        status: Optional filter — "ready", "failed", "needs_review", or "pending"
        limit: Maximum results to return (1-100, default 20)
    """
    assert _library is not None, "Library not initialized"

    # Validate and clamp limit
    limit = max(1, min(limit, 100))

    # Validate and parse status filter
    status_filter = None
    if status:
        if status.lower() not in VALID_STATUSES:
            return format_tool_error(
                f"invalid status: {status}. Expected one of: {', '.join(VALID_STATUSES)}"
            )
        status_filter = DocumentStatus(status.lower())

    try:
        all_docs = _library.list(status=status_filter)
        total = len(all_docs)
        displayed = all_docs[:limit]
        return format_document_list(displayed, total)
    except Exception as e:
        logger.exception("Error listing documents")
        return format_user_error(f"Failed to list documents: {e}")


@mcp.tool(
    description=(
        "Get the extracted text content of a document. Short documents "
        "(<50 chunks) return full text. Long documents without a chunk "
        "range return a preview with section outline and instructions "
        "for requesting specific ranges. Specify start_chunk and "
        "end_chunk (0-based, inclusive) for a specific section. "
        "Errors prefixed with 'USER-FACING ERROR' should be reported to "
        "the user rather than worked around."
    )
)
def get_document_text(
    doc_id: str,
    start_chunk: int | None = None,
    end_chunk: int | None = None,
) -> str:
    """Get extracted text content of a document.

    Args:
        doc_id: UUID (full or partial) or @citekey identifier
        start_chunk: Optional 0-based chunk index to start from
        end_chunk: Optional chunk index to end at (inclusive)
    """
    assert _library is not None, "Library not initialized"

    try:
        doc = resolve_identifier(doc_id, _library)
    except LookupError as e:
        suggestions = e.details.get("suggestions", [])
        if suggestions:
            suggestion_text = ", ".join(f"@{s}" for s in suggestions)
            return format_tool_error(
                f"No document found matching '{doc_id}'. Did you mean {suggestion_text}?"
            )
        return format_tool_error(f"No document found matching '{doc_id}'.")

    # Check that extracted text exists
    if not doc.extracted_path:
        return format_tool_error(
            f"No extracted text available for @{doc.citekey or doc_id}. "
            f"Document status: {doc.status.value}"
        )

    total_chunks = _library.get_chunk_count(doc.id)

    # Short document: return full extracted markdown
    if total_chunks < SHORT_DOC_THRESHOLD:
        try:
            text = Path(doc.extracted_path).read_text(encoding="utf-8")
        except FileNotFoundError:
            return format_tool_error(
                f"Extracted file not found at {doc.extracted_path}. "
                "The file may have been moved or deleted."
            )
        return format_document_text(doc, text=text, chunks=None, total_chunks=total_chunks)

    # Long document with range: return chunk subset
    if start_chunk is not None or end_chunk is not None:
        s = start_chunk if start_chunk is not None else 0
        e = end_chunk if end_chunk is not None else total_chunks - 1

        if s < 0 or e < 0:
            return format_tool_error("Chunk indices must be non-negative.")
        if s > e:
            return format_tool_error(f"start_chunk ({s}) must be <= end_chunk ({e}).")
        if s >= total_chunks:
            return format_tool_error(
                f"start_chunk ({s}) out of range. "
                f"Document has {total_chunks} chunks (0-{total_chunks - 1})."
            )

        chunks = _library.get_chunks(doc.id, start=s, end=e)
        return format_document_text(
            doc,
            text=None,
            chunks=chunks,
            total_chunks=total_chunks,
            start_chunk=s,
            end_chunk=min(e, total_chunks - 1),
        )

    # Long document without range: preview mode
    chunks = _library.get_chunks(doc.id, start=0, end=PREVIEW_CHUNK_COUNT - 1)
    return format_document_text(doc, text=None, chunks=chunks, total_chunks=total_chunks)


def main() -> None:
    """Entry point for the MCP server."""
    global _library

    # Configure all logging to stderr (stdout reserved for JSON-RPC protocol)
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Suppress HuggingFace tokenizer parallelism warning
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    logger.info("Starting local-library MCP server")

    # Create Library instance (read-only, no embed-on-add)
    _library = Library(embed_on_add=False)

    try:
        mcp.run(transport="stdio")
    finally:
        if _library is not None:
            _library.close()
            logger.info("Library closed")
