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
from backend.llm.evidence_compiler import (
    EvidenceBudgets,
    BudgetedSection,
    build_authoritative_facts,
    build_error_aggregates,
    build_focus_payload_plan,
    enforce_budgets,
    format_task_config,
    format_warning_tail,
    select_representative_excerpts,
)

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

# Unified audit report contract (cloud + local share this structure).
AUDIT_REPORT_STRUCTURE = """
## Report Structure
Use exactly these 6 sections as Markdown `##` headers (NOT numbered lists like `1.` or `2.`):

## Executive Summary & Health
Max 3 sentences: **X/5** Health Score (1=Critical, 5=Healthy), severity, primary root cause.

## Key Findings
Bullets; lead each with occurrence counts from Log Aggregates when provided.

## Performance & Full Load Analysis
Latency/batch/full-load facts only when telemetry is present; otherwise one sentence on missing diagnostics.

## Issues & Recommendations
For EACH major issue:
- **Evidence**: Quote LINE numbers or metrics from the evidence package.
- **Interpretation**: What it means and impact.
- **Recommendations**: Concrete steps using Tuning Reference parameter names when provided.

## Error & Component Mapping
Markdown table: error code | component | LINE(s).

## Risk Assessment
Max 2 sentences on what degrades or fails if issues persist.

Do not add, merge, or rename sections. If Release Notes or KB sections appear in the evidence package, weave fix IDs (RECOB-XXXX) or article titles into Issues — do not add extra sections.
"""

AUDIT_OUTPUT_FORMAT = """
## Output Format
- Start each section with a `## Section Name` header line — never use `1.` / `2.` numbering as section titles.
- Complete every section; do not truncate mid-sentence or end with stray characters (`/`, `...`).
- Use plain text for numbers (e.g. `60 errors`, `714.33s`). No LaTeX.
"""

AUDIT_DIRECTIVES = """
## Evidence Rules
- Counts and metrics in the evidence package are pre-computed in Python — **report them verbatim; do not recalculate**.
- Quote **LINE** numbers from provided excerpts only.
- Do NOT invent charts, graphs, or visuals unless the user message says a latency chart is attached.
- Do NOT invent parameter names outside the Tuning Reference block; if none is provided, say so.
- Do NOT give generic database administration advice unrelated to quoted log lines.
- Do NOT fabricate URLs. Reference KB/release-note titles from the evidence package only.
"""

EVIDENCE_PACKAGE_PREAMBLE = (
    "Here is the deterministic evidence package for this log. "
    "Produce the report according to the system contract. "
    "Do not rediscover or contradict pre-computed facts.\n"
)

# System prompt for log analysis
SYSTEM_PROMPT = """You are an expert log analyst specializing in Qlik Replicate (formerly Attunity Replicate) data replication logs. Your role is to interpret the evidence package and provide clear, actionable insights.

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

""" + AUDIT_DIRECTIVES + AUDIT_OUTPUT_FORMAT + AUDIT_REPORT_STRUCTURE


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

""" + AUDIT_DIRECTIVES + """
## Web Search
Use web search for unfamiliar error codes (SQLSTATE, ORA-xxxx, RECOB-xxxx). Only cite URLs you actually retrieved — never fabricate links. Map web findings into section 5 (Error & Component Mapping) or section 4 (Issues).
""" + AUDIT_OUTPUT_FORMAT + AUDIT_REPORT_STRUCTURE


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

""" + AUDIT_DIRECTIVES + AUDIT_OUTPUT_FORMAT + AUDIT_REPORT_STRUCTURE + """
Use **plain text** for numbers (e.g. `714.33s`, `195 spikes`). Never use LaTeX or `$...$` delimiters.
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
    },
    "errors": {
        "title": "Error Analysis",
        "system_addendum": (
            "The user requested an **Error Analysis**. Even if few or no errors were "
            "detected in parsing, look for: warning-level messages, informational "
            "alerts, connectivity hiccups, DDL issues, or any symptoms that could "
            "indicate latent problems. Be explicit if the log is genuinely clean."
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

    fl = summary_data.get("full_load_activity") or {}
    if fl.get("available"):
        fls = fl.get("summary") or {}
        parts = [
            f"{fls.get('tables_total', 0)} table(s)",
            f"{fls.get('tables_loaded', 0)} loaded",
        ]
        if fls.get("tables_loading"):
            parts.append(f"{fls['tables_loading']} loading")
        if fls.get("reload_events"):
            parts.append(f"{fls['reload_events']} reload event(s)")
        if fls.get("total_rows_received"):
            parts.append(f"{fls['total_rows_received']:,} rows received")
        status = "completed" if fls.get("full_load_completed") else "in progress / incomplete"
        items.append(f"- Full Load Activity: {status} ({', '.join(parts)})")

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

    cfg = summary_data.get("config") or {}
    if cfg.get("source_type") or cfg.get("target_type"):
        src = cfg.get("source_type") or "unknown"
        tgt = cfg.get("target_type") or "unknown"
        items.append(f"- Task config: {src} → {tgt} (settings table below)")

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
    warning_contexts: Optional[List[str]] = None,
    payload_format: Optional[str] = "markdown",
    graph_context: Optional[str] = None,
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
    focus_plan = build_focus_payload_plan(focus_mode, summary_data)
    warning_contexts = warning_contexts or []

    if compact:
        _max_anomalies = 3
        _max_anom_chars = 700
        _max_kb = 4
        _max_rn = 5
        _quote_top_n = focus_plan.quote_top_n
        _quote_max_chars = 900
        _budgets = EvidenceBudgets(line_evidence=600, total_input_target=4500)
    else:
        _max_anomalies = 4
        _max_anom_chars = 900
        _max_kb = 5 if focus_plan.include_kb_release_notes else 0
        _max_rn = 6 if focus_plan.include_kb_release_notes else 0
        _quote_top_n = focus_plan.quote_top_n
        _quote_max_chars = 1200
        _budgets = EvidenceBudgets()

    budgeted: List[BudgetedSection] = []

    def _add(category: str, text: str, priority: int = 3) -> None:
        if text and text.strip():
            budgeted.append(BudgetedSection(category=category, text=text.strip(), priority=priority))

    _add("facts_inventory", EVIDENCE_PACKAGE_PREAMBLE, priority=1)

    _add(
        "facts_inventory",
        _build_context_inventory(
            summary_data, error_contexts, anomaly_contexts,
            file_info, release_notes_context, kb_context,
        ),
        priority=1,
    )

    if focus_plan.include_task_config:
        task_cfg_block = format_task_config(summary_data.get("config"))
        if task_cfg_block:
            _add("task_config_tuning", task_cfg_block, priority=1)

    if focus_plan.include_authoritative_facts:
        facts_block = build_authoritative_facts(summary_data)
        if facts_block:
            _add("facts_inventory", facts_block, priority=1)

    if focus_plan.include_error_aggregates and error_contexts:
        agg_block = build_error_aggregates(error_contexts)
        if agg_block:
            _add("error_aggregates", agg_block, priority=1)

    if graph_context and graph_context.strip():
        _add("graph_structural_facts", graph_context.strip(), priority=2)

    if focus_plan.include_warning_tail and warning_contexts:
        tail = format_warning_tail(warning_contexts)
        if tail:
            _add("line_evidence", tail, priority=2)

    if error_contexts:
        combined_text = " ".join(error_contexts[:20])
        if _TUNING_TRIGGERS_ODBC_TIMEOUT.search(combined_text):
            if tuning_reference:
                _add("task_config_tuning", tuning_reference, priority=2)
            else:
                _add("task_config_tuning", _TUNING_CHEAT_SHEET_ODBC_TIMEOUT, priority=2)
        elif tuning_reference:
            _add("task_config_tuning", tuning_reference, priority=2)

    sections: List[str] = []

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

    fl_crit = summary_data.get("full_load_activity") or {}
    fls_crit = fl_crit.get("summary") or {}
    if fl_crit.get("available") and (fls_crit.get("reload_events") or 0) > 0:
        critical_section.append(
            f"- **Full load reload loops**: {fls_crit.get('reload_events')} reload event(s) across "
            f"{fls_crit.get('tables_reloaded', 0)} table(s) — segment failure forced table reload"
        )
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
    _include_perf_section = focus_plan.include_performance_telemetry and (
        focus_plan.telemetry_depth != "skip"
        or structured_perf
        or focus_mode in (None, "performance")
    )
    if focus_plan.telemetry_depth == "minimal" and not structured_perf:
        _include_perf_section = focus_plan.include_performance_telemetry

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

    # Full Load Activity (SOURCE_UNLOAD / TARGET_LOAD / segmented tables)
    fl = summary_data.get("full_load_activity") or {}
    if fl.get("available"):
        fls = fl.get("summary") or {}
        completed = "Yes" if fls.get("full_load_completed") else "No"
        sections.append(f"""
### Full Load Activity
- **Completed**: {completed}
- Task: {fls.get('task_name') or 'unknown'} · Mode: {fls.get('running_mode') or 'unknown'}
- Tables: {fls.get('tables_total', 0)} total · {fls.get('tables_loaded', 0)} loaded · {fls.get('tables_loading', 0)} loading · {fls.get('tables_failed', 0)} failed
- Rows received: {(fls.get('total_rows_received') or 0):,} · Volume: {(fls.get('total_volume_transferred') or 0):,} bytes
- Max parallel segments: {fls.get('max_parallel_segments', 0)} · Reload events: {fls.get('reload_events', 0)}
- Duration: {fls.get('duration_seconds') if fls.get('duration_seconds') is not None else 'n/a'}s
""")
        for t in (fl.get("tables") or [])[:10]:
            segs_done = t.get("segments_complete") or 0
            segs_total = t.get("segment_count") or len(t.get("segments") or [])
            sections.append(
                f"- **{t.get('table_name', 'Unknown')}** [{t.get('status', '?')}]: "
                f"segs {segs_done}/{segs_total}, "
                f"rows={(t.get('rows_received') or 0):,}, "
                f"duration={t.get('duration_seconds') if t.get('duration_seconds') is not None else 'n/a'}s"
                + (f", reloads={t.get('reload_count')}" if t.get("reload_count") else "")
            )
            # Highlight notable segments (slow / error / large gap)
            notables = []
            for s in (t.get("segments") or []):
                reasons = []
                if s.get("status") == "error":
                    reasons.append("error")
                dur = s.get("total_duration_seconds")
                if dur is not None and dur >= 3600:
                    reasons.append(f"{dur/3600:.1f}h")
                gap = s.get("gap_unload_to_load_seconds")
                if gap is not None and gap >= 30:
                    reasons.append(f"gap {gap:.0f}s")
                if reasons:
                    pred = s.get("split_predicate")
                    pred_bit = f", split=`{pred[:80]}`" if pred else ""
                    notables.append(
                        f"seg #{s.get('segment_num')} ({', '.join(reasons)}; "
                        f"rows={s.get('rows_received') if s.get('rows_received') is not None else 'n/a'}{pred_bit})"
                    )
            if notables:
                sections.append("  - Notable: " + "; ".join(notables[:4]))

        if fl.get("insights"):
            sections.append("\n**Full-load insights:**")
            for ins in fl["insights"][:6]:
                sections.append(
                    f"- [{(ins.get('severity') or 'info').upper()}] {ins.get('title') or ins.get('type')}: "
                    f"{ins.get('message') or ''}"
                )
                if ins.get("recommendation"):
                    sections.append(f"  → {ins['recommendation']}")

        sections.append(
            "\n> Use these Full Load facts in the Executive Summary when FL is relevant "
            "(tables loaded, segment skew, reload loops, unload→load gaps). "
            "Cite row counts and durations from this section; do not invent segment numbers."
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
    
    if sections:
        _add("telemetry", "\n".join(sections), priority=2)

    representative = (
        select_representative_excerpts(
            error_contexts,
            top_n=_quote_top_n,
            max_chars=_quote_max_chars,
        )
        if focus_plan.include_representative_quotes
        else []
    )
    if representative:
        quote_parts = [
            "## Representative error evidence (top patterns)\n",
            "One full excerpt per top pattern. Counts are in Log Aggregates above.\n",
        ]
        if compact:
            referenced = {
                c for ctx in representative
                for c in COMPONENT_CONTEXT if c in ctx
            }
            if referenced:
                quote_parts.append(
                    "Components referenced: "
                    + ", ".join(
                        f"**{c}** ({COMPONENT_CONTEXT[c]})"
                        for c in sorted(referenced)
                    )
                    + "\n"
                )
        for i, ctx in enumerate(representative, 1):
            quote_parts.append(f"**Pattern {i}:**\n```\n{ctx}\n```\n")
        _add("line_evidence", "\n".join(quote_parts), priority=3)

    if focus_plan.include_kb_release_notes and release_notes_context:
        rn_parts = [
            "## Release Notes Correlation\n",
            "The following release note entries may be relevant to the issues detected:\n",
        ]
        for i, rn in enumerate(release_notes_context[:_max_rn], 1):
            title = rn.get("title", "Unknown")
            version = rn.get("version", "")
            fix_id = rn.get("fix_id", "")
            snippet = rn.get("content", "")[:350]
            version_label = f" ({version})" if version else ""
            fix_label = f" [{fix_id}]" if fix_id else ""
            rn_parts.append(f"{i}. **{title}{version_label}{fix_label}**: {snippet}\n")
        _add("kb_release_notes", "\n".join(rn_parts), priority=5)

    if focus_plan.include_kb_release_notes and kb_context:
        kb_parts = [
            "## Relevant Knowledge Base Articles\n",
            "The following KB articles from the Qlik support knowledge base may help:\n",
        ]
        for i, kb in enumerate(kb_context[:_max_kb], 1):
            title = kb.get("title", "Unknown")
            snippet = kb.get("content", "")[:400]
            kb_parts.append(f"{i}. **{title}**: {snippet}\n")
        _add("kb_release_notes", "\n".join(kb_parts), priority=5)

    from backend.llm.payload_formats import render_payload

    final_sections, _budget_report = enforce_budgets(budgeted, _budgets)
    return render_payload(
        final_sections,
        payload_format,
        summary_data=summary_data,
        file_info=file_info,
    )


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

    fl_q = summary_data.get("full_load_activity") or {}
    if fl_q.get("available"):
        fls_q = fl_q.get("summary") or {}
        metrics["full_load_completed"] = fls_q.get("full_load_completed", False)
        metrics["full_load_tables_total"] = fls_q.get("tables_total", 0)
        metrics["full_load_tables_loaded"] = fls_q.get("tables_loaded", 0)
        metrics["full_load_tables_loading"] = fls_q.get("tables_loading", 0)
        metrics["full_load_reload_events"] = fls_q.get("reload_events", 0)
        metrics["full_load_rows_received"] = fls_q.get("total_rows_received", 0)
        metrics["full_load_duration_seconds"] = fls_q.get("duration_seconds")
    
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
    warning_contexts: Optional[List[str]] = None,
    payload_format: Optional[str] = "markdown",
    graph_context: Optional[str] = None,
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
        warning_contexts=warning_contexts,
        payload_format=payload_format,
        graph_context=graph_context,
    )
    
    # Select system prompt: compact (local) → short; web_search → augmented; default → full
    if compact and not web_search:
        system_prompt = SYSTEM_PROMPT_LOCAL
    elif web_search:
        system_prompt = SYSTEM_PROMPT_WITH_WEB_SEARCH
    else:
        system_prompt = SYSTEM_PROMPT

    if focus_mode and focus_mode in FOCUS_MODES:
        addendum = FOCUS_MODES[focus_mode].get("system_addendum", "")
        if addendum:
            system_prompt = system_prompt + f"\n\n## Analysis Focus\n{addendum}\n"
    
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

