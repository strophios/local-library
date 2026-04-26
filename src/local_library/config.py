"""Path configuration using platformdirs for XDG-compliant storage."""

# pattern: Mixed (Functional Core with I/O utility)
# Justification: Path getters (lines 16-39) are pure functions with no side effects.
# The ensure_directories() function (lines 42-46) performs I/O (creates directories).
# Grouping them here is intentional for bootstrapping: callers need both path config
# (pure) and directory creation (I/O) during initialization.

import os
from pathlib import Path

from platformdirs import PlatformDirs

# Application identity
APP_NAME = "local-library"

# Platform-specific directory provider
_dirs = PlatformDirs(APP_NAME)


def get_data_dir() -> Path:
    """Return the user data directory, with optional env-var override.

    LOCAL_LIBRARY_DATA_DIR, when set, fully overrides the platformdirs default.
    Used by integration tests to isolate the daemon from the user's real
    ~/Library/Application Support/local-library directory.

    Platform paths (default, without override):
    - macOS: ~/Library/Application Support/local-library
    - Linux: ~/.local/share/local-library
    - Windows: C:/Users/<user>/AppData/Local/local-library
    """
    override = os.environ.get("LOCAL_LIBRARY_DATA_DIR")
    if override:
        return Path(override)
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


def get_daemon_pid_path() -> Path:
    """Path to the daemon PID file (data dir)."""
    return get_data_dir() / "daemon.pid"


def get_socket_path() -> Path:
    """Path to the daemon's Unix domain socket (data dir)."""
    return get_data_dir() / "daemon.sock"


def get_daemon_log_dir() -> Path:
    """Directory for daemon log files (data dir / logs)."""
    return get_data_dir() / "logs"


def ensure_directories() -> None:
    """Create all required directories if they don't exist."""
    get_data_dir().mkdir(parents=True, exist_ok=True)
    get_storage_dir().mkdir(parents=True, exist_ok=True)
    get_extracted_dir().mkdir(parents=True, exist_ok=True)
    get_daemon_log_dir().mkdir(parents=True, exist_ok=True)
