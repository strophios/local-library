"""Update command - edit document metadata."""

# pattern: Mixed (Functional Core utilities + Imperative Shell update command)

import json
import os
import subprocess
import tempfile
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.prompt import Confirm

from local_library.cli.open import find_editor
from local_library.cli.utils import resolve_identifier
from local_library.core import Library, LookupError
from local_library.core.models import Document, DocumentStatus
from local_library.core.storage import get_connection, get_unique_citekey
from local_library.ingestion.metadata import MetadataHandler, generate_citekey

console = Console()
err_console = Console(stderr=True)


def validate_edited_json(
    edited: dict[str, Any],
    current_citekey: str | None,
    all_citekeys: list[str],
) -> list[str]:
    """Validate edited JSON structure.

    Checks:
    - status is valid DocumentStatus value
    - citekey is unique (or unchanged from current)
    - csl_json passes schema validation

    Args:
        edited: Parsed JSON from editor
        current_citekey: Document's current citekey (for uniqueness check)
        all_citekeys: All citekeys in the library

    Returns:
        List of error messages (empty if valid)
    """
    errors: list[str] = []

    # Validate status
    if "status" not in edited:
        errors.append("missing required field: status")
    else:
        try:
            DocumentStatus(edited["status"])
        except ValueError:
            valid = ", ".join(s.value for s in DocumentStatus)
            errors.append(f"invalid status '{edited['status']}' (valid: {valid})")

    # Validate citekey uniqueness
    new_citekey = edited.get("citekey")
    if new_citekey is not None and new_citekey != current_citekey:
        if new_citekey in all_citekeys:
            errors.append(f"citekey '{new_citekey}' already exists in library")

    # Validate CSL-JSON if present
    csl_json = edited.get("csl_json")
    if csl_json is not None:
        handler = MetadataHandler()
        is_valid, issues = handler.validate(csl_json)
        if not is_valid:
            for issue in issues:
                if not issue.startswith("warning:"):
                    errors.append(f"CSL-JSON: {issue}")

    return errors


def insert_errors_as_comments(json_content: str, errors: list[str]) -> str:
    """Insert validation errors as comments at top of JSON.

    Note: JSON doesn't support comments, but editors will display them.
    The parse step will need to strip these comments before parsing.

    Args:
        json_content: Original JSON string
        errors: List of error messages

    Returns:
        JSON with error comments prepended
    """
    comment_lines = ["// ERRORS (fix these issues and save again):"]
    for error in errors:
        comment_lines.append(f"//   - {error}")
    comment_lines.append("//")
    comment_lines.append("")

    return "\n".join(comment_lines) + json_content


def parse_edited_json(content: str) -> dict[str, Any] | None:
    """Parse JSON content, stripping any comment lines.

    Args:
        content: File content (may include // comments)

    Returns:
        Parsed JSON dict, or None if file is empty/aborted

    Raises:
        ValueError: If JSON parsing fails
    """
    # Strip comment lines (lines starting with //)
    lines = content.split("\n")
    json_lines = [line for line in lines if not line.strip().startswith("//")]
    json_content = "\n".join(json_lines).strip()

    # Empty content = abort
    if not json_content:
        return None

    try:
        return json.loads(json_content)
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e


def _check_citekey_regeneration(
    original_csl: dict[str, Any] | None,
    new_csl: dict[str, Any] | None,
    original_citekey: str | None,
    new_citekey: str | None,
) -> bool:
    """Check if citekey should be regenerated based on metadata changes.

    Args:
        original_csl: Original CSL-JSON
        new_csl: New CSL-JSON after edit
        original_citekey: Original citekey
        new_citekey: New citekey after edit

    Returns:
        True if user should be prompted to regenerate citekey
    """
    # Only prompt if citekey wasn't changed manually
    if new_citekey != original_citekey:
        return False

    # Only prompt if CSL-JSON exists in both
    if not original_csl or not new_csl:
        return False

    # Check if relevant fields changed
    def get_citekey_fields(csl: dict[str, Any]) -> tuple:
        return (
            csl.get("title"),
            csl.get("author"),
            csl.get("issued"),
        )

    return get_citekey_fields(original_csl) != get_citekey_fields(new_csl)


def build_editable_json(doc: Document) -> str:
    """Build JSON structure for editing in $EDITOR.

    The structure includes:
    - _readonly: Informational fields (id, paths, timestamps)
    - status: Editable document status
    - citekey: Editable citation key
    - csl_json: Editable bibliographic metadata

    Args:
        doc: Document to build JSON for

    Returns:
        JSON string formatted for editing
    """
    structure: dict[str, Any] = {
        "_readonly": {
            "id": str(doc.id),
            "original_path": doc.original_path,
            "storage_path": doc.storage_path,
            "extracted_path": doc.extracted_path,
            "content_hash": doc.content_hash,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        },
        "status": doc.status.value,
        "citekey": doc.citekey,
        "csl_json": doc.csl_json,
    }

    return json.dumps(structure, indent=2, ensure_ascii=False)


def update(
    identifier: Annotated[str, typer.Argument(help="Document ID (UUID or @citekey)")],
) -> None:
    """Edit document metadata in your editor.

    Opens a JSON file containing the document's status, citekey, and
    CSL-JSON metadata. Edit the fields and save to apply changes.

    Supports both UUID (full or partial) and @citekey identifiers.

    To abort, save an empty file or delete all content.
    """
    # Find editor first
    editor = find_editor()
    if not editor:
        err_console.print("[red]error:[/red] no editor found")
        err_console.print("[dim]Install nvim/vim or set $EDITOR environment variable.[/dim]")
        raise typer.Exit(code=1) from None

    try:
        with Library() as lib:
            doc = resolve_identifier(identifier, lib)
            all_citekeys = lib.get_all_citekeys()

            # Build initial JSON
            json_content = build_editable_json(doc)

            # Edit loop - use try/finally to ensure temp file cleanup
            temp_path = None
            try:
                while True:
                    # Write to temp file and open editor
                    with tempfile.NamedTemporaryFile(
                        mode="w",
                        suffix=".json",
                        delete=False,
                    ) as f:
                        f.write(json_content)
                        temp_path = f.name

                    subprocess.run([editor, temp_path], check=False)

                    # Read edited content
                    with open(temp_path) as f:
                        edited_content = f.read()

                    # Parse
                    try:
                        parsed = parse_edited_json(edited_content)
                    except ValueError as e:
                        # JSON parse error - re-edit with error message
                        json_content = insert_errors_as_comments(edited_content, [str(e)])
                        continue

                    # Check for abort
                    if parsed is None:
                        console.print("[yellow]Update aborted.[/yellow]")
                        return

                    # Validate
                    errors = validate_edited_json(parsed, doc.citekey, all_citekeys)
                    if errors:
                        # Re-edit with errors
                        json_content = insert_errors_as_comments(edited_content, errors)
                        continue

                    # Valid - break out of loop
                    break
            finally:
                # Clean up temp file
                if temp_path and os.path.exists(temp_path):
                    os.unlink(temp_path)

            # Check if citekey should be regenerated
            new_citekey = parsed.get("citekey")
            new_csl = parsed.get("csl_json")
            if _check_citekey_regeneration(doc.csl_json, new_csl, doc.citekey, new_citekey):
                if Confirm.ask(
                    "Author/title/year changed. Regenerate citekey?",
                    default=False,
                ):
                    new_citekey = generate_citekey(new_csl)
                    # Ensure uniqueness
                    if new_citekey in all_citekeys and new_citekey != doc.citekey:
                        conn = get_connection()
                        new_citekey = get_unique_citekey(conn, new_citekey)
                    console.print(f"[dim]New citekey: {new_citekey}[/dim]")

            # Apply updates
            lib.update_metadata(
                doc.id,
                status=DocumentStatus(parsed["status"]),
                citekey=new_citekey,
                csl_json=new_csl,
            )

            console.print(f"[green]Updated document {doc.id}[/green]")

    except LookupError as e:
        err_console.print(f"[red]error:[/red] {e.message}")
        if "suggestions" in e.details and e.details["suggestions"]:
            err_console.print("[dim]Did you mean:[/dim]")
            for suggestion in e.details["suggestions"]:
                err_console.print(f"  [cyan]@{suggestion}[/cyan]")
        raise typer.Exit(code=1) from None
