"""
Post-LLM response validation before report save.

Wraps deterministic graders with validation context extraction, pass/fail
semantics, and an optional single correction retry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

from backend.database import LogError
from backend.llm.ar_props_lookup import _TUNING_RELEVANT_NAMES
from backend.llm.report_grader import GradeResult, grade_report

PASS_NORMALIZED_THRESHOLD = 0.85
MIN_SECTIONS_FOR_PASS = 4

_CODE_COUNT_RE = re.compile(r"`(\[[^\]]+\])`\s*×\s*(\d+)")


@dataclass
class ValidationContext:
    chart_attached: bool = False
    allowed_param_names: Optional[Set[str]] = None
    authoritative_counts: Optional[Dict[str, int]] = None
    valid_line_numbers: Optional[Set[int]] = None
    max_completion_tokens: Optional[int] = None
    quick: bool = False


@dataclass
class ValidationResult:
    passed: bool
    grade: GradeResult
    issues: List[str] = field(default_factory=list)
    correction_applied: bool = False
    final_content: str = ""
    correction_prompt_tokens: int = 0
    correction_completion_tokens: int = 0
    correction_cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.grade.score,
            "max_score": self.grade.max_score,
            "normalized_score": self.grade.metrics.get("normalized_score"),
            "checks": self.grade.checks,
            "issues": self.issues,
            "correction_applied": self.correction_applied,
            "correction_prompt_tokens": self.correction_prompt_tokens,
            "correction_completion_tokens": self.correction_completion_tokens,
            "correction_cost_usd": self.correction_cost_usd,
        }


def extract_authoritative_counts(user_prompt: str) -> Optional[Dict[str, int]]:
    """Parse authoritative error-code counts from Log Aggregates block."""
    if "## Log Aggregates" not in (user_prompt or ""):
        return None
    counts: Dict[str, int] = {}
    for match in _CODE_COUNT_RE.finditer(user_prompt):
        counts[match.group(1)] = int(match.group(2))
    return counts or None


def extract_tuning_allowlist(user_prompt: str) -> Optional[Set[str]]:
    """Parameter names allowed from the Tuning Reference section."""
    marker = "## Tuning Reference"
    if marker not in (user_prompt or ""):
        return None
    section = user_prompt.split(marker, 1)[1]
    end = re.search(r"\n## ", section)
    chunk = section[: end.start()] if end else section[:3000]
    mentioned = set(re.findall(r"`([a-zA-Z][a-zA-Z0-9_]*)`", chunk))
    if not mentioned:
        return set(_TUNING_RELEVANT_NAMES)
    return {p for p in mentioned if p in _TUNING_RELEVANT_NAMES} or mentioned


def build_validation_context(
    db,
    file_id: int,
    bundle,
    *,
    max_completion_tokens: Optional[int] = None,
) -> ValidationContext:
    """Build grounding context for validate_report from a prompt bundle."""
    user_msg = next(
        (m.get("content", "") for m in bundle.messages if m.get("role") == "user"),
        "",
    )
    chart_attached = bundle.chart_image_data is not None or (
        "Attached: Latency Over Time" in user_msg
    )

    valid_lines: Set[int] = set()
    db_error_total = 0
    for err in db.query(LogError).filter(LogError.file_id == file_id).all():
        db_error_total += 1
        if err.line_number:
            valid_lines.add(int(err.line_number))

    authoritative_counts = extract_authoritative_counts(user_msg)
    if db_error_total:
        authoritative_counts = dict(authoritative_counts or {})
        authoritative_counts["total_indexed_errors"] = db_error_total

    return ValidationContext(
        chart_attached=chart_attached,
        allowed_param_names=extract_tuning_allowlist(user_msg),
        authoritative_counts=authoritative_counts,
        valid_line_numbers=valid_lines or None,
        max_completion_tokens=max_completion_tokens,
        quick=bool(bundle.quick),
    )


def build_correction_user_message(issues: List[str]) -> str:
    """User message asking the model to fix validator-reported issues."""
    lines = [
        "Fix the following validation issues in your report.",
        "Output the **complete** corrected Markdown report only — no preamble or commentary.",
        "",
    ]
    for idx, issue in enumerate(issues[:15], 1):
        lines.append(f"{idx}. {issue}")
    return "\n".join(lines)


def _section_pass_count(checks: Dict[str, bool]) -> int:
    return sum(1 for key, ok in checks.items() if key.startswith("section_") and ok)


def compute_passed(grade: GradeResult, *, quick: bool, extra_issues: List[str]) -> bool:
    if grade.checks.get("non_empty") is False:
        return False
    if quick:
        return True
    if extra_issues:
        return False
    normalized = grade.metrics.get("normalized_score", 0.0)
    return (
        grade.checks.get("health_score_x_of_5", False)
        and _section_pass_count(grade.checks) >= MIN_SECTIONS_FOR_PASS
        and normalized >= PASS_NORMALIZED_THRESHOLD
    )


def validate_report(
    content: str,
    context: ValidationContext,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> ValidationResult:
    """Run deterministic checks; does not call the LLM."""
    grade = grade_report(
        content,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        allowed_param_names=context.allowed_param_names,
        chart_attached=context.chart_attached,
        authoritative_counts=context.authoritative_counts,
        valid_line_numbers=context.valid_line_numbers,
    )

    extra_issues: List[str] = []
    if (
        context.max_completion_tokens
        and output_tokens
        and output_tokens > context.max_completion_tokens
    ):
        extra_issues.append(
            f"Completion used {output_tokens} tokens (budget {context.max_completion_tokens})"
        )

    issues = list(grade.issues) + extra_issues
    passed = compute_passed(grade, quick=context.quick, extra_issues=extra_issues)

    return ValidationResult(
        passed=passed,
        grade=grade,
        issues=issues,
        final_content=content or "",
    )


def validate_and_correct(
    content: str,
    context: ValidationContext,
    messages: List[Dict[str, str]],
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    llm_call: Optional[Callable[[List[Dict[str, str]]], Any]] = None,
) -> ValidationResult:
    """
    Validate report content; optionally run one correction LLM call on failure.

    ``llm_call`` receives extended messages (original + assistant draft + fix request).
    """
    result = validate_report(
        content,
        context,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    if result.passed or context.quick or not llm_call or not result.issues:
        return result

    correction_messages = list(messages) + [
        {"role": "assistant", "content": content},
        {"role": "user", "content": build_correction_user_message(result.issues)},
    ]
    try:
        corrected = llm_call(correction_messages)
    except Exception:
        return result

    if not corrected or not getattr(corrected, "content", "").strip():
        return result

    revised = validate_report(
        corrected.content,
        context,
        input_tokens=input_tokens + getattr(corrected, "prompt_tokens", 0),
        output_tokens=getattr(corrected, "completion_tokens", 0),
    )

    if revised.grade.score >= result.grade.score:
        revised.correction_applied = True
        revised.final_content = corrected.content
        revised.correction_prompt_tokens = getattr(corrected, "prompt_tokens", 0)
        revised.correction_completion_tokens = getattr(corrected, "completion_tokens", 0)
        revised.correction_cost_usd = getattr(corrected, "cost_usd", 0.0) or 0.0
        return revised

    return result


def grade_llm_output(
    content: str,
    context: ValidationContext,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> Dict[str, Any]:
    """Grade report content for prompt-lab compare (no correction retry)."""
    result = validate_report(
        content,
        context,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    out = result.to_dict()
    qpit = result.grade.quality_per_input_token
    if qpit is not None:
        out["quality_per_input_token"] = qpit
    return out
