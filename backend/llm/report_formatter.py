"""
Normalize LLM report Markdown for display and grading.

Models often emit numbered lists (1. **Section**) because the system contract
described sections that way. This promotes them to ## headers and fixes
common truncation artifacts.
"""

from __future__ import annotations

import re
from typing import List, Tuple

# (line pattern, canonical ## header)
_SECTION_PROMOTIONS: List[Tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"^(?:#+\s*|\d+\.\s+)(?:\*\*)?\s*Executive Summary(?:\s*&\s*Health)?(?:\*\*)?"
            r"(?:\s*[—\-:].*)?$",
            re.IGNORECASE,
        ),
        "## Executive Summary & Health",
    ),
    (
        re.compile(
            r"^(?:#+\s*|\d+\.\s+)(?:\*\*)?\s*Key Findings(?:\*\*)?(?:\s*[—\-:].*)?$",
            re.IGNORECASE,
        ),
        "## Key Findings",
    ),
    (
        re.compile(
            r"^(?:#+\s*|\d+\.\s+)(?:\*\*)?\s*Performance(?:\s*&\s*Full Load Analysis)?(?:\*\*)?"
            r"(?:\s*[—\-:].*)?$",
            re.IGNORECASE,
        ),
        "## Performance & Full Load Analysis",
    ),
    (
        re.compile(
            r"^(?:#+\s*|\d+\.\s+)(?:\*\*)?\s*Issues(?:\s*&\s*Recommendations)?(?:\*\*)?"
            r"(?:\s*[—\-:].*)?$",
            re.IGNORECASE,
        ),
        "## Issues & Recommendations",
    ),
    (
        re.compile(
            r"^(?:#+\s*|\d+\.\s+)(?:\*\*)?\s*Error(?:\s*&\s*Component Mapping)?(?:\*\*)?"
            r"(?:\s*[—\-:].*)?$",
            re.IGNORECASE,
        ),
        "## Error & Component Mapping",
    ),
    (
        re.compile(
            r"^(?:#+\s*|\d+\.\s+)(?:\*\*)?\s*Risk Assessment(?:\*\*)?(?:\s*[—\-:].*)?$",
            re.IGNORECASE,
        ),
        "## Risk Assessment",
    ),
]

_NUMBERED_SECTION_RE = re.compile(
    r"^\d+\.\s+\*\*(Executive Summary|Key Findings|Performance|Issues|Error|Risk Assessment)",
    re.IGNORECASE | re.MULTILINE,
)

_TRAILING_SLASH_RE = re.compile(r"/{2,}\s*$")


def uses_numbered_section_headers(content: str) -> bool:
    """True when major sections use ordered-list numbering instead of ## headers."""
    return bool(_NUMBERED_SECTION_RE.search(content or ""))


def normalize_report_markdown(content: str) -> Tuple[str, List[str]]:
    """
    Promote numbered/bold section lines to ## headers; strip truncation junk.

    Returns (normalized_text, list of fix descriptions).
    """
    if not (content or "").strip():
        return content or "", []

    fixes: List[str] = []
    lines = content.replace("\r\n", "\n").split("\n")
    out: List[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue

        promoted_header = None
        for pattern, header in _SECTION_PROMOTIONS:
            if pattern.match(stripped):
                promoted_header = header
                break

        if promoted_header:
            if stripped != promoted_header:
                fixes.append(f"Promoted section line to `{promoted_header}`")
            out.append(promoted_header)
        else:
            out.append(line)

    text = "\n".join(out)
    cleaned_lines: List[str] = []
    slash_fixed = False
    for line in text.split("\n"):
        new_line = re.sub(r"(?<=\S)/{2,}\s*$", "", line)
        if new_line != line:
            slash_fixed = True
        cleaned_lines.append(new_line)
    text = "\n".join(cleaned_lines).rstrip()
    if slash_fixed:
        fixes.append("Removed trailing slash truncation artifact")

    return text, fixes


def display_report_content(content: str) -> str:
    """Normalize stored report markdown for API responses and UI rendering."""
    normalized, _ = normalize_report_markdown(content or "")
    return normalized
