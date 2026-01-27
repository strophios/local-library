"""Update command - edit document metadata."""

# pattern: Imperative Shell

import json
from typing import Any

from local_library.core.models import Document, DocumentStatus
from local_library.ingestion.metadata import MetadataHandler


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
