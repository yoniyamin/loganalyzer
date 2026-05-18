"""Extract End-of-Support bullets from Qlik Community release-note page text."""

from __future__ import annotations

import re
from typing import AbstractSet, Any, Dict, List, Optional

HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.+)$")


def _parse_heading(line: str) -> Optional[tuple[int, str]]:
    m = HEADING_RE.match(line.strip())
    if not m:
        return None
    return len(m.group(1)), m.group(2).strip()


def _title_starts_known_non_eol_topic(title: str) -> bool:
    tl = title.strip().lower()
    return bool(
        re.match(
            r"^(newly supported|resolved issues|what'?s new|known issues|downloads)\b",
            tl,
        )
    )


def _heading_opens_eol_capture(title: str) -> bool:
    t = title.strip().lower()
    if not t:
        return False
    if "end of life" in t and "support features" in t:
        return False
    if "end of support features" in t:
        return False
    if re.match(r"^end of support(\s|$)", t):
        return True
    if "no longer supported" in t or "has been discontinued" in t:
        return True
    if re.search(r"\bend of support\b", t):
        return True
    return False


def _plaintext_body(line: str) -> str:
    return re.sub(r"^#{1,6}\s+", "", line.strip()).strip()


def _plaintext_should_open_capture(stripped_line: str) -> bool:
    if stripped_line.startswith("-"):
        return False
    body = _plaintext_body(stripped_line)
    return bool(re.match(r"^end of support\s*$", body, re.IGNORECASE))


def _plaintext_should_stop_capture(stripped_line: str) -> bool:
    body = _plaintext_body(stripped_line).lower()
    return bool(
        re.match(
            r"^(newly supported|resolved issues|known issues|what'?s new|downloads|migration and upgrade)\b",
            body,
        )
    )


def _plaintext_skip_non_bullet_line(stripped: str) -> bool:
    """Skip short HTML sub-headings (e.g. 'Endpoint versions') inside the EOL block."""
    if stripped.startswith("-") or stripped.startswith("*"):
        return False
    if len(stripped) >= 72:
        return False
    if "." in stripped:
        return False
    low = stripped.lower()
    if any(
        k in low
        for k in (
            "discontinued",
            "deprecated",
            "support for",
            "minimum",
            "xml configuration",
        )
    ):
        return False
    return len(stripped.split()) <= 8


def _text_uses_markdown_headings(text: str) -> bool:
    return bool(re.search(r"(?m)^\s*#{1,6}\s+\S", text))


def _parse_eol_markdown(
    lines: list[str],
    task_endpoint_keys: Optional[AbstractSet[str]],
    max_entries: int,
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    capture = False
    start_level: Optional[int] = None
    section_count = 0

    def line_matches_tasks(line_lower: str) -> bool:
        if not task_endpoint_keys:
            return True
        for key in task_endpoint_keys:
            if key in line_lower:
                return True
            parts = key.split()
            if any(p in line_lower for p in parts if len(p) > 3):
                return True
        return False

    for ln in lines:
        hi = _parse_heading(ln)
        if hi:
            level, title = hi
            if capture and start_level is not None:
                if level < start_level or _title_starts_known_non_eol_topic(title):
                    capture = False
                    start_level = None
                    section_count = 0
            if (not capture) and _heading_opens_eol_capture(title):
                capture = True
                start_level = level
                section_count = 0
            continue

        if not capture:
            continue

        stripped = ln.strip()
        if len(stripped) <= 3:
            continue
        if section_count >= max_entries:
            capture = False
            start_level = None
            continue

        ll = stripped.lower()
        if task_endpoint_keys and not line_matches_tasks(ll):
            continue

        section_count += 1
        entries.append({
            "entry_type": "End of Support",
            "description": stripped,
            "component": "",
            "fix_id": "",
            "salesforce_case": "",
            "source": "chromadb",
        })

    return entries


def _parse_eol_plain(
    lines: list[str],
    task_endpoint_keys: Optional[AbstractSet[str]],
    max_entries: int,
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    capture = False
    section_count = 0

    def line_matches_tasks(line_lower: str) -> bool:
        if not task_endpoint_keys:
            return True
        for key in task_endpoint_keys:
            if key in line_lower:
                return True
            parts = key.split()
            if any(p in line_lower for p in parts if len(p) > 3):
                return True
        return False

    for ln in lines:
        stripped = ln.strip()

        if not capture:
            if _plaintext_should_open_capture(stripped):
                capture = True
                section_count = 0
            continue

        if _plaintext_should_stop_capture(stripped):
            capture = False
            section_count = 0
            continue

        if not stripped:
            continue

        if _plaintext_skip_non_bullet_line(stripped):
            continue

        if len(stripped) <= 3:
            continue

        if section_count >= max_entries:
            capture = False
            continue

        ll = stripped.lower()
        if task_endpoint_keys and not line_matches_tasks(ll):
            continue

        section_count += 1
        entries.append({
            "entry_type": "End of Support",
            "description": stripped,
            "component": "",
            "fix_id": "",
            "salesforce_case": "",
            "source": "chromadb",
        })

    return entries


def parse_eol_entries_from_release_note_text(
    text: str,
    *,
    task_endpoint_keys: Optional[AbstractSet[str]] = None,
    max_entries: int = 50,
) -> List[Dict[str, Any]]:
    """EOL bullets live under headings such as ``End of support``.

    Community HTML converted with BeautifulSoup strips ``#`` heading markers from
    plaintext; MCP-sourced snapshots may retain Markdown ``#``. Both are supported.
    """
    lines = text.split("\n")
    if _text_uses_markdown_headings(text):
        return _parse_eol_markdown(lines, task_endpoint_keys, max_entries)
    return _parse_eol_plain(lines, task_endpoint_keys, max_entries)
