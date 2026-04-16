"""MCP server — wraps Library API for Claude Code integration."""

# pattern: Imperative Shell

import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

from local_library.cli.utils import resolve_identifier
from local_library.core.errors import EmbeddingError, FTSQueryError, LookupError
from local_library.core.library import Library
from local_library.core.vec_extension import is_vec_available
from local_library.mcp.formatters import (
    format_search_results,
    format_tool_error,
    format_user_error,
)

logger = logging.getLogger(__name__)

# Valid search modes
VALID_MODES = ("hybrid", "vector", "fts")

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
        return format_tool_error(
            f"invalid mode: {mode}. Expected one of: {', '.join(VALID_MODES)}"
        )

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
            return format_tool_error(
                f"{e.message}. Did you mean {suggestion_text}?"
            )
        return format_tool_error(e.message)
    except FTSQueryError as e:
        return format_tool_error(
            f"{e.message}. Try a different search query or use mode='vector'."
        )
    except EmbeddingError as e:
        return format_user_error(str(e))


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
