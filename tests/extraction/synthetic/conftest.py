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

from pathlib import Path

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip extraction_quality tests unless --run-extraction-quality is set."""
    if config.getoption("--run-extraction-quality"):
        return

    skip_marker = pytest.mark.skip(reason="need --run-extraction-quality option to run")
    for item in items:
        if "extraction_quality" in item.keywords:
            item.add_marker(skip_marker)


SYNTHETIC_DIR = Path(__file__).parent
SOURCES_DIR = SYNTHETIC_DIR / "sources"
FIXTURES_DIR = SYNTHETIC_DIR / "fixtures"
RESULTS_DIR = SYNTHETIC_DIR / "results"


@pytest.fixture(scope="session")
def quality_runner():
    """Session-scoped extraction quality runner."""
    from tests.extraction.synthetic.runner import ExtractionQualityRunner

    return ExtractionQualityRunner(
        sources_dir=SOURCES_DIR,
        fixtures_dir=FIXTURES_DIR,
        results_dir=RESULTS_DIR,
    )


@pytest.fixture(scope="session")
def quality_report(quality_runner):
    """Session-scoped quality report (runs full benchmark once)."""
    return quality_runner.run()
