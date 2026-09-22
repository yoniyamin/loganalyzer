"""
Phase 5 — Gated graph enrichment for report prompts.

Uses the per-file SQLite adjacency graph (backend.core.graph), NOT chroma_db.
chroma_db stores semantic log embeddings; structural neighborhood facts come
from co-occurrence / component / error-code edges built at index time.

Injection is skipped when get_related_context() marks the neighborhood weak.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.llm.evidence_compiler import estimate_tokens, select_representative_excerpts

logger = logging.getLogger(__name__)

_LINE_ANCHOR_RE = re.compile(r"\bLINE\s+(\d+)\b", re.IGNORECASE)

DEFAULT_MAX_ANCHORS = 3
DEFAULT_TOTAL_TOKEN_BUDGET = 300


@dataclass
class GraphEnrichmentResult:
    """Outcome of gated graph injection attempt."""

    xml_block: Optional[str] = None
    anchor_lines: List[int] = field(default_factory=list)
    injected_anchors: List[int] = field(default_factory=list)
    skipped_weak: List[int] = field(default_factory=list)
    estimated_tokens: int = 0

    @property
    def injected(self) -> bool:
        return bool(self.xml_block)


def extract_anchor_lines(error_contexts: List[str], *, top_n: int = 3) -> List[int]:
    """Top error-pattern anchor LINE numbers (one per representative excerpt)."""
    anchors: List[int] = []
    for block in select_representative_excerpts(error_contexts, top_n=top_n):
        match = _LINE_ANCHOR_RE.search(block)
        if match:
            anchors.append(int(match.group(1)))
    return anchors


def should_attempt_graph_injection(
    error_contexts: List[str],
    *,
    focus_mode: Optional[str] = None,
    include_graph: bool = True,
) -> bool:
    if not include_graph or not error_contexts:
        return False
    if focus_mode == "configuration":
        return False
    return True


def build_gated_graph_context(
    db: Session,
    file_id: int,
    error_contexts: List[str],
    *,
    focus_mode: Optional[str] = None,
    include_graph: bool = True,
    max_anchors: int = DEFAULT_MAX_ANCHORS,
    max_total_tokens: int = DEFAULT_TOTAL_TOKEN_BUDGET,
) -> GraphEnrichmentResult:
    """
    Build structural_facts XML for up to max_anchors error patterns.

    Skips anchors where the graph neighborhood is weak (fewer than 2 enriched
    neighbors — same gate as error_resolution._build_structural_facts).
    """
    result = GraphEnrichmentResult()
    if not should_attempt_graph_injection(
        error_contexts, focus_mode=focus_mode, include_graph=include_graph,
    ):
        return result

    from backend.llm.error_resolution import _build_structural_facts

    anchors = extract_anchor_lines(error_contexts, top_n=max_anchors)
    result.anchor_lines = anchors
    if not anchors:
        return result

    per_anchor_budget = max(80, max_total_tokens // len(anchors))
    xml_parts: List[str] = []
    tokens_used = 0

    for line_num in anchors:
        if tokens_used >= max_total_tokens:
            break
        remaining = max_total_tokens - tokens_used
        budget = min(per_anchor_budget, remaining)
        xml = _build_structural_facts(db, file_id, line_num, max_tokens=budget)
        if not xml:
            result.skipped_weak.append(line_num)
            continue
        xml_parts.append(xml.strip())
        result.injected_anchors.append(line_num)
        tokens_used += estimate_tokens(xml)

    if not xml_parts:
        return result

    header = (
        "## Structural context (graph — gated)\n\n"
        "Co-occurrence and component neighborhood around top error anchors. "
        "Use alongside Log Aggregates; skip if unrelated to your findings.\n"
    )
    result.xml_block = header + "\n\n".join(xml_parts)
    result.estimated_tokens = estimate_tokens(result.xml_block)
    logger.info(
        "Graph enrichment file_id=%s anchors=%s injected=%s skipped_weak=%s est_tokens=%s",
        file_id,
        anchors,
        result.injected_anchors,
        result.skipped_weak,
        result.estimated_tokens,
    )
    return result


def graph_enrichment_metrics(result: GraphEnrichmentResult) -> Dict[str, Any]:
    """Serializable metrics for prompt-lab compare / grader delta tracking."""
    return {
        "graph_injected": result.injected,
        "graph_anchor_lines": result.anchor_lines,
        "graph_injected_anchors": result.injected_anchors,
        "graph_skipped_weak": result.skipped_weak,
        "graph_est_tokens": result.estimated_tokens,
    }
