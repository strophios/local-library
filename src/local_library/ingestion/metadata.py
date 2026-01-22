"""Metadata processing handler for CSL-JSON validation and enrichment."""

# pattern: Functional Core

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft7Validator

from local_library.core.errors import ErrorCode, MetadataError
from local_library.core.models import MetadataResult


# Load schema once at module level
_SCHEMA_PATH = Path(__file__).parent / "schemas" / "csl-data.json"


def _load_full_schema() -> dict[str, Any]:
    """Load the full CSL-JSON schema including definitions."""
    with open(_SCHEMA_PATH) as f:
        return json.load(f)


def _load_item_schema() -> dict[str, Any]:
    """Load the CSL item schema for validation."""
    full_schema = _load_full_schema()
    # Extract the item schema from the collection schema
    # The collection schema defines an array of items; we validate individual items
    item_schema = full_schema.get("items", {})
    # Include definitions in item schema for reference resolution
    if "definitions" in full_schema:
        item_schema = item_schema.copy()
        item_schema["definitions"] = full_schema["definitions"]
    return item_schema


# Cache the validator for reuse
_CSL_SCHEMA: dict[str, Any] | None = None
_CSL_VALIDATOR: Draft7Validator | None = None


def _get_validator() -> Draft7Validator:
    """Get or create the cached CSL-JSON validator."""
    global _CSL_SCHEMA, _CSL_VALIDATOR
    if _CSL_VALIDATOR is None:
        _CSL_SCHEMA = _load_item_schema()
        _CSL_VALIDATOR = Draft7Validator(_CSL_SCHEMA)
    return _CSL_VALIDATOR


class MetadataHandler:
    """Validates CSL-JSON metadata and extracts indexed fields.

    Stateless handler that processes CSL-JSON input:
    1. Validates against CSL-JSON schema
    2. Generates citekey if not provided
    3. Extracts indexed fields (title, authors, date)

    The handler is source-agnostic - metadata can come from CLI input,
    PDF extraction, Zotero import, or CrossRef API.
    """

    # Valid CSL item types (subset - full list in schema)
    VALID_TYPES = frozenset({
        "article",
        "article-journal",
        "article-magazine",
        "article-newspaper",
        "bill",
        "book",
        "broadcast",
        "chapter",
        "classic",
        "collection",
        "dataset",
        "document",
        "entry",
        "entry-dictionary",
        "entry-encyclopedia",
        "event",
        "figure",
        "graphic",
        "hearing",
        "interview",
        "legal_case",
        "legislation",
        "manuscript",
        "map",
        "motion_picture",
        "musical_score",
        "pamphlet",
        "paper-conference",
        "patent",
        "performance",
        "periodical",
        "personal_communication",
        "post",
        "post-weblog",
        "regulation",
        "report",
        "review",
        "review-book",
        "software",
        "song",
        "speech",
        "standard",
        "thesis",
        "treaty",
        "webpage",
    })

    def __init__(self) -> None:
        """Initialize the handler with cached validator."""
        self._validator = _get_validator()

    def validate(self, csl_json: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate CSL-JSON against schema.

        Returns:
            Tuple of (is_valid, list of issues).
            Issues may be errors (validation fails) or warnings (validation passes
            but data is incomplete).

        Validation strategy (lenient):
        - Fatal: missing/invalid 'type' field
        - Fatal: wrong field types (string where object expected, etc.)
        - Warning: missing optional fields including 'id', abstract, DOI, etc.
        """
        issues: list[str] = []

        # Check 'type' field explicitly (fatal if missing or invalid)
        if "type" not in csl_json:
            return False, ["missing required field: type"]

        item_type = csl_json["type"]
        if not isinstance(item_type, str):
            return False, [f"field 'type' must be string, got {type(item_type).__name__}"]

        if item_type not in self.VALID_TYPES:
            return False, [f"invalid item type: {item_type}"]

        # Run JSON Schema validation for structural issues
        errors = list(self._validator.iter_errors(csl_json))

        # Classify errors as fatal or warnings
        fatal_errors: list[str] = []
        for error in errors:
            # Type errors are fatal
            if error.validator == "type":
                path = ".".join(str(p) for p in error.path) if error.path else "root"
                fatal_errors.append(f"type error at {path}: {error.message}")
            # Required field errors: 'id' is lenient (warning), others fatal
            elif error.validator == "required":
                # 'id' can be generated later; other required fields are fatal
                if "'id'" in error.message or "id" in error.message:
                    issues.append(f"warning: {error.message}")
                else:
                    fatal_errors.append(f"missing required field: {error.message}")
            # Additional properties errors are warnings (lenient)
            elif error.validator == "additionalProperties":
                issues.append(f"warning: {error.message}")
            else:
                # Other schema violations are fatal
                path = ".".join(str(p) for p in error.path) if error.path else "root"
                fatal_errors.append(f"schema error at {path}: {error.message}")

        if fatal_errors:
            return False, fatal_errors

        # Check for recommended but missing fields (warnings only)
        if "title" not in csl_json:
            issues.append("warning: missing recommended field 'title'")
        if "author" not in csl_json and "editor" not in csl_json:
            issues.append("warning: missing author or editor")
        if "issued" not in csl_json:
            issues.append("warning: missing publication date (issued)")

        return True, issues

    def process(self, csl_json: dict[str, Any], citekey: str | None = None) -> MetadataResult:
        """Process CSL-JSON metadata.

        Args:
            csl_json: CSL-JSON metadata dictionary
            citekey: Optional override for citation key. If not provided,
                     will be generated from metadata.

        Returns:
            MetadataResult with validated metadata and extracted fields

        Raises:
            MetadataError: If validation fails
        """
        # Validate
        is_valid, issues = self.validate(csl_json)
        if not is_valid:
            raise MetadataError(
                f"invalid CSL-JSON: {'; '.join(issues)}",
                ErrorCode.METADATA_INVALID_SCHEMA,
                details={"issues": issues},
            )

        # Separate warnings from errors
        warnings = [i for i in issues if i.startswith("warning:")]

        # Generate or validate citekey
        if citekey is None:
            # Citekey generation will be implemented in Phase 3
            # For now, use a placeholder
            citekey = self._generate_citekey(csl_json)
        else:
            # Validate provided citekey format
            if not self._is_valid_citekey(citekey):
                raise MetadataError(
                    f"invalid citekey format: {citekey}",
                    ErrorCode.METADATA_CITEKEY_INVALID,
                    details={"citekey": citekey},
                )

        # Extract indexed fields (will be fully implemented in Phase 4)
        title = self._extract_title(csl_json)
        authors, author_list = self._extract_authors(csl_json)
        issued_date = self._extract_issued_date(csl_json)

        return MetadataResult.create(
            csl_json=csl_json,
            citekey=citekey,
            title=title,
            authors=authors,
            issued_date=issued_date,
            validation_warnings=warnings,
            author_list=author_list,
        )

    def _generate_citekey(self, csl_json: dict[str, Any]) -> str:
        """Generate a citekey from metadata.

        Full implementation in Phase 3. This is a placeholder.
        """
        # Placeholder: will be replaced in Phase 3
        json_str = json.dumps(csl_json, sort_keys=True)
        hash_prefix = sha256(json_str.encode()).hexdigest()[:8]
        return f"unknown-{hash_prefix}"

    def _is_valid_citekey(self, citekey: str) -> bool:
        """Check if a citekey has valid format.

        Valid citekeys:
        - Non-empty
        - No whitespace
        - Alphanumeric with optional hyphens and underscores
        """
        if not citekey or not citekey.strip():
            return False
        # Allow alphanumeric, hyphens, underscores
        return bool(re.match(r"^[\w-]+$", citekey))

    def _extract_title(self, csl_json: dict[str, Any]) -> str | None:
        """Extract title for indexing."""
        return csl_json.get("title")

    def _extract_authors(self, csl_json: dict[str, Any]) -> tuple[str | None, list[str]]:
        """Extract authors for indexing.

        Returns:
            Tuple of (formatted_string, list_of_names)
            Formatted string like "Smith, J.; Jones, M."
        """
        # Placeholder: full implementation in Phase 4
        authors = csl_json.get("author", [])
        if not authors:
            return None, []

        author_list: list[str] = []
        for author in authors:
            if isinstance(author, dict):
                if "literal" in author:
                    author_list.append(author["literal"])
                elif "family" in author:
                    name = author["family"]
                    if "given" in author:
                        # Abbreviate given name
                        given = author["given"]
                        initials = "".join(g[0] + "." for g in given.split() if g)
                        name = f"{name}, {initials}"
                    author_list.append(name)

        authors_str = "; ".join(author_list) if author_list else None
        return authors_str, author_list

    def _extract_issued_date(self, csl_json: dict[str, Any]) -> str | None:
        """Extract issued date for indexing.

        Returns ISO date (YYYY-MM-DD) or year only (YYYY).
        """
        issued = csl_json.get("issued")
        if not issued:
            return None

        date_parts = issued.get("date-parts")
        if not date_parts or not date_parts[0]:
            return None

        parts = date_parts[0]
        if len(parts) >= 3:
            return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"
        elif len(parts) >= 2:
            return f"{parts[0]:04d}-{parts[1]:02d}"
        elif len(parts) >= 1:
            return str(parts[0])

        return None
