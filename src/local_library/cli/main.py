"""CLI entry point with Typer app and shared context."""

# pattern: Imperative Shell

import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from local_library.core import Library

# Create Typer app
app = typer.Typer(
    name="local-library",
    help="Personal knowledge management for local documents.",
    add_completion=False,
)

# Rich consoles for output
console = Console()
err_console = Console(stderr=True)


def get_library() -> Library:
    """Get a Library instance with default paths."""
    return Library()


def error(message: str, code: int = 1) -> None:
    """Print error message to stderr and exit."""
    err_console.print(f"[red]error:[/red] {message}")
    raise typer.Exit(code=code)


# Import and register subcommands
from local_library.cli import add as add_cmd
from local_library.cli import delete as delete_cmd
from local_library.cli import list as list_cmd
from local_library.cli import show as show_cmd

app.command(name="add")(add_cmd.add)
app.command(name="list")(list_cmd.list_docs)
app.command(name="show")(show_cmd.show)
app.command(name="delete")(delete_cmd.delete)


def main() -> None:
    """CLI entry point."""
    app()


if __name__ == "__main__":
    main()
