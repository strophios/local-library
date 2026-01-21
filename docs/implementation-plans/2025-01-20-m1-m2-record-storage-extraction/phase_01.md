# M1+M2 Record Storage & Extraction - Implementation Plan

**Goal:** Establish project structure, dependencies, and configuration for the PDF RAG pipeline

**Architecture:** Module pattern with src/local_library/ containing core/, ingestion/, and cli/ subpackages. Uses platformdirs for XDG-compliant storage paths, Typer for CLI, and marker-pdf for extraction.

**Tech Stack:** Python 3.10+, uv (package management), ruff (linting), typer, rich, platformdirs, marker-pdf, pytest

**Scope:** 8 phases from original design (phases 1-8, complete implementation)

**Codebase verified:** 2025-01-20

---

## Phase 1: Project Scaffolding

<!-- START_TASK_1 -->
### Task 1: Create pyproject.toml with dependencies

**Files:**
- Create: `pyproject.toml`

**Step 1: Create the project configuration file**

```toml
[project]
name = "local-library"
version = "0.1.0"
description = "Personal knowledge management system with PDF ingestion and RAG capabilities"
readme = "README.md"
requires-python = ">=3.10"
license = {text = "MIT"}
authors = [
    {name = "strophios"}
]
dependencies = [
    "typer>=0.21.0",
    "rich>=13.0.0",
    "platformdirs>=4.0.0",
    "marker-pdf>=1.10.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.8.0",
]

[project.scripts]
local-library = "local_library.cli.main:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/local_library"]

[tool.ruff]
src = ["src"]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # pyflakes
    "I",      # isort
    "B",      # flake8-bugbear
    "C4",     # flake8-comprehensions
    "UP",     # pyupgrade
]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
markers = [
    "unit: Unit tests (substeps)",
    "stage: Full pipeline stage tests",
    "contract: Transition/contract tests",
    "integration: End-to-end integration tests",
]
```

**Step 2: Verify configuration is valid**

Run: `cd /Users/strophios/development/local-library/.worktrees/m1-m2-record-storage-extraction && cat pyproject.toml`

Expected: File contents displayed without errors

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add pyproject.toml with dependencies and tooling config

- Core deps: typer, rich, platformdirs, marker-pdf
- Dev deps: pytest, pytest-cov, ruff
- Pytest markers for four-level test strategy
- Ruff configuration for code quality

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_1 -->

---

<!-- START_TASK_2 -->
### Task 2: Create package directory structure

**Files:**
- Create: `src/local_library/__init__.py`
- Create: `src/local_library/core/__init__.py`
- Create: `src/local_library/ingestion/__init__.py`
- Create: `src/local_library/cli/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Create the directory structure and init files**

`src/local_library/__init__.py`:
```python
"""Local Library - Personal knowledge management with PDF ingestion and RAG."""

__version__ = "0.1.0"
```

`src/local_library/core/__init__.py`:
```python
"""Core module - models, storage, orchestration."""
```

`src/local_library/ingestion/__init__.py`:
```python
"""Ingestion module - content acquisition and extraction."""
```

`src/local_library/cli/__init__.py`:
```python
"""CLI module - command-line interface."""
```

`tests/__init__.py`:
```python
"""Test suite for local-library."""
```

`tests/conftest.py`:
```python
"""Pytest configuration and shared fixtures."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir() -> Path:
    """Provide a temporary directory for test isolation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
```

**Step 2: Verify directory structure**

Run: `find src tests -type f -name "*.py" | sort`

Expected:
```
src/local_library/__init__.py
src/local_library/cli/__init__.py
src/local_library/core/__init__.py
src/local_library/ingestion/__init__.py
tests/__init__.py
tests/conftest.py
```

**Step 3: Commit**

```bash
git add src/ tests/
git commit -m "chore: create package directory structure

- src/local_library/ with core/, ingestion/, cli/ subpackages
- tests/ with conftest.py and temp_dir fixture

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_2 -->

---

<!-- START_TASK_3 -->
### Task 3: Create config module with platformdirs paths

**Files:**
- Create: `src/local_library/config.py`

**Step 1: Create the configuration module**

```python
"""Path configuration using platformdirs for XDG-compliant storage."""

# pattern: Functional Core

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
```

**Step 2: Verify module is importable**

Run: `cd /Users/strophios/development/local-library/.worktrees/m1-m2-record-storage-extraction && uv run python -c "from local_library.config import get_data_dir; print(get_data_dir())"`

Expected: A path like `/Users/strophios/Library/Application Support/local-library` (macOS) printed without errors

**Step 3: Commit**

```bash
git add src/local_library/config.py
git commit -m "feat: add config module with platformdirs paths

- XDG-compliant user data directory
- Paths for database, storage, and extracted files
- ensure_directories() for initialization

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_3 -->

---

<!-- START_TASK_4 -->
### Task 4: Install dependencies and verify environment

**Files:**
- None (operational verification)

**Step 1: Sync dependencies with uv**

Run: `cd /Users/strophios/development/local-library/.worktrees/m1-m2-record-storage-extraction && uv sync`

Expected: Dependencies installed successfully, including typer, rich, platformdirs, marker-pdf, pytest

**Step 2: Verify package is importable**

Run: `uv run python -c "import local_library; print(local_library.__version__)"`

Expected: `0.1.0`

**Step 3: Verify key dependencies are available**

Run: `uv run python -c "import typer; import rich; import platformdirs; print('All dependencies available')"`

Expected: `All dependencies available`

**Step 4: Commit lockfile**

```bash
git add uv.lock
git commit -m "chore: add uv.lock with resolved dependencies

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_4 -->

---

<!-- START_TASK_5 -->
### Task 5: Create minimal CLI entry point

**Files:**
- Create: `src/local_library/cli/main.py`

**Step 1: Create the CLI app with placeholder commands**

```python
"""CLI entry point for local-library."""

# pattern: Imperative Shell

import typer
from rich.console import Console

app = typer.Typer(
    name="local-library",
    help="Personal knowledge management with PDF ingestion and RAG.",
    no_args_is_help=True,
)

console = Console()


@app.command()
def version() -> None:
    """Display the current version."""
    from local_library import __version__

    console.print(f"local-library version {__version__}")


@app.callback()
def main() -> None:
    """Local Library - Personal knowledge management system."""
    pass


if __name__ == "__main__":
    app()
```

**Step 2: Verify CLI runs**

Run: `uv run local-library --help`

Expected: Help text showing available commands including `version`

**Step 3: Verify version command**

Run: `uv run local-library version`

Expected: `local-library version 0.1.0`

**Step 4: Commit**

```bash
git add src/local_library/cli/main.py
git commit -m "feat: add minimal CLI entry point with version command

- Typer app with Rich console integration
- Entry point configured in pyproject.toml

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

<!-- END_TASK_5 -->

---

<!-- START_TASK_6 -->
### Task 6: Verify complete scaffolding

**Files:**
- None (verification only)

**Step 1: Run ruff to verify code quality**

Run: `uv run ruff check src/ tests/`

Expected: No errors (or only fixable warnings)

**Step 2: Run pytest to verify test infrastructure**

Run: `uv run pytest --collect-only`

Expected: Test collection succeeds (0 tests collected is fine for scaffolding phase)

**Step 3: Verify final project structure**

Run: `find src tests -type f -name "*.py" | sort && echo "---" && ls -la`

Expected:
```
src/local_library/__init__.py
src/local_library/cli/__init__.py
src/local_library/cli/main.py
src/local_library/config.py
src/local_library/core/__init__.py
src/local_library/ingestion/__init__.py
tests/__init__.py
tests/conftest.py
---
[directory listing including pyproject.toml, uv.lock, src/, tests/]
```

<!-- END_TASK_6 -->

---

**Phase 1 Definition of Done:**
- `uv sync` succeeds
- `uv run python -c "import local_library"` works
- CLI entry point functional (`uv run local-library --help`)
