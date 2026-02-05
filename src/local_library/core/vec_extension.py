"""sqlite-vec extension loading utilities."""

# pattern: Imperative Shell

import sqlite3

from local_library.core.errors import EmbeddingError, ErrorCode

# Module-level state for tracking extension availability
_extension_available: bool | None = None
_extension_error: str | None = None


def load_vec_extension(conn: sqlite3.Connection) -> bool:
    """Load sqlite-vec extension into the given connection.

    This function attempts to load the sqlite-vec extension. It caches the
    result of the first attempt to avoid repeated failure messages.

    Args:
        conn: SQLite connection to load extension into

    Returns:
        True if extension loaded successfully, False otherwise

    Note:
        On macOS, the system Python may not support loading extensions.
        Use Homebrew Python or python.org Python for extension support.
    """
    global _extension_available, _extension_error

    # If we've already determined extension is unavailable, return early
    if _extension_available is False:
        return False

    try:
        import sqlite_vec

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)

        _extension_available = True
        return True

    except ImportError as e:
        _extension_available = False
        _extension_error = f"sqlite-vec package not installed: {e}"
        return False

    except Exception as e:
        _extension_available = False
        _extension_error = f"failed to load sqlite-vec extension: {e}"
        return False


def is_vec_available() -> bool:
    """Check if sqlite-vec extension is available.

    Returns:
        True if extension is available, False otherwise
    """
    if _extension_available is None:
        # Test with an in-memory database
        test_conn = sqlite3.connect(":memory:")
        load_vec_extension(test_conn)
        test_conn.close()

    return _extension_available is True


def get_vec_error() -> str | None:
    """Get the error message if sqlite-vec extension failed to load.

    Returns:
        Error message string, or None if extension loaded successfully
    """
    return _extension_error


def require_vec_extension(conn: sqlite3.Connection) -> None:
    """Load sqlite-vec extension, raising an error if unavailable.

    Args:
        conn: SQLite connection to load extension into

    Raises:
        EmbeddingError: If extension cannot be loaded
    """
    if not load_vec_extension(conn):
        raise EmbeddingError(
            _extension_error or "sqlite-vec extension unavailable",
            ErrorCode.EMBEDDING_EXTENSION_UNAVAILABLE,
        )


def create_vec0_table(
    conn: sqlite3.Connection,
    table_name: str,
    dimensions: int = 768,
    distance_metric: str = "cosine",
) -> None:
    """Create a vec0 virtual table for vector storage.

    Args:
        conn: SQLite connection (must have sqlite-vec loaded)
        table_name: Name for the virtual table
        dimensions: Vector dimensions (default: 768 for nomic-embed-text-v1.5)
        distance_metric: Distance metric ('cosine', 'L2', 'L1')

    Raises:
        EmbeddingError: If table creation fails
    """
    # Validate distance metric
    valid_metrics = {"cosine", "L2", "L1"}
    if distance_metric.lower() not in {m.lower() for m in valid_metrics}:
        raise EmbeddingError(
            f"invalid distance metric: {distance_metric}. Must be one of {valid_metrics}",
            ErrorCode.EMBEDDING_STORAGE_FAILED,
        )

    # Use uppercase for SQL compatibility
    metric = distance_metric.upper() if distance_metric.lower() != "cosine" else "COSINE"

    try:
        conn.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {table_name} USING vec0(
                chunk_id TEXT PRIMARY KEY,
                embedding FLOAT[{dimensions}] DISTANCE_METRIC={metric}
            )
        """)
        conn.commit()
    except sqlite3.Error as e:
        raise EmbeddingError(
            f"failed to create vec0 table {table_name}: {e}",
            ErrorCode.EMBEDDING_STORAGE_FAILED,
        ) from e
