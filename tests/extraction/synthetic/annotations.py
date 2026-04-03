# pattern: Functional Core
"""Parse and strip feature annotations from synthetic source markdown.

Annotations are HTML comments marking feature regions for quality measurement:
    <!-- feature: heading-h2 id:section-intro -->
    ## Introduction
    <!-- /feature -->

This module provides:
- parse_annotations(): Extract annotated regions with metadata
- strip_annotations(): Remove annotation markers, preserving content
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_OPEN_TAG = re.compile(
    r"^<!-- feature: (?P<feature_type>\S+) id:(?P<region_id>\S+) -->$"
)
_CLOSE_TAG = re.compile(r"^<!-- /feature -->$")


@dataclass(frozen=True)
class AnnotatedRegion:
    """A region of source markdown annotated with a feature type."""

    feature_type: str
    region_id: str
    content: str


def parse_annotations(text: str) -> list[AnnotatedRegion]:
    """Extract annotated regions from source markdown.

    Args:
        text: Source markdown containing feature annotation comments.

    Returns:
        List of AnnotatedRegion in document order.
    """
    regions: list[AnnotatedRegion] = []
    lines = text.split("\n")

    current_type: str | None = None
    current_id: str | None = None
    content_lines: list[str] = []

    for line in lines:
        if current_type is None:
            match = _OPEN_TAG.match(line.strip())
            if match:
                current_type = match.group("feature_type")
                current_id = match.group("region_id")
                content_lines = []
        else:
            if _CLOSE_TAG.match(line.strip()):
                content = "\n".join(content_lines).strip()
                regions.append(
                    AnnotatedRegion(
                        feature_type=current_type,
                        region_id=current_id,  # type: ignore[arg-type]
                        content=content,
                    )
                )
                current_type = None
                current_id = None
                content_lines = []
            else:
                content_lines.append(line)

    return regions


def strip_annotations(text: str) -> str:
    """Remove annotation markers from source markdown, preserving content.

    Strips only feature annotation tags. Other HTML comments are preserved.

    Args:
        text: Source markdown with annotation comments.

    Returns:
        Markdown with annotation tags removed, content intact.
    """
    lines = text.split("\n")
    output: list[str] = []

    for line in lines:
        stripped = line.strip()
        if _OPEN_TAG.match(stripped) or _CLOSE_TAG.match(stripped):
            continue
        output.append(line)

    return "\n".join(output)
