"""CLI entry point with Typer app and shared context."""

# pattern: Imperative Shell

import typer

from local_library.cli import add as add_cmd
from local_library.cli import delete as delete_cmd
from local_library.cli import list as list_cmd
from local_library.cli import show as show_cmd

# Create Typer app
app = typer.Typer(
    name="local-library",
    help="Personal knowledge management for local documents.",
    add_completion=False,
)

# Register subcommands
app.command(name="add")(add_cmd.add)
app.command(name="list")(list_cmd.list_docs)
app.command(name="show")(show_cmd.show)
app.command(name="delete")(delete_cmd.delete)


def main() -> None:
    """CLI entry point."""
    app()


if __name__ == "__main__":
    main()
