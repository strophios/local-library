"""Path configuration using platformdirs for XDG-compliant storage."""

# pattern: Mixed (Functional Core with I/O utility)
# Justification: Path getters (lines 16-39) are pure functions with no side effects.
# The ensure_directories() function (lines 42-46) performs I/O (creates directories).
# Grouping them here is intentional for bootstrapping: callers need both path config
# (pure) and directory creation (I/O) during initialization.

from pathlib import Path

from platformdirs import PlatformDirs

# Application identity
APP_NAME = "local-library"

# Platform-specific directory provider
_dirs = PlatformDirs(APP_NAME)


def get_data_dir() -> Path:
    """Return the user data directory for storing database and files.

    Platform paths:
    - macOS: ~/Library/Application Support/local-library
    - Linux: ~/.local/share/local-library
    - Windows: C:/Users/<user>/AppData/Local/local-library
    """
    return Path(_dirs.user_data_dir)


def get_database_path() -> Path:
    """Return the path to the SQLite database file."""
    return get_data_dir() / "library.db"


def get_storage_dir() -> Path:
    """Return the directory for content-addressable file storage."""
    return get_data_dir() / "storage"


def get_extracted_dir() -> Path:
    """Return the directory for extracted markdown files."""
    return get_data_dir() / "extracted"


def ensure_directories() -> None:
    """Create all required directories if they don't exist."""
    get_data_dir().mkdir(parents=True, exist_ok=True)
    get_storage_dir().mkdir(parents=True, exist_ok=True)
    get_extracted_dir().mkdir(parents=True, exist_ok=True)
