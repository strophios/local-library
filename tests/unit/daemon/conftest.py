"""Fixtures for daemon tests.

Provides short_tmp_path fixture for tests that bind Unix-domain sockets.
Darwin's AF_UNIX sun_path limit (~104 chars) constrains the path length;
pytest's default tmp_path with nested temp directories can exceed this.
The short_tmp_path fixture uses /tmp/ll-d-<random> as a workaround.
"""

import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest


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
