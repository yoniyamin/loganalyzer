"""
Deterministic graders for AI report quality (no LLM judge).

Used by prompt-lab regression and post-generation validation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


REQUIRED_SECTIONS = (
    "Executive Summary",
    "Key Findings",
    "Performance",
    "Issues",
    "Error",
    "Risk Assessment",
)

HEALTH_SCORE_RE = re.compile(
    r"\b([1-5])\s*/\s*5\b|Health Score.*?([1-5])\s*/\s*5",
    re.IGNORECASE | re.DOTALL,
)

BANNED_VAGUE_RE = re.compile(
    r"\b(several|multiple|many)\b(?!\s*\d)(?!\s*×)",
    re.IGNORECASE,
)

CHART_CLAIM_RE = re.compile(
    r"(latency over time graph|attached.*chart|as shown in the graph)",
    re.IGNORECASE,
)

LINE_CITE_RE = re.compile(r"\bLINE\s+(\d+)\b", re.IGNORECASE)

NUMBERED_SECTION_RE = re.compile(
    r"^\d+\.\s+\*\*(Executive Summary|Key Findings|Performance|Issues|Error|Risk Assessment)",
    re.IGNORECASE | re.MULTILINE,
)

TRUNCATION_ARTIFACT_RE = re.compile(r"(?<=\S)/{2,}\s*$", re.MULTILINE)


@dataclass
class GradeResult:
    score: float
    max_score: float
    checks: Dict[str, bool] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def quality_per_input_token(self) -> Optional[float]:
        inp = self.metrics.get("input_tokens")
        if inp and inp > 0:
            return round(self.score / inp, 6)
        return None


def _section_headers(content: str) -> List[str]:
    return [
        m.group(1).strip()
        for m in re.finditer(r"^#{1,3}\s+\*?\*?([^*\n]+?)\*?\*?\s*$", content, re.MULTILINE)
    ]


def _section_present(headers: List[str], keyword: str) -> bool:
    kw = keyword.lower()
    return any(kw in h.lower() for h in headers)


def grade_report(
    content: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    allowed_param_names: Optional[Set[str]] = None,
    chart_attached: bool = False,
    authoritative_counts: Optional[Dict[str, int]] = None,
    valid_line_numbers: Optional[Set[int]] = None,
) -> GradeResult:
    """Score a report against structural and grounding checks."""
    checks: Dict[str, bool] = {}
    issues: List[str] = []
    score = 0.0
    max_score = 0.0

    if not (content or "").strip():
        return GradeResult(
            score=0.0,
            max_score=10.0,
            checks={"non_empty": False},
            issues=["Report content is empty"],
            metrics={"input_tokens": input_tokens, "output_tokens": output_tokens},
        )

    headers = _section_headers(content)

    # Markdown ## headers (not numbered-list section titles)
    max_score += 1.0
    h2_ok = len(headers) >= 4 and not NUMBERED_SECTION_RE.search(content)
    checks["markdown_h2_sections"] = h2_ok
    if h2_ok:
        score += 1.0
    else:
        issues.append("Sections must use ## Markdown headers, not numbered list titles (1. 2. 3.)")

    # No truncation artifacts
    max_score += 1.0
    trunc_ok = not TRUNCATION_ARTIFACT_RE.search(content)
    checks["no_truncation_artifacts"] = trunc_ok
    if trunc_ok:
        score += 1.0
    else:
        issues.append("Report ends with truncation artifact (trailing slashes)")

    # Section structure (6 checks, weight 1 each)
    for sec in REQUIRED_SECTIONS:
        max_score += 1.0
        ok = _section_present(headers, sec)
        checks[f"section_{sec.lower().replace(' ', '_')}"] = ok
        if ok:
            score += 1.0
        else:
            issues.append(f"Missing section matching: {sec}")

    # Health score format
    max_score += 1.0
    health_ok = bool(HEALTH_SCORE_RE.search(content))
    checks["health_score_x_of_5"] = health_ok
    if health_ok:
        score += 1.0
    else:
        issues.append("Health score not in X/5 format")

    # No chart claims without attachment
    max_score += 1.0
    chart_ok = not CHART_CLAIM_RE.search(content) or chart_attached
    checks["no_unsupported_chart_claims"] = chart_ok
    if chart_ok:
        score += 1.0
    else:
        issues.append("Report references a chart/graph but none was attached")

    # Banned vague phrases
    max_score += 1.0
    vague_ok = not BANNED_VAGUE_RE.search(content)
    checks["no_vague_counts"] = vague_ok
    if vague_ok:
        score += 1.0
    else:
        issues.append("Uses vague quantifiers (several/multiple) without counts")

    # Parameter allowlist (optional)
    if allowed_param_names is not None:
        max_score += 1.0
        backtick_params = set(re.findall(r"`([a-zA-Z][a-zA-Z0-9_]*)`", content))
        unknown = {p for p in backtick_params if p not in allowed_param_names}
        param_ok = len(unknown) == 0
        checks["params_in_allowlist"] = param_ok
        if param_ok:
            score += 1.0
        else:
            issues.append(f"Unknown parameter names: {', '.join(sorted(unknown)[:5])}")

    # LINE citation validity (optional)
    if valid_line_numbers is not None:
        max_score += 1.0
        cited = {int(m.group(1)) for m in LINE_CITE_RE.finditer(content)}
        invalid = cited - valid_line_numbers
        line_ok = len(invalid) == 0
        checks["line_citations_valid"] = line_ok
        if line_ok:
            score += 1.0
        elif cited:
            issues.append(f"Invalid LINE citations: {sorted(invalid)[:5]}")

    # Count accuracy vs authoritative facts (optional)
    if authoritative_counts:
        max_score += 1.0
        count_ok = True
        for label, expected in authoritative_counts.items():
            if str(expected) not in content:
                count_ok = False
                issues.append(f"Expected count {expected} for {label} not found in report")
        checks["authoritative_counts_present"] = count_ok
        if count_ok:
            score += 1.0

    return GradeResult(
        score=score,
        max_score=max_score,
        checks=checks,
        issues=issues,
        metrics={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "section_count": len(headers),
            "normalized_score": round(score / max_score, 4) if max_score else 0.0,
        },
    )


def assert_no_analysis_request_in_prompt(prompt_text: str) -> None:
    """Regression guard: user payload must not contain competing outlines."""
    if "## Analysis Request" in prompt_text:
        raise AssertionError("Prompt still contains ## Analysis Request block")
