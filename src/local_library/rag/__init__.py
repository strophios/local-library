"""RAG query interface - context assembly, prompt construction, and generation."""

# Lazy imports to prevent circular import on package initialization
# (follows same pattern as embeddings and ingestion modules)


def __getattr__(name: str) -> object:
    """Lazy-load rag submodules to avoid circular imports."""
    if name == "RAGInterface":
        from local_library.rag.interface import RAGInterface

        return RAGInterface
    elif name == "assemble_context":
        from local_library.rag.interface import assemble_context

        return assemble_context
    elif name == "build_messages":
        from local_library.rag.interface import build_messages

        return build_messages
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "RAGInterface",
    "assemble_context",
    "build_messages",
]
