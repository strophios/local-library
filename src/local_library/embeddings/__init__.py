"""Embeddings module - chunking, embedding computation, and vector storage."""

# Lazy imports to prevent circular import on package initialization
# (follows same pattern as ingestion module)


def __getattr__(name: str) -> object:
    """Lazy-load embeddings submodules to avoid circular imports."""
    if name == "Chunker":
        from local_library.embeddings.base import Chunker

        return Chunker
    elif name == "Embedder":
        from local_library.embeddings.base import Embedder

        return Embedder
    elif name == "Chunk":
        from local_library.embeddings.base import Chunk

        return Chunk
    elif name == "ChunkEmbedding":
        from local_library.embeddings.base import ChunkEmbedding

        return ChunkEmbedding
    elif name == "MarkdownChunker":
        from local_library.embeddings.chunking import MarkdownChunker

        return MarkdownChunker
    elif name == "estimate_token_count":
        from local_library.embeddings.chunking import estimate_token_count

        return estimate_token_count
    elif name == "NomicEmbedder":
        from local_library.embeddings.nomic import NomicEmbedder

        return NomicEmbedder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Protocols
    "Chunker",
    "Embedder",
    # Data models
    "Chunk",
    "ChunkEmbedding",
    # Implementations
    "MarkdownChunker",
    "NomicEmbedder",
    # Utilities
    "estimate_token_count",
]
