"""
Deterministic evidence compiler for LLM report prompts.

Python computes and packages facts; the model interprets only.
Enforces per-category token budgets with fixed truncation priority.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Approximate tokens (matches prompts.count_prompt_tokens heuristic)
_CHARS_PER_TOKEN = 4

_NORMALIZE_PATTERNS = [
    re.compile(r"\bLINE\s+\d+\b", re.IGNORECASE),
    re.compile(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}"),
    re.compile(r"\bst_\d+_\w+"),
    re.compile(r"\b(subtask|line)\s+\d+", re.IGNORECASE),
]

_CODE_EXTRACT = re.compile(r"\[\d{5,8}\]")

_TUNING_TRIGGERS_ODBC_TIMEOUT = re.compile(
    r"(?:timed?\s*out|timeout|HYT00|30149|executeTimeout|cdcTimeout|SOURCE_UNLOAD.*error)",
    re.IGNORECASE,
)

_TUNING_TRIGGERS_BATCH_PERF = re.compile(
    r"(?:cdcMinFileSize|cdcBatchTimeOut|bulkArraySize|BulkArraySize|batch.*(?:slow|timeout|efficiency)|"
    r"TARGET_LOAD|FILE_FACTORY|parallelApply|bulk_timeout)",
    re.IGNORECASE,
)


@dataclass
class EvidenceBudgets:
    """Per-category token ceilings (initial audit-mode targets)."""

    facts_inventory: int = 400
    error_aggregates: int = 600
    line_evidence: int = 800
    telemetry: int = 500
    task_config_tuning: int = 400
    graph_structural_facts: int = 300
    kb_release_notes: int = 400
    total_input_target: int = 6000


@dataclass
class BudgetedSection:
    category: str
    text: str
    priority: int = 3  # 1=never drop, 5=drop first
    tokens: int = 0

    def __post_init__(self) -> None:
        if not self.tokens:
            self.tokens = estimate_tokens(self.text)


@dataclass
class CompiledEvidence:
    sections: List[str] = field(default_factory=list)
    selected_error_contexts: List[str] = field(default_factory=list)
    budget_report: Dict[str, Any] = field(default_factory=dict)


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN)


def truncate_to_budget(text: str, budget_tokens: int) -> str:
    if budget_tokens <= 0:
        return ""
    max_chars = budget_tokens * _CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20].rstrip() + "\n… [truncated]"


def _normalize_error_body(block: str) -> Tuple[Optional[int], str, str]:
    """Return (line_num, normalized_key, raw_body) for one error excerpt block."""
    if not block or not isinstance(block, str):
        return None, "", block or ""

    lines = block.strip().split("\n")
    line_num = None
    body = block

    if lines and lines[0].startswith("LINE "):
        header = lines[0]
        parts = header.split("|")
        try:
            line_num = int(parts[0].replace("LINE", "").strip())
        except (ValueError, IndexError):
            pass
        body = "\n".join(lines[1:]) if len(lines) > 1 else header

    normalized = body
    for pat in _NORMALIZE_PATTERNS:
        normalized = pat.sub("", normalized)
    normalized = " ".join(normalized.split())[:160]
    if not normalized:
        normalized = body[:120]

    return line_num, normalized, body


def build_error_aggregates(error_contexts: List[str]) -> str:
    """Authoritative per-pattern error counts table."""
    if not error_contexts:
        return ""

    pattern_lines: Dict[str, List[int]] = defaultdict(list)
    code_counter: Counter = Counter()

    for block in error_contexts:
        line_num, normalized, _ = _normalize_error_body(block)
        if not normalized:
            continue
        pattern_lines[normalized].append(line_num if line_num is not None else 0)
        for m in _CODE_EXTRACT.finditer(block):
            code_counter[m.group(0)] += 1

    if not pattern_lines:
        return ""

    sorted_patterns = sorted(pattern_lines.items(), key=lambda x: -len(x[1]))

    parts: List[str] = ["## Log Aggregates (computed — authoritative)\n"]
    parts.append("| # | Occurrences | First LINE | Last LINE | Pattern (normalized) |")
    parts.append("|---|---|---|---|---|")
    for idx, (norm, line_nums) in enumerate(sorted_patterns[:10], 1):
        count = len(line_nums)
        valid = [ln for ln in line_nums if ln > 0]
        first = str(min(valid)) if valid else "?"
        last = str(max(valid)) if valid else "?"
        display = norm[:100] + ("…" if len(norm) > 100 else "")
        parts.append(f"| {idx} | {count} | {first} | {last} | {display} |")

    if code_counter:
        parts.append("\n**Distinct error codes:**")
        for code, cnt in code_counter.most_common(10):
            parts.append(f"- `{code}` × {cnt}")

    parts.append(
        "\nThese counts are computed from the full parsed log. "
        "Your report MUST reference them; do not say \"several\" or \"multiple\" when a count is given.\n"
    )
    return "\n".join(parts)


def select_representative_excerpts(
    error_contexts: List[str],
    *,
    top_n: int = 3,
    max_chars: int = 1200,
) -> List[str]:
    """One full LINE quote per top-N error patterns (evidence hierarchy slot 2)."""
    if not error_contexts or top_n <= 0:
        return []

    pattern_counts: Counter = Counter()
    pattern_example: Dict[str, str] = {}
    for block in error_contexts:
        _, normalized, _ = _normalize_error_body(block)
        if not normalized:
            continue
        pattern_counts[normalized] += 1
        if normalized not in pattern_example:
            pattern_example[normalized] = block.strip()

    selected: List[str] = []
    for norm, _ in pattern_counts.most_common(top_n):
        block = pattern_example[norm]
        if len(block) > max_chars:
            block = block[: max_chars - 20].rstrip() + "\n…"
        selected.append(block)
    return selected


def format_task_config(config: Optional[Dict[str, Any]]) -> str:
    """Render indexed task configuration as authoritative facts."""
    if not config:
        return ""

    labels = [
        ("source_type", "Source endpoint"),
        ("target_type", "Target endpoint"),
        ("apply_mode", "Apply mode"),
        ("merge_enabled", "MERGE enabled"),
        ("parallel_apply_threads", "Parallel apply threads"),
        ("bulk_timeout_ms", "Bulk timeout (ms)"),
        ("bulk_timeout_min_ms", "Bulk min timeout (ms)"),
        ("bulk_max_file_size_kb", "Bulk max file size (KB)"),
        ("stream_buffer_size", "Stream buffer size"),
        ("stream_buffers_number", "Stream buffers count"),
        ("stop_on_memory_limit", "Stop on memory limit"),
    ]

    rows: List[str] = []
    for key, label in labels:
        val = config.get(key)
        if val is None or val == "":
            continue
        if isinstance(val, bool):
            val = "yes" if val else "no"
        rows.append(f"| {label} | `{val}` |")

    if not rows:
        return ""

    parts = [
        "## Task Configuration (computed — authoritative)\n",
        "Values extracted from the log at indexing time. Cite these; do not invent settings.\n",
        "| Setting | Value |",
        "|---|---|",
        *rows,
        "",
    ]
    return "\n".join(parts)


def _pct_delta(a: float, b: float) -> str:
    if b == 0:
        return "n/a"
    pct = ((a - b) / b) * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.0f}%"


def build_authoritative_facts(summary_data: Dict[str, Any]) -> str:
    """Pre-computed numeric facts the model may cite but must not recalculate."""
    lines: List[str] = ["## Authoritative Facts (computed — do not recalculate)\n"]

    lp = summary_data.get("latency_profile") or {}
    if (lp.get("data_points") or 0) > 0:
        src = lp.get("source") or {}
        tgt = lp.get("target") or {}
        hnd = lp.get("handling") or {}
        src_avg = float(src.get("avg") or 0)
        tgt_avg = float(tgt.get("avg") or 0)
        hnd_avg = float(hnd.get("avg") or 0)
        delta = tgt_avg - src_avg
        lines.append("### Latency (sampled windows)")
        lines.append(
            f"- Source avg **{src_avg:.2f}s** | Handling avg **{hnd_avg:.2f}s** | "
            f"Target avg **{tgt_avg:.2f}s** ({lp.get('data_points', 0):,} samples)"
        )
        if src_avg > 0:
            lines.append(
                f"- Target − Source = **{delta:+.2f}s** ({_pct_delta(tgt_avg, src_avg)} vs source avg)"
            )
        bn = (summary_data.get("bottleneck") or {}).get("primary", "unknown")
        lines.append(f"- Bottleneck classifier: **{bn}**")

    bp = summary_data.get("batch_profile") or {}
    if (bp.get("total_batches") or 0) > 0:
        lines.append("\n### Batch apply")
        lines.append(f"- Total batches: **{bp.get('total_batches', 0):,}**")
        if bp.get("avg_rows_per_batch") is not None:
            lines.append(f"- Avg rows/batch: **{bp['avg_rows_per_batch']:.1f}**")
        if bp.get("one_by_one_ratio") is not None:
            lines.append(f"- One-by-one ratio: **{bp['one_by_one_ratio']:.1%}**")

    es = summary_data.get("error_summary") or {}
    if es.get("total"):
        lines.append(f"\n### Errors")
        lines.append(f"- Total errors indexed: **{es['total']:,}**")
        by_comp = es.get("by_component") or {}
        if by_comp:
            top = sorted(by_comp.items(), key=lambda x: -x[1])[:5]
            comp_str = ", ".join(f"{c} × {n}" for c, n in top)
            lines.append(f"- Top components: {comp_str}")

    spikes = summary_data.get("spikes") or {}
    if spikes.get("count"):
        lines.append(f"\n### Latency spikes: **{spikes['count']}** detected")

    recs = summary_data.get("recommendations") or []
    if recs:
        lines.append("\n### Pre-computed recommendations (validate/extend, do not replace)")
        for rec in recs[:6]:
            pri = (rec.get("priority") or "medium").upper()
            title = rec.get("title") or ""
            area = rec.get("area") or ""
            lines.append(f"- [{pri}] **{title}** ({area})")

    if len(lines) <= 1:
        return ""

    lines.append("")
    return "\n".join(lines)


@dataclass
class FocusPayloadPlan:
    """Per-focus-mode evidence package emphasis (Phase 3)."""

    include_task_config: bool = True
    include_authoritative_facts: bool = True
    include_error_aggregates: bool = True
    include_representative_quotes: bool = True
    include_warning_tail: bool = False
    include_performance_telemetry: bool = True
    include_kb_release_notes: bool = True
    include_full_tuning_reference: bool = False
    quote_top_n: int = 3
    telemetry_depth: str = "full"  # full | minimal | skip


def build_focus_payload_plan(
    focus_mode: Optional[str],
    summary_data: Dict[str, Any],
) -> FocusPayloadPlan:
    """Slice the evidence package by user-chosen analysis focus."""
    has_perf = bool(
        (summary_data.get("latency_profile") or {}).get("data_points")
        or (summary_data.get("batch_profile") or {}).get("total_batches")
        or summary_data.get("pain_tables")
    )
    has_fl = bool((summary_data.get("full_load_activity") or {}).get("available"))

    if not focus_mode:
        return FocusPayloadPlan()

    if focus_mode == "general_review":
        return FocusPayloadPlan(
            include_task_config=True,
            include_performance_telemetry=has_perf or has_fl,
            telemetry_depth="minimal" if not has_perf else "full",
            include_representative_quotes=True,
            quote_top_n=2,
            include_kb_release_notes=True,
        )

    if focus_mode == "performance":
        return FocusPayloadPlan(
            include_task_config=False,
            include_performance_telemetry=True,
            telemetry_depth="full",
            include_representative_quotes=True,
            quote_top_n=2,
            include_warning_tail=False,
        )

    if focus_mode == "errors":
        return FocusPayloadPlan(
            include_task_config=False,
            include_performance_telemetry=has_perf,
            telemetry_depth="minimal" if has_perf else "skip",
            include_warning_tail=True,
            include_representative_quotes=True,
            quote_top_n=3,
            include_kb_release_notes=True,
        )

    if focus_mode == "configuration":
        return FocusPayloadPlan(
            include_task_config=True,
            include_authoritative_facts=True,
            include_error_aggregates=False,
            include_representative_quotes=False,
            include_performance_telemetry=False,
            telemetry_depth="skip",
            include_full_tuning_reference=True,
            include_kb_release_notes=False,
        )

    return FocusPayloadPlan()


def format_warning_tail(warning_contexts: List[str], *, max_items: int = 12) -> str:
    """Recent warning sample for errors-focus sparse logs."""
    if not warning_contexts:
        return ""
    parts = [
        "## Recent warnings (computed — authoritative tail sample)\n",
        f"Showing the most recent {min(len(warning_contexts), max_items)} warning lines "
        "indexed from the log (severity W).\n",
    ]
    for i, ctx in enumerate(warning_contexts[:max_items], 1):
        parts.append(f"**Warning {i}:**\n```\n{ctx}\n```\n")
    return "\n".join(parts)


def detect_tuning_modes(
    summary_data: Dict[str, Any],
    error_contexts: List[str],
    *,
    focus_mode: Optional[str] = None,
) -> List[str]:
    """Return tuning reference modes to inject: 'timeout', 'batch'."""
    if focus_mode == "configuration":
        return ["timeout", "batch"]

    modes: List[str] = []
    combined = " ".join(error_contexts[:20])

    if _TUNING_TRIGGERS_ODBC_TIMEOUT.search(combined):
        modes.append("timeout")

    has_perf = (summary_data.get("latency_profile") or {}).get("data_points", 0) > 0
    has_batch = (summary_data.get("batch_profile") or {}).get("total_batches", 0) > 0
    target = (summary_data.get("config") or {}).get("target_type") or ""
    is_databricks = "databricks" in target.lower()

    if (
        focus_mode in (None, "performance", "configuration")
        and (has_perf or has_batch or is_databricks or _TUNING_TRIGGERS_BATCH_PERF.search(combined))
    ):
        if "batch" not in modes:
            modes.append("batch")

    return modes


def enforce_budgets(
    sections: List[BudgetedSection],
    budgets: EvidenceBudgets,
) -> Tuple[List[BudgetedSection], Dict[str, Any]]:
    """
    Trim sections to per-category and total budgets.

    Truncation priority: drop KB/RN first → reduce LINE quotes → compress telemetry
    → never drop aggregates or authoritative facts (priority 1).
    """
    category_caps = {
        "facts_inventory": budgets.facts_inventory,
        "error_aggregates": budgets.error_aggregates,
        "line_evidence": budgets.line_evidence,
        "telemetry": budgets.telemetry,
        "task_config_tuning": budgets.task_config_tuning,
        "graph_structural_facts": budgets.graph_structural_facts,
        "kb_release_notes": budgets.kb_release_notes,
    }

    report: Dict[str, Any] = {
        "categories": {},
        "total_tokens_before": sum(s.tokens for s in sections),
        "total_tokens_after": 0,
        "truncated": [],
    }

    # Per-category cap first
    for sec in sections:
        cap = category_caps.get(sec.category)
        if cap and sec.tokens > cap:
            sec.text = truncate_to_budget(sec.text, cap)
            sec.tokens = estimate_tokens(sec.text)
            report["truncated"].append(f"{sec.category}:category_cap")

    # Sort by priority descending for total budget trimming
    total = sum(s.tokens for s in sections)
    if total <= budgets.total_input_target:
        report["total_tokens_after"] = total
        for sec in sections:
            report["categories"][sec.category] = sec.tokens
        return [s for s in sections if s.text.strip()], report

    ordered = sorted(sections, key=lambda s: -s.priority)
    while total > budgets.total_input_target:
        trimmed = False
        for sec in ordered:
            if sec.priority <= 1 or sec.tokens <= 50:
                continue
            new_tokens = max(50, int(sec.tokens * 0.75))
            if new_tokens < sec.tokens:
                sec.text = truncate_to_budget(sec.text, new_tokens)
                sec.tokens = estimate_tokens(sec.text)
                report["truncated"].append(f"{sec.category}:total_budget")
                trimmed = True
                break
        new_total = sum(s.tokens for s in sections)
        if not trimmed or new_total >= total:
            break
        total = new_total

    report["total_tokens_after"] = sum(s.tokens for s in sections)
    for sec in sections:
        report["categories"][sec.category] = sec.tokens

    return [s for s in sections if s.text.strip()], report
