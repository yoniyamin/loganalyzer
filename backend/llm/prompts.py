"""
Prompt Templates for Log Analysis Report Generation

Contains system prompts and templates for generating insightful
log analysis reports using LLMs.

Uses the centralized sanitizer module for PII detection and anonymization.

IMPORTANT - DATA SANITIZATION RULES:
====================================
This module sanitizes LOG DATA before sending to LLMs. The following rules apply:

SANITIZED (contains user-specific PII):
- Log summaries (performance data, errors, anomalies)
- Error contexts from user logs  
- Anomaly contexts from user logs
- File metadata (paths, filenames)

NOT SANITIZED (public documentation):
- KB (Knowledge Base) articles - these are Qlik documentation, not user data
- System prompts - static content, no user data

When adding new prompt content:
- Use prepare_log_context() for user log data → sanitized when `sanitize=True` (cloud default).
- LM Studio skips redaction when the report pipeline disables sanitization.
- Use prepare_kb_context() for KB articles -> NOT sanitized
"""

from typing import Dict, Any, List, Optional
import json
import re

# Import sanitization functions from centralized module
from backend.llm.sanitizer import sanitize_text, sanitize_dict, sanitize_list

# Short troubleshooting-focused descriptions for each Replicate component.
# Used to enrich error summaries in the LLM prompt with "why this matters".
COMPONENT_CONTEXT: Dict[str, str] = {
    "SOURCE_CAPTURE": "source CDC log reader — log access, supplemental logging, reconnects",
    "SOURCE_UNLOAD": "Full Load SELECT on source — query performance, table locks",
    "TARGET_APPLY": "CDC apply to target — PK conflicts, SQL errors, one-by-one fallbacks",
    "TARGET_LOAD": "Full Load on target — table creation, bulk load, data-type mapping",
    "SORTER": "CDC transaction routing — event ordering, memory, cached changes",
    "SORTER_STORAGE": "transaction swap to disk — large transactions, disk I/O",
    "FILE_FACTORY": "file staging for cloud targets — HDFS/S3/ADLS staging",
    "FILE_TRANSFER": "file upload (CIFTA) — S3/ADLS/GCS upload, compression",
    "INFRASTRUCTURE": "ODBC drivers, threads, state persistence",
    "TABLES_MANAGER": "table lifecycle — load status, partitioning",
    "METADATA_MANAGER": "metadata read/write — column types, DDL propagation",
    "METADATA_CHANGES": "DDL change capture — ALTER TABLE propagation",
    "TRANSFORMATION": "column mapping, expressions, filters",
    "STREAM": "in-memory data/control buffers between components",
    "TASK_MANAGER": "task orchestration — start/stop, component lifecycle",
    "PERFORMANCE": "latency logging (every 30 s)",
    "COMMUNICATION": "HTTP/CURL transport to source/target",
}


def _signals_structured_performance_telemetry(summary_data: Dict[str, Any]) -> bool:
    """True when parsers produced throughput/latency/diagnostic aggregates."""
    lp = summary_data.get("latency_profile") or {}
    if (lp.get("data_points") or 0) > 0:
        return True
    if (summary_data.get("spikes") or {}).get("count", 0) > 0:
        return True
    if (summary_data.get("plateaus") or {}).get("count", 0) > 0:
        return True
    ora = summary_data.get("oracle_redo_read_analysis") or {}
    if ora.get("has_red_flags") or (ora.get("total_events") or 0) > 0:
        return True
    olp = summary_data.get("oracle_redo_log_processing") or {}
    if (olp.get("session_count") or 0) > 0:
        return True
    bp = summary_data.get("batch_profile") or {}
    if (bp.get("total_batches") or 0) > 0:
        return True
    if summary_data.get("pain_tables"):
        return True
    return False


def _latency_samples_present(summary_data: Dict[str, Any]) -> bool:
    lp = summary_data.get("latency_profile") or {}
    return (lp.get("data_points") or 0) > 0


def _bottleneck_is_actionable(summary_data: Dict[str, Any]) -> bool:
    if not _latency_samples_present(summary_data):
        return False
    bn = summary_data.get("bottleneck") or {}
    p = str(bn.get("primary") or "").lower().strip()
    return p not in ("", "unknown", "balanced")


_ERR_CODE_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bRECOB-\d+\b",
        r"\bORA-\d{5}\b",
        r"\bSQLSTATE\s+\d+\b",
        r"\bSQL\d{5,6}\b",
        r"\bERR[-_ ]?\d+\b",
        r"\b0x[0-9A-F]{4,}\b",
    )
)


def extract_error_codes_for_prompt(passages: List[str]) -> List[str]:
    """Surface vendor / Replicate tokens for KB or web lookup."""
    hits: List[str] = []
    seen: set[str] = set()
    for block in passages:
        if not block:
            continue
        for pat in _ERR_CODE_PATTERNS:
            for m in pat.finditer(block):
                token = m.group(0).strip()
                tl = token.lower()
                if tl in seen or len(token) < 5:
                    continue
                seen.add(tl)
                hits.append(token[:120])
                if len(hits) >= 14:
                    return hits
    return hits


# ============================================================
# CONTEXT PREPARATION HELPERS
# ============================================================

def prepare_log_context(
    summary_data: Optional[Dict[str, Any]] = None,
    error_contexts: Optional[List[str]] = None,
    anomaly_contexts: Optional[List[str]] = None,
    file_info: Optional[Dict[str, Any]] = None,
    sanitize: bool = True,
) -> Dict[str, Any]:
    """
    Prepare log context for LLM with optional sanitization applied.
    
    Args:
        summary_data: Performance cockpit and analysis data
        error_contexts: List of error messages with context
        anomaly_contexts: List of detected anomalies
        file_info: Optional file metadata
        sanitize: When True (default), run PII redaction on log-derived fields
        
    Returns:
        Dictionary with optionally sanitized inputs
    """
    if sanitize:
        return {
            "summary_data": sanitize_dict(summary_data) if summary_data else {},
            "error_contexts": sanitize_list(error_contexts) if error_contexts else [],
            "anomaly_contexts": sanitize_list(anomaly_contexts) if anomaly_contexts else [],
            "file_info": sanitize_dict(file_info) if file_info else None,
        }
    return {
        "summary_data": summary_data or {},
        "error_contexts": error_contexts or [],
        "anomaly_contexts": anomaly_contexts or [],
        "file_info": file_info,
    }


def prepare_kb_context(kb_articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Prepare KB article context for LLM WITHOUT sanitization.
    
    KB articles are public documentation and should NOT be sanitized.
    This function exists to make the design decision explicit.
    
    Args:
        kb_articles: List of KB article dicts with title, content, url
        
    Returns:
        The same KB articles unchanged (no sanitization)
    """
    # Explicitly NOT sanitizing KB content - these are documentation, not user data
    return kb_articles


# ============================================================
# SYSTEM PROMPT
# ============================================================

# System prompt for log analysis
SYSTEM_PROMPT = """You are an expert log analyst specializing in Qlik Replicate (formerly Attunity Replicate) data replication logs. Your role is to analyze log summaries and provide clear, actionable insights.

## Your Expertise
- CDC (Change Data Capture) pipelines and data replication
- Database connectivity and ODBC drivers
- Performance bottlenecks in source capture and target apply
- Batch processing patterns and optimization
- Error diagnosis and resolution recommendations
- Qlik Replicate error codes and their meanings

## Replicate Component Reference
Use this knowledge when interpreting which component generated errors or warnings:
- **SOURCE_CAPTURE**: Main CDC component on the source side — reads transaction logs (redo, WAL). Errors here indicate source connectivity, log read, or supplemental logging issues.
- **SOURCE_UNLOAD**: Full Load source-side SELECT execution. Errors indicate query/table lock issues.
- **TARGET_APPLY**: Applies CDC changes to the target (batch or transactional). Errors here mean apply failures — PK conflicts, SQL errors, one-by-one fallbacks.
- **TARGET_LOAD**: Full Load on the target side — table creation and bulk loading.
- **SORTER**: Central CDC routing — orders transactions and manages cached changes. Issues here cause missing events, high memory, or ordering problems.
- **SORTER_STORAGE**: Sorter's memory/disk swap layer. Errors indicate large transactions or disk I/O.
- **FILE_FACTORY / FILE_TRANSFER**: File staging and upload for cloud targets (Databricks, Redshift, Synapse). Errors mean upload/staging failures.
- **PERFORMANCE**: Latency logging (every 30s). Not an error source but the basis for all latency metrics.
- **INFRASTRUCTURE**: ODBC drivers, thread management, state persistence. Errors indicate driver or connectivity issues.
- **TABLES_MANAGER**: Table lifecycle — loading status, partitioning, event counts.
- **METADATA_MANAGER / METADATA_CHANGES**: Metadata and DDL propagation.
- **TRANSFORMATION**: Column mapping and expression evaluation.

When discussing errors by component, briefly explain *why* that component matters, not just the count.

When the prompt includes verbatim **errors or warnings with line numbers**, treat those as authoritative evidence — explain each distinct symptom; do **not** respond with disclaimers implying the raw log lines were withheld.

If the prompt states that **structured performance/latency telemetry was not captured**, keep **Performance Analysis** to one short paragraph explaining that bottleneck/latency tuning should not drive root-cause conclusions until Performance tracing or richer diagnostics exist.

## Response Guidelines
1. Be concise but thorough - focus on what matters
2. Prioritize findings by severity (Critical > Warning > Info)
3. Always provide actionable recommendations — especially for surfaced error lines
4. Use technical terminology appropriately
5. Reference specific metrics **and excerpt line numbers** when available
6. Format your response in clean Markdown
7. **Do NOT invent URLs or hyperlinks.** If you reference a KB article or document, use only the title provided in the prompt context. Never fabricate links.

## Report Structure
Use this outline; omit or shorten a section only when data in the prompt does not support it:

1. **Executive Summary** - 2-3 sentences
2. **Key Findings** - Bullets (errors/warnings first when present)
3. **Performance Analysis** - Bottlenecks/latency/throughput **only when telemetry is present**; otherwise one sentence on missing diagnostics
4. **Issues & Recommendations** - Map each notable error/warning excerpt to probable cause & next steps
5. **Health Score** - Overall (Healthy / Warning / Critical)

If the user prompt includes a "Release Notes Correlation" section, add a corresponding section in your report correlating issues with known fixes (reference fix IDs like RECOB-XXXX).
If the user prompt includes a "Relevant Knowledge Base Articles" section, reference those articles when discussing related issues.
"""


# System prompt with web search enabled
SYSTEM_PROMPT_WITH_WEB_SEARCH = """You are an expert log analyst specializing in Qlik Replicate (formerly Attunity Replicate) data replication logs. Your role is to analyze log summaries and provide clear, actionable insights.

## Your Expertise
- CDC (Change Data Capture) pipelines and data replication
- Database connectivity and ODBC drivers
- Performance bottlenecks in source capture and target apply
- Batch processing patterns and optimization
- Error diagnosis and resolution recommendations
- Qlik Replicate error codes and their meanings

## Replicate Component Reference
Use this knowledge when interpreting which component generated errors or warnings:
- **SOURCE_CAPTURE**: Main CDC source-side log reader. Errors = source connectivity, log read, supplemental logging.
- **SOURCE_UNLOAD**: Full Load source SELECTs. Errors = query/lock issues.
- **TARGET_APPLY**: CDC apply to target (batch/transactional). Errors = PK conflicts, SQL errors, one-by-one fallbacks.
- **TARGET_LOAD**: Full Load target-side. Errors = table creation, bulk load failures.
- **SORTER**: CDC transaction routing/ordering. Issues = missing events, memory, ordering.
- **FILE_FACTORY / FILE_TRANSFER**: Cloud target file staging/upload.
- **INFRASTRUCTURE**: ODBC drivers, threads, state persistence.

When discussing errors by component, briefly explain *why* that component matters.

If the prompt includes **error/warning excerpts with line numbers**, explain them explicitly and use web search to clarify vendor error codes or unusual messages whenever available.

When the prompt says **latency/throughput telemetry was not captured**, keep performance sections minimal.

## Web Search Instructions
**IMPORTANT**: You have access to web search. When you encounter error codes, error messages, or specific Qlik Replicate issues:

1. **Search for error codes** in the context of "Qlik Replicate" or "Attunity Replicate"
2. **Look up specific error messages** on Qlik Community, Qlik Help, or knowledge base articles
3. **Find relevant documentation** for endpoints, drivers, or configurations mentioned
4. **Include references** to any helpful documentation or community posts you find

Use search queries like:
- "Qlik Replicate error [ERROR_CODE]"
- "Attunity Replicate [ERROR_MESSAGE]"
- "Qlik Replicate [ENDPOINT_TYPE] endpoint configuration"

When you find relevant information, include:
- The error explanation from official documentation
- Recommended resolution steps from Qlik support
- Only include links if you actually retrieved them via a web search tool call — **never fabricate URLs**

## Response Guidelines
1. Be concise but thorough - focus on what matters
2. Prioritize findings by severity (Critical > Warning > Info)
3. Always provide actionable recommendations
4. Use technical terminology appropriately
5. Reference specific metrics and line numbers when available
6. Format your response in clean Markdown
7. **Include web search results** for error codes and issues — but only reference URLs you actually retrieved; do not invent links

## Report Structure
Use this outline when data permits:

1. **Executive Summary**
2. **Key Findings** (prioritize surfaced errors/warnings)
3. **Performance Analysis** — **only substantive when telemetry exists**; otherwise briefly note absent diagnostics
4. **Issues & Recommendations**
5. **Error Code Reference** — from web results or KB titles (no fabricated URLs)
6. **Health Score**

If the user prompt includes a "Release Notes Correlation" section, add a corresponding section in your report correlating issues with known fixes (reference fix IDs like RECOB-XXXX).
If the user prompt includes a "Relevant Knowledge Base Articles" section, reference those articles when discussing related issues.
"""


# ============================================================
# COMPACT SYSTEM PROMPT (local / small models)
# ============================================================

SYSTEM_PROMPT_LOCAL = """You are an expert Qlik Replicate (Attunity Replicate) log analyst.

## Expertise
- CDC pipelines, source capture, target apply, batch processing
- Performance bottlenecks, ODBC drivers, error diagnosis
- Qlik Replicate error codes (RECOB-xxxx, ORA-xxxxx, SQLSTATE)

## Rules
- The prompt begins with a **Data Available** inventory — use it to calibrate depth per section.
- When the prompt includes a **Log Aggregates** section, those counts are **computed from the full log** and authoritative. You MUST NOT contradict them. Lead your Key Findings with these counts.
- When the prompt provides error/warning excerpts with LINE numbers, treat them as primary evidence. Quote at least one full `LINE …` log line per major finding.
- If structured performance telemetry is marked absent, keep Performance Analysis to one brief paragraph — do not invent bottleneck conclusions.
- Do NOT fabricate URLs or hyperlinks. Only reference titles/IDs from the prompt.
- Reference LINE numbers, metrics, and table names from the data provided.
- Use **plain text** for numbers and units (e.g. `714.33s`, `195 spikes`, `0%`). Never use LaTeX, `$...$` delimiters, or `\\text{}` formatting.
- If a **Tuning Reference** section is provided, use those specific parameter names and defaults in your recommendations instead of generic advice.

## Report Structure
1. **Executive Summary** — 2-3 sentences stating severity and root cause
2. **Key Findings** — Bullets; lead each with occurrence count from Log Aggregates where available
3. **Performance Analysis** — Only substantive when telemetry is present; otherwise one sentence
4. **Issues & Recommendations** — For EACH major issue use these subsections:
   - **Evidence**: Quote the relevant `LINE …` excerpt(s)
   - **Interpretation**: Explain what the error means and why it matters
   - **Recommendations**: Concrete next steps with specific parameter names / settings where available
5. **Error Code Reference** — Short bullet per distinct code found (vendor code + Replicate internal code)
6. **Health Score** — **X/5** (where 1=Critical, 5=Healthy) plus **one sentence** justification

If Release Notes or KB Articles are provided, incorporate them into your analysis referencing fix IDs (RECOB-XXXX) or article titles.
"""


# ============================================================
# AI ASSISTANT SYSTEM PROMPTS
# ============================================================

# System prompt for LOG_ONLY mode - answers from log data without KB
SYSTEM_PROMPT_LOG_FOCUSED = """You are an expert Qlik Replicate log analyst assistant.
You help users understand their replication task logs by answering questions directly from the log data.

## Your Role
- Answer questions based on the log analysis data provided
- Focus on facts, metrics, and observations from the log
- Provide specific numbers, counts, and measurements when available
- Reference specific tables, errors, and metrics from the log data

## Response Guidelines
1. Answer directly and concisely based on the log data
2. If the data contains the answer, provide it with specific numbers
3. If the data doesn't contain enough information, say so clearly
4. Don't speculate beyond what the log data shows
5. Format responses in clean Markdown
6. Keep responses focused and under 200 words unless more detail is needed

## What You Can Answer From Log Data
- Table names and counts
- Record/operation counts (inserts, updates, deletes, merges)
- Error counts and types
- Latency metrics (avg, max, p95, p99)
- Batch statistics
- Performance bottlenecks
- Spike and plateau detections
- CDC pipeline status
- Source/target health metrics
"""

# System prompt for LOG_PLUS_KB mode - uses both log data and KB articles
SYSTEM_PROMPT_LOG_PLUS_KB = """You are an expert Qlik Replicate support engineer assistant.
You help users troubleshoot their replication tasks by analyzing log data and referencing knowledge base articles.

## Your Role
- Analyze log data to understand the current state and issues
- Use KB articles to explain errors, root causes, and solutions
- Provide actionable recommendations based on both sources
- Connect log observations to documented solutions

## Response Guidelines
1. First, acknowledge what the log data shows
2. Then, explain the meaning using KB article knowledge
3. Provide specific, actionable recommendations
4. Reference KB articles when they provide relevant guidance
5. Format responses in clean Markdown
6. Keep responses under 300 words unless more detail is needed

## Priority Order
1. Log data facts and metrics (primary source)
2. KB article explanations and solutions (supporting context)
3. General Qlik Replicate knowledge (when KB doesn't cover it)

## When Referencing KB Articles
- Mention the article title if it's directly relevant
- Summarize the key points rather than quoting extensively
- Focus on actionable guidance from the articles
"""


# ============================================================
# FOCUS MODE DEFINITIONS
# ============================================================
# Used when the log has no errors or performance data and the
# user selects what kind of analysis they want.

FOCUS_MODES: Dict[str, Dict[str, str]] = {
    "general_review": {
        "title": "General Review",
        "system_addendum": (
            "The user requested a **General Review**. Focus on: task health status, "
            "driver and version information, endpoint configuration, CDC pipeline state, "
            "source/target connectivity, and any informational observations. "
            "Do NOT fabricate performance bottlenecks or error patterns that are not in the data."
        ),
        "analysis_request": (
            "1. **Task Configuration**: Source/target endpoints, driver versions, task type, "
            "parallel apply threads, bulk settings.\n"
            "2. **Health Status**: Overall CDC pipeline state, connectivity, reconnections.\n"
            "3. **Observations**: Any notable patterns — DDL propagation, table counts, "
            "supplemental logging status, task duration.\n"
            "4. **Recommendations**: Configuration improvements, version upgrade suggestions, "
            "best-practice alignment.\n"
            "5. **Health Score**: Healthy / Warning / Critical with justification."
        ),
    },
    "performance": {
        "title": "Performance Analysis",
        "system_addendum": (
            "The user requested a **Performance Analysis** even though structured "
            "latency telemetry may be limited. Focus on: batch processing patterns, "
            "throughput hints (record counts, apply times), table-level metrics, "
            "sorter behaviour, and any indirect performance signals in the log. "
            "Clearly state when conclusions are inferred rather than measured."
        ),
        "analysis_request": (
            "1. **Throughput Assessment**: Records processed, batch sizes, apply times, "
            "table-level operation counts.\n"
            "2. **Batch Efficiency**: Closure reasons, single-record batch percentage, "
            "timeout tuning opportunities.\n"
            "3. **Resource Signals**: Sorter memory, parallel threads, disk swap events.\n"
            "4. **Tuning Recommendations**: Ranked by expected impact.\n"
            "5. **Health Score**: Healthy / Warning / Critical."
        ),
    },
    "errors": {
        "title": "Error Analysis",
        "system_addendum": (
            "The user requested an **Error Analysis**. Even if few or no errors were "
            "detected in parsing, look for: warning-level messages, informational "
            "alerts, connectivity hiccups, DDL issues, or any symptoms that could "
            "indicate latent problems. Be explicit if the log is genuinely clean."
        ),
        "analysis_request": (
            "1. **Error/Warning Inventory**: List any errors, warnings, or informational "
            "alerts found — even minor ones. If none exist, state that clearly.\n"
            "2. **Symptom Interpretation**: For each finding, explain probable cause.\n"
            "3. **Latent Risks**: Potential issues that could emerge (e.g., no supplemental "
            "logging, missing PK, large transactions without sorter storage).\n"
            "4. **Preventive Actions**: Recommendations to avoid future errors.\n"
            "5. **Health Score**: Healthy / Warning / Critical."
        ),
    },
    "configuration": {
        "title": "Configuration Review",
        "system_addendum": (
            "The user requested a **Configuration Review**. Focus entirely on: "
            "endpoint settings, driver versions, task parameters (parallel apply, "
            "batch timeout, bulk mode), replication mode (FL/CDC/FL+CDC), "
            "and alignment with Qlik Replicate best practices."
        ),
        "analysis_request": (
            "1. **Endpoint Configuration**: Source and target types, versions, "
            "connection parameters.\n"
            "2. **Task Settings**: Batch optimizations, parallel apply, error handling "
            "policy, DDL handling, LOB settings.\n"
            "3. **Best-Practice Alignment**: Compare settings against recommended "
            "defaults for the detected endpoint combination.\n"
            "4. **Optimization Opportunities**: Specific settings to change and why.\n"
            "5. **Health Score**: Healthy / Warning / Critical."
        ),
    },
}


# ---------------------------------------------------------------------------
# Phase 3: Domain-specific tuning hints injected when patterns match
# ---------------------------------------------------------------------------

_TUNING_CHEAT_SHEET_ODBC_TIMEOUT = """## Tuning Reference — ODBC / Source Timeout Parameters

When recommending timeout or connectivity adjustments, use these **exact parameter names**:

| Parameter | Where to set | Default | Notes |
|---|---|---|---|
| `executeTimeout` | Source endpoint → Advanced → Internal parameters | 60 s | Governs individual SQL statement execution. Increase for slow Full Load SELECTs. |
| `cdcTimeout` | Source endpoint → Advanced → Internal parameters | 600 s | Governs CDC log-read operations. Increase if source log reader times out. |
| `connectTimeout` | Source endpoint → Advanced → Internal parameters | 60 s | TCP connection establishment timeout. |
| `fetchTimeout` | Source endpoint → Advanced → Internal parameters | 60 s | Row-fetch timeout during Full Load. |
| `commandTimeout` | ODBC DSN / driver level | varies | Driver-level timeout; separate from Replicate internal params. |

**Typical remediation**: Double `executeTimeout` (e.g. 120→240→600) iteratively; verify source DB is not holding locks during Full Load windows.
"""

_TUNING_TRIGGERS_ODBC_TIMEOUT = re.compile(
    r"(?:timed?\s*out|timeout|HYT00|30149|executeTimeout|cdcTimeout|SOURCE_UNLOAD.*error)",
    re.IGNORECASE,
)


_NORMALIZE_PATTERNS = [
    re.compile(r"\bLINE\s+\d+\b", re.IGNORECASE),
    re.compile(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}"),
    re.compile(r"\bst_\d+_\w+"),
    re.compile(r"\b(subtask|line)\s+\d+", re.IGNORECASE),
]

_CODE_EXTRACT = re.compile(r"\[\d{5,8}\]")


def _build_error_aggregates(error_contexts: List[str]) -> str:
    """Build a deterministic per-pattern aggregation block from error excerpts.

    Groups errors by normalized message pattern and produces a concise summary
    the model can cite directly.
    """
    if not error_contexts:
        return ""

    from collections import Counter, defaultdict

    pattern_lines: Dict[str, List[int]] = defaultdict(list)
    pattern_example: Dict[str, str] = {}
    code_counter: Counter = Counter()

    for block in error_contexts:
        if not block or not isinstance(block, str):
            continue
        lines = block.strip().split("\n")
        line_num = None
        component = ""
        body = block

        if lines and lines[0].startswith("LINE "):
            header = lines[0]
            parts = header.split("|")
            try:
                line_num = int(parts[0].replace("LINE", "").strip())
            except (ValueError, IndexError):
                pass
            if len(parts) >= 3:
                component = parts[2].strip()
            body = "\n".join(lines[1:]) if len(lines) > 1 else header

        normalized = body
        for pat in _NORMALIZE_PATTERNS:
            normalized = pat.sub("", normalized)
        normalized = " ".join(normalized.split())[:160]

        if not normalized:
            normalized = body[:120]

        pattern_lines[normalized].append(line_num if line_num is not None else 0)
        if normalized not in pattern_example:
            pattern_example[normalized] = block.strip()[:300]

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


def _build_context_inventory(
    summary_data: Dict[str, Any],
    error_contexts: List[str],
    anomaly_contexts: List[str],
    file_info: Optional[Dict[str, Any]],
    release_notes_context: Optional[List[Dict[str, Any]]],
    kb_context: Optional[List[Dict[str, Any]]],
) -> str:
    """Produce a short inventory so the model knows what data it has."""
    items: List[str] = []

    has_perf = _signals_structured_performance_telemetry(summary_data)
    lp = summary_data.get("latency_profile") or {}
    dp = lp.get("data_points", 0) or 0

    if has_perf:
        parts: List[str] = []
        if dp > 0:
            parts.append(f"{dp:,} latency samples")
        bp = summary_data.get("batch_profile") or {}
        if (bp.get("total_batches") or 0) > 0:
            parts.append(f"{bp['total_batches']:,} batches")
        if _bottleneck_is_actionable(summary_data):
            bn = summary_data.get("bottleneck", {}).get("primary", "")
            parts.append(f"bottleneck: {bn}")
        if summary_data.get("pain_tables"):
            parts.append(f"{len(summary_data['pain_tables'])} pain tables")
        items.append(f"- Performance telemetry: {', '.join(parts) if parts else 'present'}")
    else:
        items.append("- Performance telemetry: **Not available** — no latency/throughput data captured")

    err_total = summary_data.get("error_summary", {}).get("total", 0) or 0
    if error_contexts:
        items.append(
            f"- Error/warning excerpts: {len(error_contexts)} excerpts with line references"
            + (f" (from {err_total:,} total)" if err_total > len(error_contexts) else "")
        )
    elif err_total > 0:
        items.append(f"- Error summary: {err_total:,} errors counted (no detailed excerpts available)")
    else:
        items.append("- Errors: None detected")

    cp = summary_data.get("cdc_pipeline")
    if cp:
        status = cp.get("health_status", "unknown").upper()
        extras: List[str] = []
        if cp.get("memory_warnings", 0) > 0:
            extras.append(f"{cp['memory_warnings']} memory warnings")
        if cp.get("disconnections", 0) > 0:
            extras.append(f"{cp['disconnections']} disconnections")
        items.append(f"- CDC pipeline: {status}" + (f" ({', '.join(extras)})" if extras else ""))

    sa = summary_data.get("source_analysis")
    if sa:
        items.append(f"- Source health: {sa.get('health_status', 'unknown').upper()}")

    ora = summary_data.get("oracle_redo_read_analysis") or {}
    olp = summary_data.get("oracle_redo_log_processing") or {}
    if ora.get("has_red_flags"):
        items.append("- Oracle redo: High-variance reads detected (red flag)")
    elif (ora.get("total_events") or 0) > 0 or (olp.get("session_count") or 0) > 0:
        items.append("- Oracle redo: Data available")

    if anomaly_contexts:
        items.append(f"- Anomalies: {len(anomaly_contexts)} detected")

    if kb_context:
        items.append(f"- KB articles: {len(kb_context)} relevant articles included below")
    if release_notes_context:
        items.append(f"- Release notes: {len(release_notes_context)} correlation entries included below")

    return "## Data Available for This Analysis\n" + "\n".join(items) + "\n"


def build_analysis_prompt(
    summary_data: Dict[str, Any],
    error_contexts: List[str],
    anomaly_contexts: List[str],
    file_info: Optional[Dict[str, Any]] = None,
    release_notes_context: Optional[List[Dict[str, Any]]] = None,
    kb_context: Optional[List[Dict[str, Any]]] = None,
    web_search: bool = False,
    sanitize_log_payload: bool = True,
    compact: bool = False,
    focus_mode: Optional[str] = None,
    tuning_reference: Optional[str] = None,
) -> str:
    """
    Build the user prompt for log analysis.
    
    Args:
        summary_data: Performance cockpit and analysis data
        error_contexts: List of error messages with context
        anomaly_contexts: List of detected anomalies
        file_info: Optional file metadata (name, size, line count)
        sanitize_log_payload: When True, redact PII from log-derived fields before formatting
        tuning_reference: Optional pre-built endpoint-specific tuning parameter reference
    
    Returns:
        Formatted prompt string
    """
    if sanitize_log_payload:
        summary_data = sanitize_dict(summary_data)
        error_contexts = sanitize_list(error_contexts)
        anomaly_contexts = sanitize_list(anomaly_contexts)
        if file_info:
            file_info = sanitize_dict(file_info)

    # Dynamic caps: local models get moderately trimmed excerpts to keep
    # the prompt focused without losing important detail; cloud models
    # get the full set.
    if compact:
        _max_errors = 14
        _max_err_chars = 2200
        _max_anomalies = 3
        _max_anom_chars = 700
        _max_kb = 4
        _max_rn = 5
    else:
        _max_errors = 22
        _max_err_chars = 2600
        _max_anomalies = 4
        _max_anom_chars = 900
        _max_kb = 5
        _max_rn = 6

    sections = []

    # Context inventory — tells the model exactly what data is present
    sections.append(_build_context_inventory(
        summary_data, error_contexts, anomaly_contexts,
        file_info, release_notes_context, kb_context,
    ))

    # Deterministic aggregates — give local models grounded counts to cite
    if compact and error_contexts:
        agg_block = _build_error_aggregates(error_contexts)
        if agg_block:
            sections.append(agg_block)

    # Domain-specific tuning hints — prefer dynamic ar_props lookup, fallback to static
    if error_contexts:
        combined_text = " ".join(error_contexts[:20])
        if _TUNING_TRIGGERS_ODBC_TIMEOUT.search(combined_text):
            if tuning_reference:
                sections.append(tuning_reference)
            else:
                sections.append(_TUNING_CHEAT_SHEET_ODBC_TIMEOUT)

    # === CRITICAL ISSUES FIRST (if any) ===
    # Highlight critical issues at the top for immediate attention
    has_critical = False
    critical_section = ["## ⚠️ Critical Issues Detected\n"]
    
    if summary_data.get("error_summary", {}).get("total", 0) > 100:
        critical_section.append(f"- **High error count**: {summary_data['error_summary']['total']:,} errors logged")
        has_critical = True
    
    if summary_data.get("cdc_pipeline", {}).get("health_status", "").lower() == "critical":
        critical_section.append("- **CDC pipeline critical**: Memory warnings or disconnections detected")
        has_critical = True
    
    if summary_data.get("pain_tables") and len(summary_data["pain_tables"]) > 0:
        worst_table = summary_data["pain_tables"][0]
        if worst_table.get("pain_score", 0) > 50:
            critical_section.append(f"- **Problematic table**: {worst_table.get('table_name', 'Unknown')} showing severe issues")
            has_critical = True
    
    ora = summary_data.get("oracle_redo_read_analysis") or {}
    if ora.get("has_red_flags"):
        critical_section.append(
            "- **Oracle archived redo read variance**: Similar redo reads (>200 ms) differ by ≥2× in duration — review source I/O and storage"
        )
        has_critical = True
    
    if has_critical:
        sections.append("\n".join(critical_section) + "\n")
    
    # File info header (compact)
    if file_info:
        filename = file_info.get('filename', 'Unknown')
        if '\\' in filename:
            filename = filename.split('\\')[-1]
        if '/' in filename:
            filename = filename.split('/')[-1]
        
        sections.append(f"""## Log Overview
File: {filename} | Size: {file_info.get('size_bytes', 0):,} bytes | Lines: {file_info.get('line_count', 0):,}
""")
    
    structured_perf = _signals_structured_performance_telemetry(summary_data)

    # When a non-performance focus mode is active AND there's no telemetry,
    # omit the entire Performance section — its presence misleads the model
    # into discussing performance even when the user asked for something else.
    _include_perf_section = (
        focus_mode in (None, "performance")
        or structured_perf
    )

    if _include_perf_section:
        sections.append("## Performance & diagnostics")

    if not structured_perf and _include_perf_section:
        sections.append(
            "### Telemetry availability\n\n"
            "This ingestion did **not** produce substantive structured performance aggregates "
            "(no sampled latency profile, spikes/plateaus, Oracle redo summaries, batches, "
            "or pain-table metrics).\n\n"
            "**Interpretation mandate:** Bottleneck / latency / throughput RCA is **usually not warranted** unless "
            "the log excerpts above show clear slow-path evidence. Focus on **errors, warnings, and connectivity** "
            "unless the user enabled Performance tracing or richer task diagnostic levels.\n"
        )
    elif structured_perf and _include_perf_section:
        if "latency_profile" in summary_data:
            lp = summary_data["latency_profile"]
            if lp.get("data_points", 0) > 0:
                sections.append(f"""
### Latency ({lp.get('data_points', 0):,} samples)
- **Source**: avg {lp.get('source', {}).get('avg', 0):.2f}s, p95 {lp.get('source', {}).get('p95', 0):.2f}s, max {lp.get('source', {}).get('max', 0):.2f}s
- **Handling**: avg {lp.get('handling', {}).get('avg', 0):.2f}s, p95 {lp.get('handling', {}).get('p95', 0):.2f}s, max {lp.get('handling', {}).get('max', 0):.2f}s
- **Target**: avg {lp.get('target', {}).get('avg', 0):.2f}s, p95 {lp.get('target', {}).get('p95', 0):.2f}s, max {lp.get('target', {}).get('max', 0):.2f}s
""")

        if _bottleneck_is_actionable(summary_data) and "bottleneck" in summary_data:
            bn = summary_data["bottleneck"]
            primary = bn.get("primary", "Unknown")
            sections.append(f"""
### Primary bottleneck (from latency mix): {str(primary).upper()}
""")
            if primary == "source":
                sections.append(
                    "The source side dominated end-to-end latency in sampled windows. "
                    "Consider source I/O, log read configuration, and resource contention.\n"
                )
            elif primary == "target":
                sections.append(
                    "The target side dominated end-to-end latency in sampled windows. "
                    "Consider apply tuning, indexes, and target resource headroom.\n"
                )
            elif primary == "handling":
                sections.append(
                    "Internal handling dominated sampled latency. "
                    "Consider memory, parallel apply threads, and transformation cost.\n"
                )
        elif _latency_samples_present(summary_data) and "bottleneck" in summary_data:
            sections.append(
                f"\n### Bottleneck signal\n"
                f"Classifier: **{summary_data['bottleneck'].get('primary', 'unknown')}** "
                f"(insufficient confidence for deep tuning — corroborate with task statistics).\n"
            )

        if "spikes" in summary_data:
            spikes = summary_data["spikes"]
            if spikes.get("count", 0) > 0:
                sections.append(
                    f"\n### Latency spikes\nDetected **{spikes['count']} spikes**. Top spikes:"
                )
                for spike in spikes.get("items", [])[:5]:
                    sections.append(
                        f"- Line {spike.get('line_number', '?')}: {spike.get('value', 0):.1f}s "
                        f"({spike.get('multiplier', 0):.1f}x baseline, driver: {spike.get('driver', '?')})"
                    )

        if "plateaus" in summary_data:
            plateaus = summary_data["plateaus"]
            if plateaus.get("count", 0) > 0:
                sections.append(
                    f"\n### Latency plateaus\nDetected **{plateaus['count']} sustained high-latency periods**:"
                )
                for plateau in plateaus.get("items", [])[:3]:
                    sections.append(
                        f"- Lines {plateau.get('start_line', '?')}-{plateau.get('end_line', '?')}: "
                        f"avg {plateau.get('avg_latency', 0):.1f}s for {plateau.get('duration_points', 0)} readings"
                    )

        ora_pf = summary_data.get("oracle_redo_read_analysis") or {}
        olp_pf = summary_data.get("oracle_redo_log_processing") or {}
        oracle_findings: List[str] = []

        if ora_pf.get("has_red_flags"):
            n_groups = len(ora_pf.get("high_variance_groups", []))
            oracle_findings.append(
                f"Archived redo block reads show **high variance** — {n_groups} group(s) of "
                f"similar-sized reads (same thread & code path) differ by ≥{ora_pf.get('multiplier_threshold', 2):.0f}× "
                f"in duration. This points to **intermittent storage or I/O contention** on the source host."
            )

        if olp_pf.get("session_count", 0) > 0:
            st = olp_pf.get("duration_seconds_stats") or {}
            mn, mx = st.get("min"), st.get("max")
            avg, p95 = st.get("avg"), st.get("p95")
            typical = p95 if (p95 is not None and p95 > 0) else avg
            notable_spread = False
            if mx is not None and typical not in (None, 0) and mx >= float(typical) * 2.5:
                notable_spread = True
            if mn not in (None, 0) and mx is not None and mx / float(mn) >= 5:
                notable_spread = True
            if notable_spread:
                oracle_findings.append(
                    f"Redo log hold times (open→close) **fluctuate sharply**: "
                    f"min {mn}s → max {mx}s (typical ~{typical}s). "
                    f"Large swings usually indicate occasional storage pressure or archivelog "
                    f"contention rather than a steady bottleneck."
                )

        if oracle_findings:
            sections.append("\n### Oracle source — notable findings")
            for finding in oracle_findings:
                sections.append(f"- {finding}")
            sections.append(
                "\n> Mention these naturally in the Executive Summary / performance discussion — "
                "do NOT enumerate individual redo log sessions, file paths, or per-read samples."
            )

        if "batch_profile" in summary_data:
            bp = summary_data["batch_profile"]
            sections.append(
                f"\n### Batch processing ({bp.get('total_batches', 0):,} batches)\n"
            )
            if "size_stats" in bp:
                ss = bp["size_stats"]
                single_record_pct = ss.get("single_record_pct", 0)
                avg_size = ss.get("avg", 0)
                if single_record_pct > 20 or avg_size < 10:
                    sections.append(
                        f"⚠️ **Batch efficiency issue**: avg size {avg_size:.0f}, "
                        f"{single_record_pct:.1f}% single-record batches\n"
                    )
                else:
                    sections.append(
                        f"✓ Batch sizes: avg {avg_size:.0f}, max {ss.get('max', 0):,}\n"
                    )
            if bp.get("closure_reasons"):
                top_reasons = sorted(
                    bp["closure_reasons"].items(), key=lambda x: x[1], reverse=True
                )[:3]
                sections.append(
                    "**Top closure reasons**: "
                    + ", ".join([f"{r}: {c}" for r, c in top_reasons])
                    + "\n"
                )

        if summary_data.get("batch_issues"):
            critical_issues = [
                i
                for i in summary_data["batch_issues"]
                if i.get("severity") in ["warning", "critical"]
            ]
            if critical_issues:
                sections.append("\n**Batch issues:**")
                for issue in critical_issues[:3]:
                    sections.append(
                        f"- {issue.get('title', '')}: {issue.get('message', '')[:150]}"
                    )

        if summary_data.get("pain_tables"):
            sections.append("\n### Tables with performance hotspots")
            for table in summary_data["pain_tables"][:5]:
                sections.append(
                    f"- **{table.get('table_name', 'Unknown')}**: "
                    f"pain_score={table.get('pain_score', 0):.0f}, "
                    f"apply_time={table.get('total_apply_time', 0):.1f}s, "
                    f"one-by-one={table.get('one_by_one_count', 0)}"
                )

    if "cdc_pipeline" in summary_data:
        cp = summary_data["cdc_pipeline"]
        sections.append(f"""
### CDC pipeline health
- **Status**: {cp.get('health_status', 'unknown').upper()}
- Memory warnings: {cp.get('memory_warnings', 0)}
- Disconnections: {cp.get('disconnections', 0)}
- Reconnections: {cp.get('reconnections', 0)}
""")

    if "source_analysis" in summary_data:
        sa = summary_data["source_analysis"]
        sections.append(f"""
### Source health
- **Status**: {sa.get('health_status', 'unknown').upper()}
- Reconnects: {sa.get('total_reconnects', 0)}
- Network issues: {sa.get('network_issues', 0)}
- Contention issues: {sa.get('contention_issues', 0)}
""")
        if sa.get("investigation_hints"):
            sections.append(
                "Investigation hints: " + "; ".join(sa["investigation_hints"])
            )
    
    # Error Summary - prioritize critical information
    if "error_summary" in summary_data:
        es = summary_data["error_summary"]
        error_count = es.get('total', 0)
        
        if error_count > 0:
            severity_indicator = "⚠️" if error_count > 100 else "ℹ️"
            sections.append(f"""
### {severity_indicator} Error Summary
- **Total**: {error_count:,} errors
""")
            if es.get('by_component'):
                top_components = sorted(es['by_component'].items(), key=lambda x: x[1], reverse=True)[:5]
                comp_parts = []
                for comp, count in top_components:
                    ctx = COMPONENT_CONTEXT.get(comp, "")
                    label = f"**{comp}** ({count})"
                    if ctx:
                        label += f" — {ctx}"
                    comp_parts.append(label)
                sections.append("- " + "\n- ".join(comp_parts) + "\n")
    
    # Error Correlation - only if significant
    if structured_perf and summary_data.get("error_correlation", {}).get("total_correlated_errors", 0) > 10:
        ec = summary_data["error_correlation"]
        sections.append(f"""
### Error-latency correlation
{ec.get('total_correlated_errors', 0)} errors occurred during high latency periods, suggesting performance-related coupling.
""")
    
    # Existing Recommendations from analysis
    if "recommendations" in summary_data and summary_data["recommendations"]:
        sections.append("""
### Pre-computed Recommendations""")
        for rec in summary_data["recommendations"]:
            sections.append(f"- [{rec.get('priority', 'medium').upper()}] **{rec.get('title', '')}** ({rec.get('area', '')})")
            sections.append(f"  {rec.get('description', '')}")
            if rec.get('actions'):
                for action in rec['actions'][:2]:
                    sections.append(f"  - {action}")
    
    err_total = summary_data.get("error_summary", {}).get("total", 0) or 0

    lookup_passages = [
        p for p in (error_contexts or []) if isinstance(p, str) and p.strip()
    ]
    code_hits = extract_error_codes_for_prompt(lookup_passages)
    if code_hits:
        sections.append(
            "\n### Candidate codes / tokens detected in excerpts\n"
            + "\n".join(f"- `{c}`" for c in code_hits)
            + "\nTry to map these to vendor messages, RECOB fixes, or KB articles when possible.\n"
        )

    # Error/warning excerpts — structured DB rows + retrieval
    if error_contexts:
        # In compact mode, annotate which components appear so the model
        # has context even though the full reference table was omitted.
        comp_annotation = ""
        if compact:
            referenced = {
                c for ctx in error_contexts[:_max_errors]
                for c in COMPONENT_CONTEXT if c in ctx
            }
            if referenced:
                comp_annotation = (
                    "\nComponents referenced: "
                    + ", ".join(
                        f"**{c}** ({COMPONENT_CONTEXT[c]})"
                        for c in sorted(referenced)
                    )
                    + "\n"
                )

        sections.append(
            "\n## Log-derived error & warning excerpts\n"
            "These snippets are taken from parsed log lines (and optional semantic retrieval). "
            "Reference **LINE** numbers in your write-up.\n"
            + comp_annotation
        )
        for i, ctx in enumerate(error_contexts[:_max_errors], 1):
            clean_ctx = ctx[:_max_err_chars] if len(ctx) > _max_err_chars else ctx
            sections.append(f"**Excerpt {i}:**\n```\n{clean_ctx}\n```\n")

    if anomaly_contexts:
        _anom_title = (
            "## Performance anomalies (latency-derived context)"
            if structured_perf
            else "## Retrieved anomaly / diagnostic notes"
        )
        sections.append(f"\n{_anom_title}\n")
        for i, ctx in enumerate(anomaly_contexts[:_max_anomalies], 1):
            clean_ctx = ctx[:_max_anom_chars] if len(ctx) > _max_anom_chars else ctx
            sections.append(f"**Note {i}:**\n```\n{clean_ctx}\n```\n")
    
    # Release notes correlation (omit URLs when web_search is enabled to avoid grounding conflicts)
    if release_notes_context:
        sections.append("""
## Release Notes Correlation
The following release note entries may be relevant to the issues detected:
""")
        for i, rn in enumerate(release_notes_context[:_max_rn], 1):
            title = rn.get("title", "Unknown")
            version = rn.get("version", "")
            fix_id = rn.get("fix_id", "")
            snippet = rn.get("content", "")[:350]
            version_label = f" ({version})" if version else ""
            fix_label = f" [{fix_id}]" if fix_id else ""
            sections.append(f"{i}. **{title}{version_label}{fix_label}**: {snippet}\n")

    # KB articles (titles + short summaries only; no URLs to avoid grounding conflicts)
    if kb_context:
        sections.append("""
## Relevant Knowledge Base Articles
The following KB articles from the Qlik support knowledge base may help:
""")
        for i, kb in enumerate(kb_context[:_max_kb], 1):
            title = kb.get("title", "Unknown")
            snippet = kb.get("content", "")[:400]
            sections.append(f"{i}. **{title}**: {snippet}\n")

    # Final instruction — use focus-mode template when set, otherwise default
    focus_def = FOCUS_MODES.get(focus_mode) if focus_mode else None

    if focus_def:
        # Focus-mode: user explicitly chose what they want
        sections.append(
            f"\n---\n\n## Analysis Request — {focus_def['title']}\n\n"
            f"{focus_def['system_addendum']}\n\n"
            f"{focus_def['analysis_request']}\n"
        )
    else:
        # Default dynamic analysis request
        extra_items = []
        if release_notes_context:
            extra_items.append("**Release Notes Correlation**: Identify which issues may already be fixed in a newer release, referencing fix IDs (RECOB-XXXX) and versions")
        if kb_context:
            extra_items.append("**Relevant KB Articles**: Reference specific KB articles that provide guidance for the issues found")

        analysis_items: List[str] = [
            "1. **Health assessment**: Overall task health (Healthy/Warning/Critical) with justification.",
            "2. **Root cause analysis**: Tie major issues to **evidence** (metrics and **LINE** references from excerpts). "
            "Do not invent latency bottlenecks when telemetry is absent unless the log text itself shows slow operations.",
        ]
        if err_total > 0 or error_contexts:
            err_item = (
                "3. **Error & warning interpretation**: Group related excerpts, cite **LINE** numbers and components, "
                "explain impact, and propose verification. **Do not** say the full log is missing when excerpts are provided above."
            )
            if web_search:
                err_item += (
                    " Use **web search** for unfamiliar SQLSTATE / ORA-xxxx / ERR… / internal codes."
                )
            analysis_items.extend(
                [
                    err_item,
                    "4. **Priority actions**: Top 3-5 remediation steps ranked by impact.",
                    "5. **Risk assessment**: What degrades or fails if issues persist?",
                ]
            )
            next_idx = 6
        else:
            analysis_items.extend(
                [
                    "3. **Priority actions**: Top 3-5 remediation steps ranked by impact.",
                    "4. **Risk assessment**: What degrades or fails if issues persist?",
                ]
            )
            next_idx = 5

        if extra_items:
            for j, item in enumerate(extra_items):
                analysis_items.append(f"{next_idx + j}. {item}")

        base_focus = "Practical guidance for a DBA or Qlik support engineer."
        if err_total > 0 or error_contexts:
            base_focus += " Prioritize explaining surfaced log lines before generic advice."

        perf_focus_clause = ""
        if structured_perf:
            perf_focus_clause = " Reference throughput/latency statistics when they support a conclusion."
        else:
            perf_focus_clause = (
                " Structured latency/throughput telemetry was limited — keep performance tuning advice cautious."
            )

        sections.append(
            "\n---\n\n## Analysis Request\n\n"
            + "\n".join(analysis_items)
            + f"\n\n**Focus**: {base_focus}{perf_focus_clause}\n"
        )
    
    return "\n".join(sections)


def build_quick_summary_prompt(
    summary_data: Dict[str, Any],
    sanitize_log_payload: bool = True,
) -> str:
    """
    Build a prompt for a quick summary (fewer tokens, faster response).
    
    Args:
        summary_data: Performance cockpit data
        sanitize_log_payload: When True, redact before serializing metrics
    
    Returns:
        Formatted prompt string
    """
    if sanitize_log_payload:
        summary_data = sanitize_dict(summary_data)
    
    # Extract key metrics only (these are numeric/safe values)
    metrics = {
        "bottleneck": summary_data.get("bottleneck", {}).get("primary", "unknown"),
        "error_count": summary_data.get("error_summary", {}).get("total", 0),
        "spike_count": summary_data.get("spikes", {}).get("count", 0),
        "plateau_count": summary_data.get("plateaus", {}).get("count", 0),
        "cdc_health": summary_data.get("cdc_pipeline", {}).get("health_status", "unknown"),
        "source_health": summary_data.get("source_analysis", {}).get("health_status", "unknown"),
    }
    ora_q = summary_data.get("oracle_redo_read_analysis") or {}
    if ora_q.get("total_events_over_floor", 0) or ora_q.get("has_red_flags"):
        metrics["oracle_redo_reads_over_200ms"] = ora_q.get("total_events_over_floor", 0)
        metrics["oracle_redo_high_variance"] = ora_q.get("has_red_flags", False)
    olp_q = summary_data.get("oracle_redo_log_processing") or {}
    if olp_q.get("session_count", 0):
        metrics["oracle_redo_log_sessions"] = olp_q.get("session_count", 0)
        stq = olp_q.get("duration_seconds_stats") or {}
        if stq:
            metrics["oracle_redo_log_avg_seconds"] = stq.get("avg", 0)
            metrics["oracle_redo_log_max_seconds"] = stq.get("max", 0)
    
    # Latency stats
    lp = summary_data.get("latency_profile", {})
    if lp:
        metrics["avg_source_latency"] = lp.get("source", {}).get("avg", 0)
        metrics["avg_handling_latency"] = lp.get("handling", {}).get("avg", 0)
        metrics["max_target_latency"] = lp.get("target", {}).get("max", 0)
    
    return f"""Analyze this Qlik Replicate log summary and provide a brief assessment:

{json.dumps(metrics, indent=2)}

Provide a 3-5 sentence summary of:
1. Overall health status (Healthy/Warning/Critical)
2. Main issue if any
3. Top recommendation
"""


QUICK_SUMMARY_SYSTEM = """You are a log analysis assistant. Provide concise, actionable summaries.
Keep responses under 200 words. Use markdown formatting."""


def get_messages_for_analysis(
    summary_data: Dict[str, Any],
    error_contexts: List[str],
    anomaly_contexts: List[str],
    file_info: Optional[Dict[str, Any]] = None,
    quick: bool = False,
    web_search: bool = False,
    release_notes_context: Optional[List[Dict[str, Any]]] = None,
    kb_context: Optional[List[Dict[str, Any]]] = None,
    sanitize_log_payload: bool = True,
    compact: bool = False,
    focus_mode: Optional[str] = None,
    tuning_reference: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    Build the complete messages list for the LLM.
    
    Args:
        summary_data: Performance cockpit data
        error_contexts: Error context strings from RAG
        anomaly_contexts: Anomaly context strings from RAG
        file_info: Optional file metadata
        quick: If True, use quick summary mode
        web_search: If True, use system prompt with web search instructions
        release_notes_context: Release note entries from vector store / Tavily
        kb_context: KB articles from vector store
        sanitize_log_payload: When True, redact PII from log-derived fields
        compact: When True, use condensed prompts for local / small models
        focus_mode: Optional user-chosen analysis focus (general_review, performance, errors, configuration)
        tuning_reference: Optional endpoint-specific parameter reference from ar_props
    
    Returns:
        List of message dicts ready for the LLM API
    """
    if quick:
        return [
            {"role": "system", "content": QUICK_SUMMARY_SYSTEM},
            {
                "role": "user",
                "content": build_quick_summary_prompt(
                    summary_data, sanitize_log_payload=sanitize_log_payload
                ),
            },
        ]
    
    user_prompt = build_analysis_prompt(
        summary_data=summary_data,
        error_contexts=error_contexts,
        anomaly_contexts=anomaly_contexts,
        file_info=file_info,
        release_notes_context=release_notes_context,
        kb_context=kb_context,
        web_search=web_search,
        sanitize_log_payload=sanitize_log_payload,
        compact=compact,
        focus_mode=focus_mode,
        tuning_reference=tuning_reference,
    )
    
    # Select system prompt: compact (local) → short; web_search → augmented; default → full
    if compact and not web_search:
        system_prompt = SYSTEM_PROMPT_LOCAL
    elif web_search:
        system_prompt = SYSTEM_PROMPT_WITH_WEB_SEARCH
    else:
        system_prompt = SYSTEM_PROMPT
    
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]


def count_prompt_tokens(messages: List[Dict[str, str]]) -> int:
    """
    Estimate the number of tokens in the messages.
    
    This is a rough estimate; actual count may vary by model.
    Uses ~4 characters per token as approximation.
    
    Args:
        messages: List of message dicts
    
    Returns:
        Estimated token count
    """
    total_chars = sum(len(m.get("content", "")) for m in messages)
    # Add overhead for message structure
    overhead = len(messages) * 10
    return (total_chars // 4) + overhead

