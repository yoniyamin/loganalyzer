"""
Phase 7 — evidence insufficiency detection for log embedding fallback.

Log Chroma (chroma_db/) is used only when the deterministic evidence package
cannot satisfy the report contract. KB Chroma (chroma_kb/) is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

DEFAULT_MERGE_CAP = 30
DEFAULT_SQLITE_EXCERPT_LIMIT = 40


@dataclass
class EvidenceInsufficiencyAssessment:
    insufficient: bool
    reasons: List[str] = field(default_factory=list)
    retrieval_query: Optional[str] = None


def assess_evidence_insufficiency(
    *,
    quick: bool,
    focus_mode: Optional[str],
    db_error_count: int,
    sqlite_excerpt_count: int,
    warning_count: int,
    merge_cap: int = DEFAULT_MERGE_CAP,
    sqlite_limit: int = DEFAULT_SQLITE_EXCERPT_LIMIT,
) -> EvidenceInsufficiencyAssessment:
    """
    Return True when deterministic SQLite + compiler evidence is likely incomplete.

    Not triggered by error count alone — only when caps or focus mode leave gaps.
    """
    if quick:
        return EvidenceInsufficiencyAssessment(insufficient=False)

    reasons: List[str] = []

    if focus_mode == "errors" and db_error_count == 0 and warning_count == 0:
        reasons.append(
            "errors focus requested but no indexed errors or warnings in SQLite"
        )

    if db_error_count > merge_cap:
        reasons.append(
            f"{db_error_count} indexed errors exceed deterministic excerpt budget "
            f"(SQLite limit {sqlite_limit}, prompt merge cap {merge_cap})"
        )

    return EvidenceInsufficiencyAssessment(
        insufficient=bool(reasons),
        reasons=reasons,
    )


def build_semantic_retrieval_query(
    *,
    error_snippets: List[str],
    error_codes: List[str],
    focus_mode: Optional[str] = None,
    reasons: Optional[List[str]] = None,
) -> str:
    """Build a query string from top error codes + symptom snippets."""
    parts: List[str] = []

    for code in (error_codes or [])[:6]:
        parts.append(code.strip("[]"))

    for snippet in (error_snippets or [])[:5]:
        text = " ".join(snippet.split())[:120]
        if text:
            parts.append(text)

    if focus_mode == "errors":
        parts.append("warning timeout connection failure replication error")

    if reasons:
        for reason in reasons[:2]:
            if "errors focus" in reason.lower():
                parts.append("warning alert informational error symptom")

    query = " ".join(parts).strip()
    return query[:500] if query else "replication error warning timeout failure"


def insufficiency_metrics(assessment: EvidenceInsufficiencyAssessment) -> Dict[str, Any]:
    """Serializable stats for prompt-lab / logging."""
    return {
        "embedding_fallback": assessment.insufficient,
        "insufficiency_reasons": list(assessment.reasons),
    }
