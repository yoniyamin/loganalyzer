"""Context ranker: score → merge → truncate to token budget.

Produces ranked, citation-ready structural_facts XML for LLM prompts.
"""
import re
import math
from typing import Any, Dict, List, Optional, Tuple


# Approximate token count (whitespace + punctuation splitting)
def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def rank_neighbors(
    neighbors: List[Dict[str, Any]],
    anchor_line: int,
    total_lines: int,
) -> List[Dict[str, Any]]:
    """Score each neighbor: edge_weight * decay(hop) * temporal_proximity."""
    scored = []
    for n in neighbors:
        hop = n.get("hop", 1)
        raw_score = n.get("score", 0.5)
        line_num = n.get("line_number")

        # Temporal proximity: closer lines score higher
        temporal = 1.0
        if line_num is not None and total_lines > 0:
            distance = abs(line_num - anchor_line)
            temporal = max(0.2, 1.0 - (distance / total_lines))

        # Hop decay
        decay = 1.0 / (1.0 + hop * 0.5)

        # Confidence multiplier: extracted > inferred
        conf = 1.2 if n.get("provenance") == "EXTRACTED" else 1.0

        final_score = raw_score * decay * conf * temporal
        scored.append({**n, "_rank_score": final_score})

    scored.sort(key=lambda x: -x["_rank_score"])
    return scored


def merge_overlapping_windows(
    snippets: List[Dict[str, Any]],
    window_before: int = 3,
    window_after: int = 3,
    max_window: int = 20,
) -> List[Dict[str, Any]]:
    """Merge overlapping line windows into contiguous ranges.

    Each snippet should have 'line_number' and optionally 'context_lines'.
    Returns merged groups with start/end line and combined text.
    """
    if not snippets:
        return []

    # Sort by line number
    sorted_snips = sorted(
        [s for s in snippets if s.get("line_number") is not None],
        key=lambda x: x["line_number"]
    )

    if not sorted_snips:
        return snippets

    groups: List[Dict[str, Any]] = []
    current_group = {
        "start": sorted_snips[0]["line_number"] - window_before,
        "end": sorted_snips[0]["line_number"] + window_after,
        "items": [sorted_snips[0]],
    }

    for snip in sorted_snips[1:]:
        snip_start = snip["line_number"] - window_before
        snip_end = snip["line_number"] + window_after

        if snip_start <= current_group["end"] + 1:
            # Overlaps — extend group
            current_group["end"] = max(current_group["end"], snip_end)
            current_group["items"].append(snip)
            # Cap window size
            if current_group["end"] - current_group["start"] > max_window:
                current_group["end"] = current_group["start"] + max_window
        else:
            groups.append(current_group)
            current_group = {"start": snip_start, "end": snip_end, "items": [snip]}

    groups.append(current_group)
    return groups


def build_structural_facts_xml(
    ranked_neighbors: List[Dict[str, Any]],
    anchor_line: int,
    max_tokens: int = 1500,
) -> str:
    """Build citation-ready XML from ranked neighbors, respecting token budget.

    Format:
      <structural_facts anchor="line:123">
        <c1 type="co_occurs_within" line="125">error text...</c1>
        <c2 type="has_code" label="ORA-00054"/>
        ...
      </structural_facts>
    """
    lines = [f'<structural_facts anchor="line:{anchor_line}">']
    token_count = _approx_tokens(lines[0])
    citation_idx = 0

    for n in ranked_neighbors:
        citation_idx += 1
        cid = f"c{citation_idx}"

        # Build the fact element
        attrs = f'type="{n.get("edge_type", "related")}"'
        if n.get("line_number") is not None:
            attrs += f' line="{n["line_number"]}"'
        if n.get("label"):
            attrs += f' label="{_xml_escape(n["label"])}"'

        # Content: snippet or label
        content = ""
        if n.get("context_lines"):
            content = " | ".join(n["context_lines"][:3])
        elif n.get("label"):
            content = n["label"]

        if content:
            fact_line = f"  <{cid} {attrs}>{_xml_escape(content)}</{cid}>"
        else:
            fact_line = f"  <{cid} {attrs}/>"

        fact_tokens = _approx_tokens(fact_line)
        if token_count + fact_tokens > max_tokens:
            break

        lines.append(fact_line)
        token_count += fact_tokens

    lines.append("</structural_facts>")
    return "\n".join(lines)


def _xml_escape(text: str) -> str:
    """Minimal XML escaping for attribute/content values."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def deduplicate_facts(facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove duplicate facts (same line_number or same label)."""
    seen_lines = set()
    seen_labels = set()
    unique = []

    for f in facts:
        ln = f.get("line_number")
        label = f.get("label")

        if ln is not None:
            if ln in seen_lines:
                continue
            seen_lines.add(ln)
        elif label:
            if label in seen_labels:
                continue
            seen_labels.add(label)

        unique.append(f)
    return unique
