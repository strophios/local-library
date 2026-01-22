"""Metadata processing handler for CSL-JSON validation and enrichment."""

# pattern: Imperative Shell
# This module performs I/O (file loading) and coordinates validation logic

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator
from unidecode import unidecode

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
# Note: Using Any for Draft7Validator since jsonschema lacks complete type stubs
_CSL_SCHEMA: dict[str, Any] | None = None
_CSL_VALIDATOR: Any = None


def _get_validator() -> Any:
    """Get or create the cached CSL-JSON validator."""
    global _CSL_SCHEMA, _CSL_VALIDATOR
    if _CSL_VALIDATOR is None:
        _CSL_SCHEMA = _load_item_schema()
        _CSL_VALIDATOR = Draft7Validator(_CSL_SCHEMA)
    return _CSL_VALIDATOR


# English stopwords for title word extraction
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "then",
        "else",
        "when",
        "at",
        "by",
        "for",
        "with",
        "about",
        "against",
        "between",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "to",
        "from",
        "up",
        "down",
        "in",
        "out",
        "on",
        "off",
        "over",
        "under",
        "again",
        "further",
        "once",
        "here",
        "there",
        "where",
        "why",
        "how",
        "all",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "can",
        "will",
        "just",
        "should",
        "now",
        "of",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "having",
        "do",
        "does",
        "did",
        "doing",
        "would",
        "could",
        "might",
        "must",
        "shall",
    }
)


def generate_citekey(csl_json: dict[str, Any]) -> str:
    """Generate a BetterBibTeX-style citekey from CSL-JSON metadata.

    Pattern: AuthorYearTitleword (e.g., "Smith2020Attention")

    Components:
    - Author: First author's family name, diacritics folded
    - Year: Four-digit year from issued.date-parts[0][0]
    - Titleword: First significant word (after stopword filtering)

    Fallback: "unknown-{hash[:8]}" if insufficient data.

    Args:
        csl_json: CSL-JSON metadata dictionary

    Returns:
        Generated citekey string
    """
    author_part = _extract_author_for_citekey(csl_json)
    year_part = _extract_year_for_citekey(csl_json)
    title_part = _extract_titleword_for_citekey(csl_json)

    # If we have at least author or title, build a key
    if author_part or title_part:
        parts = []
        if author_part:
            parts.append(author_part)
        if year_part:
            parts.append(year_part)
        if title_part:
            parts.append(title_part)
        return "".join(parts)

    # Fallback: hash-based key
    json_str = json.dumps(csl_json, sort_keys=True)
    hash_prefix = hashlib.sha256(json_str.encode()).hexdigest()[:8]
    return f"unknown-{hash_prefix}"


def _extract_author_for_citekey(csl_json: dict[str, Any]) -> str:
    """Extract first author's family name for citekey.

    Handles:
    - Standard author format: {"family": "Smith", "given": "John"}
    - Literal/organizational: {"literal": "World Health Organization"}
    - Non-ASCII names: folded via unidecode

    Returns:
        Cleaned author name or empty string if no author
    """
    # Check author field first, then editor as fallback
    contributors = csl_json.get("author") or csl_json.get("editor") or []

    if not contributors:
        return ""

    first_author = contributors[0]

    if isinstance(first_author, dict):
        # Prefer family name
        if "family" in first_author:
            name = first_author["family"]
        elif "literal" in first_author:
            # For organizations, use first word
            name = first_author["literal"].split()[0] if first_author["literal"] else ""
        else:
            return ""
    elif isinstance(first_author, str):
        name = first_author
    else:
        return ""

    # Clean the name: fold diacritics, remove non-alphanumeric
    name = unidecode(name)
    name = re.sub(r"[^a-zA-Z]", "", name)

    return name


def _extract_year_for_citekey(csl_json: dict[str, Any]) -> str:
    """Extract year from issued date for citekey.

    Returns:
        Four-digit year string or empty string if not available
    """
    issued = csl_json.get("issued")
    if not issued:
        return ""

    date_parts = issued.get("date-parts")
    if not date_parts or not date_parts[0]:
        return ""

    year = date_parts[0][0]
    if year is None:
        return ""

    return str(year)


def _extract_titleword_for_citekey(csl_json: dict[str, Any]) -> str:
    """Extract first significant word from title for citekey.

    Filters out stopwords and returns first remaining word.

    Returns:
        First significant title word or empty string
    """
    title = csl_json.get("title")
    if not title:
        return ""

    # Fold diacritics and extract words
    title = unidecode(title)
    words = re.findall(r"[a-zA-Z]+", title)

    for word in words:
        word_lower = word.lower()
        if word_lower not in _STOPWORDS and len(word) > 2:
            # Return with original capitalization
            return word.capitalize()

    # All words were stopwords or too short
    return ""


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
    VALID_TYPES = frozenset(
        {
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
        }
    )

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
                # Check specifically for 'id' field using regex to avoid false matches
                if re.search(r"'id'.*required", error.message):
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

        Delegates to module-level generate_citekey function.
        """
        return generate_citekey(csl_json)

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
            Formatted string like "Smith, J.; Jones, M.A."
            List contains individual formatted names.

        Author formatting rules:
        - Personal: "Family, G." where G. is abbreviated given names
        - Literal/org: Used as-is
        - Multiple authors: separated by "; "
        """
        # Check author field first, then editor as fallback
        contributors = csl_json.get("author") or csl_json.get("editor") or []

        if not contributors:
            return None, []

        author_list: list[str] = []
        for contributor in contributors:
            if not isinstance(contributor, dict):
                continue

            formatted = self._format_contributor(contributor)
            if formatted:
                author_list.append(formatted)

        authors_str = "; ".join(author_list) if author_list else None
        return authors_str, author_list

    def _format_contributor(self, contributor: dict[str, Any]) -> str | None:
        """Format a single contributor for display.

        Args:
            contributor: CSL-JSON contributor object

        Returns:
            Formatted name string or None
        """
        if "literal" in contributor:
            # Organizational/literal author - use as-is
            return contributor["literal"]

        if "family" not in contributor:
            return None

        family = contributor["family"]

        # Handle particles (von, de, etc.)
        if "non-dropping-particle" in contributor:
            family = f"{contributor['non-dropping-particle']} {family}"

        if "given" not in contributor:
            return family

        # Abbreviate given names to initials
        given = contributor["given"]
        initials = self._abbreviate_given_name(given)

        if initials:
            return f"{family}, {initials}"
        return family

    def _abbreviate_given_name(self, given: str) -> str:
        """Abbreviate given name to initials.

        "John" -> "J."
        "John Robert" -> "J.R."
        "J." -> "J."
        "J.R." -> "J.R."
        "Jean-Pierre" -> "J.-P."

        Args:
            given: Full given name(s)

        Returns:
            Abbreviated initials string
        """
        if not given:
            return ""

        parts: list[str] = []

        # Split on spaces first
        for part in given.split():
            if not part:
                continue

            # Handle hyphenated names (Jean-Pierre -> J.-P.)
            if "-" in part:
                hyphen_parts = []
                for hp in part.split("-"):
                    if hp:
                        # Already initial or needs abbreviation
                        if len(hp) == 1 or (len(hp) == 2 and hp.endswith(".")):
                            hyphen_parts.append(hp if hp.endswith(".") else f"{hp}.")
                        else:
                            hyphen_parts.append(f"{hp[0].upper()}.")
                if hyphen_parts:
                    parts.append("-".join(hyphen_parts))
            else:
                # Regular name part
                if len(part) == 1 or (len(part) == 2 and part.endswith(".")):
                    parts.append(part if part.endswith(".") else f"{part}.")
                else:
                    parts.append(f"{part[0].upper()}.")

        return "".join(parts)

    def _extract_issued_date(self, csl_json: dict[str, Any]) -> str | None:
        """Extract issued date for indexing.

        Returns ISO date format:
        - Full date: YYYY-MM-DD
        - Year-month: YYYY-MM
        - Year only: YYYY

        Args:
            csl_json: CSL-JSON metadata

        Returns:
            Formatted date string or None if not available
        """
        issued = csl_json.get("issued")
        if not issued:
            return None

        date_parts = issued.get("date-parts")
        if not date_parts or not date_parts[0]:
            return None

        parts = date_parts[0]

        # Handle None values in date parts
        if not parts or parts[0] is None:
            return None

        year = parts[0]

        if len(parts) >= 3 and parts[1] is not None and parts[2] is not None:
            # Full date: YYYY-MM-DD
            return f"{int(year):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
        elif len(parts) >= 2 and parts[1] is not None:
            # Year-month: YYYY-MM
            return f"{int(year):04d}-{int(parts[1]):02d}"
        else:
            # Year only
            return str(int(year))
