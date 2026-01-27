"""Open command - open document files for viewing."""

# pattern: Imperative Shell

import os
import shutil
import subprocess
from typing import Annotated

import typer
from rich.console import Console

from local_library.cli.utils import resolve_identifier
from local_library.core import Library, LookupError

console = Console()
err_console = Console(stderr=True)


def find_editor() -> str | None:
    """Find an editor to use for markdown files.

    Preference order: nvim > vim > $EDITOR

    Returns:
        Path to editor, or None if not found
    """
    # Try nvim first
    nvim_path = shutil.which("nvim")
    if nvim_path:
        return nvim_path

    # Try vim
    vim_path = shutil.which("vim")
    if vim_path:
        return vim_path

    # Fall back to $EDITOR
    return os.environ.get("EDITOR")
