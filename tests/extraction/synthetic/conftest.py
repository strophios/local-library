# pattern: Imperative Shell
"""Pytest configuration for synthetic extraction quality tests.

Registers the extraction_quality marker and provides --run-extraction-quality
flag to opt into these slow tests.

NOTE: This conftest sits under tests/extraction/, so the parent conftest.py
also applies. The parent's pytest_collection_modifyitems skips tests marked
with "extraction" (exact key match) — our "extraction_quality" marker is a
different key and is NOT affected. Verified via --collect-only.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add --run-extraction-quality flag."""
    parser.addoption(
        "--run-extraction-quality",
        action="store_true",
        default=False,
        help="Run synthetic extraction quality benchmark tests",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip extraction_quality tests unless --run-extraction-quality is set."""
    if config.getoption("--run-extraction-quality"):
        return

    skip_marker = pytest.mark.skip(reason="need --run-extraction-quality option to run")
    for item in items:
        if "extraction_quality" in item.keywords:
            item.add_marker(skip_marker)
