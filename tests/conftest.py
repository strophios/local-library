"""Pytest configuration and shared fixtures."""

import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory for test isolation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def short_tmp_path() -> Generator[Path, None, None]:
    """Create a short-path temp directory suitable for AF_UNIX binding.

    Returns a Path in /tmp with prefix "ll-d-" to keep socket path under
    Darwin's ~104-char sun_path limit. Cleans up with ignore_errors=True
    for robustness.
    """
    path = Path(tempfile.mkdtemp(prefix="ll-d-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)
