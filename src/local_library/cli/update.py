"""Update command - edit document metadata."""

# pattern: Imperative Shell

import json
from typing import Any

from local_library.core.models import Document


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
