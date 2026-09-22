"""
Phase 4 — Evidence payload format variants for A/B testing.

Variants (no default winner assumed):
  - markdown (A): Markdown sections, fenced LINE blocks
  - json_markdown (B): JSON scalar facts + Markdown tables + XML evidence tags
  - xml (C): XML-heavy report_context wrapper
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape as xml_escape

from backend.llm.evidence_compiler import BudgetedSection

VALID_PAYLOAD_FORMATS = frozenset({"markdown", "json_markdown", "xml"})

_FORMAT_ALIASES = {
    "": "markdown",
    "a": "markdown",
    "md": "markdown",
    "b": "json_markdown",
    "json": "json_markdown",
    "hybrid": "json_markdown",
    "c": "xml",
}

_FENCED_BLOCK_RE = re.compile(
    r"\*\*(?:Pattern|Warning|Excerpt|Note)\s+\d+:\*\*\s*\n```\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)
_LINE_ANCHOR_RE = re.compile(r"\bLINE\s+(\d+)\b", re.IGNORECASE)


def normalize_payload_format(name: Optional[str]) -> str:
    """Return canonical format id; unknown values fall back to markdown."""
    if not name:
        return "markdown"
    key = name.strip().lower()
    canonical = _FORMAT_ALIASES.get(key, key)
    if canonical not in VALID_PAYLOAD_FORMATS:
        return "markdown"
    return canonical


def build_scalar_facts_dict(
    summary_data: Optional[Dict[str, Any]],
    file_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compact scalar facts suitable for JSON injection (format B)."""
    summary_data = summary_data or {}
    facts: Dict[str, Any] = {}

    if file_info:
        fname = file_info.get("filename", "")
        if "\\" in fname:
            fname = fname.split("\\")[-1]
        if "/" in fname:
            fname = fname.split("/")[-1]
        facts["file"] = {
            "filename": fname or "Unknown",
            "line_count": file_info.get("line_count", 0),
            "size_bytes": file_info.get("size_bytes", 0),
        }

    cfg = summary_data.get("config") or {}
    if cfg:
        facts["task_config"] = {k: v for k, v in cfg.items() if v is not None and v != ""}

    es = summary_data.get("error_summary") or {}
    if es.get("total") is not None:
        facts["errors"] = {"total": es.get("total", 0), "by_component": es.get("by_component") or {}}

    lp = summary_data.get("latency_profile") or {}
    if (lp.get("data_points") or 0) > 0:
        facts["latency"] = {
            "samples": lp.get("data_points", 0),
            "source_avg_s": (lp.get("source") or {}).get("avg"),
            "handling_avg_s": (lp.get("handling") or {}).get("avg"),
            "target_avg_s": (lp.get("target") or {}).get("avg"),
            "bottleneck": (summary_data.get("bottleneck") or {}).get("primary"),
        }

    bp = summary_data.get("batch_profile") or {}
    if (bp.get("total_batches") or 0) > 0:
        facts["batches"] = {
            "total": bp.get("total_batches", 0),
            "avg_rows_per_batch": bp.get("avg_rows_per_batch"),
            "one_by_one_ratio": bp.get("one_by_one_ratio"),
        }

    cp = summary_data.get("cdc_pipeline")
    if cp:
        facts["cdc_pipeline"] = {
            "health_status": cp.get("health_status"),
            "memory_warnings": cp.get("memory_warnings", 0),
            "disconnections": cp.get("disconnections", 0),
        }

    fl = summary_data.get("full_load_activity") or {}
    if fl.get("available"):
        fls = fl.get("summary") or {}
        facts["full_load"] = {
            "completed": fls.get("full_load_completed"),
            "tables_total": fls.get("tables_total", 0),
            "tables_loaded": fls.get("tables_loaded", 0),
            "reload_events": fls.get("reload_events", 0),
        }

    return facts


def _extract_inventory_lines(inventory_text: str) -> List[str]:
    lines: List[str] = []
    for raw in inventory_text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("- "):
            lines.append(stripped[2:].strip())
    return lines


def _convert_fenced_blocks_to_evidence_xml(text: str) -> str:
    """Replace fenced excerpt blocks with <evidence anchor=...> tags."""
    if not text or "<evidence " in text:
        return text

    def _replace(match: re.Match) -> str:
        body = match.group(1).strip()
        anchor_m = _LINE_ANCHOR_RE.search(body)
        anchor = f"LINE {anchor_m.group(1)}" if anchor_m else "LINE unknown"
        return f'<evidence anchor="{xml_escape(anchor)}">\n{xml_escape(body)}\n</evidence>'

    converted = _FENCED_BLOCK_RE.sub(_replace, text)
    if converted != text:
        return converted

    if "```" in text:
        parts = text.split("```")
        out = [parts[0]]
        for i in range(1, len(parts), 2):
            if i >= len(parts):
                break
            body = parts[i].strip()
            if i + 1 < len(parts):
                anchor_m = _LINE_ANCHOR_RE.search(body)
                anchor = f"LINE {anchor_m.group(1)}" if anchor_m else "LINE unknown"
                out.append(f'<evidence anchor="{xml_escape(anchor)}">\n{xml_escape(body)}\n</evidence>')
                out.append(parts[i + 1])
        return "".join(out)
    return text


def render_markdown(sections: List[BudgetedSection]) -> str:
    """Format A — Markdown (current default)."""
    return "\n\n".join(s.text.strip() for s in sections if s.text.strip())


def render_json_markdown(
    sections: List[BudgetedSection],
    *,
    summary_data: Optional[Dict[str, Any]] = None,
    file_info: Optional[Dict[str, Any]] = None,
) -> str:
    """Format B — JSON scalar facts + Markdown tables + XML evidence."""
    preamble = ""
    inventory_lines: List[str] = []
    markdown_parts: List[str] = []
    evidence_parts: List[str] = []

    for sec in sections:
        text = sec.text.strip()
        if not text:
            continue
        if sec.category == "facts_inventory" and "evidence package" in text.lower():
            preamble = text
            continue
        if sec.category == "facts_inventory" and "Data Available" in text:
            inventory_lines = _extract_inventory_lines(text)
            continue
        if sec.category == "facts_inventory" and "Authoritative Facts" in text:
            continue
        if sec.category == "line_evidence":
            evidence_parts.append(_convert_fenced_blocks_to_evidence_xml(text))
            continue
        if sec.category in (
            "error_aggregates",
            "telemetry",
            "task_config_tuning",
            "graph_structural_facts",
            "kb_release_notes",
        ):
            markdown_parts.append(text)
            continue
        if sec.category == "facts_inventory":
            markdown_parts.append(text)
        else:
            markdown_parts.append(text)

    scalar = build_scalar_facts_dict(summary_data, file_info)
    if inventory_lines:
        scalar["inventory"] = inventory_lines

    parts: List[str] = []
    if preamble:
        parts.append(preamble)
    parts.append(
        "### Scalar facts (JSON — authoritative)\n"
        f"```json\n{json.dumps(scalar, indent=2, default=str)}\n```"
    )
    parts.extend(markdown_parts)
    parts.extend(evidence_parts)
    return "\n\n".join(p for p in parts if p.strip())


def render_xml(sections: List[BudgetedSection]) -> str:
    """Format C — XML-heavy wrapper."""
    inner: List[str] = ['<report_context>']
    for sec in sections:
        text = sec.text.strip()
        if not text:
            continue
        cat = xml_escape(sec.category)
        if sec.category == "line_evidence":
            payload = _convert_fenced_blocks_to_evidence_xml(text)
            inner.append(f'  <section category="{cat}" format="evidence">')
            inner.append(f"    {payload}")
            inner.append("  </section>")
        else:
            inner.append(f'  <section category="{cat}">')
            inner.append(f"    <![CDATA[\n{text}\n    ]]>")
            inner.append("  </section>")
    inner.append("</report_context>")
    return "\n".join(inner)


def render_payload(
    sections: List[BudgetedSection],
    format_name: Optional[str] = None,
    *,
    summary_data: Optional[Dict[str, Any]] = None,
    file_info: Optional[Dict[str, Any]] = None,
) -> str:
    """Render budgeted evidence sections in the requested payload format."""
    fmt = normalize_payload_format(format_name)
    if fmt == "json_markdown":
        return render_json_markdown(sections, summary_data=summary_data, file_info=file_info)
    if fmt == "xml":
        return render_xml(sections)
    return render_markdown(sections)
