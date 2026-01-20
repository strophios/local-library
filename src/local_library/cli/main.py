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
