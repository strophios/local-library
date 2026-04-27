"""Pytest configuration and shared fixtures."""

import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register custom command-line options.

    NOTE: --run-extraction-quality is registered in tests/extraction/conftest.py,
    not here. Don't re-register it — pytest will error on duplicate option.
    """
    parser.addoption(
        "--run-daemon-latency",
        action="store_true",
        default=False,
        help="Run the daemon warm-latency benchmark (slow; requires real corpus)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip daemon_latency tests unless --run-daemon-latency is set.

    The extraction_quality skip is handled in tests/extraction/conftest.py.
    """
    if not config.getoption("--run-daemon-latency"):
        skip_marker = pytest.mark.skip(reason="need --run-daemon-latency option to run")
        for item in items:
            if "daemon_latency" in item.keywords:
                item.add_marker(skip_marker)


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
