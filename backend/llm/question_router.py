"""
Question Router for AI Assistant

Implements Zero-LLM-First routing with three modes:
1. LOCAL: Answer from SQLite data, no AI, no sanitization
2. KB_FUSION: Combine log facts + KB articles, no AI, no sanitization
3. AI_REQUIRED: Complex reasoning, requires AI, SANITIZE before sending

Key principles:
- 80%+ of questions should be answered locally (zero tokens)
- Sanitization ONLY happens when sending to remote AI
- All answers clearly indicate their source
"""

import re
import json
from typing import Dict, List, Tuple, Any, Optional

# Import the new routing system
from backend.llm.local_query_engine import (
    AnswerMode, 
    classify_intent as _classify_intent,
    LocalAnswer,
    QueryIntent
)


# ============================================================
# New 3-Mode Classification (Zero-LLM-First)
# ============================================================

def get_answer_mode(question: str) -> Tuple[AnswerMode, QueryIntent]:
    """
    Classify question using the new 3-mode system.
    
    Returns:
        Tuple of (AnswerMode, QueryIntent)
    """
    return _classify_intent(question)


# ============================================================
# Legacy Classification (for backward compatibility)
# ============================================================

# Patterns that indicate the question can be answered from log data alone
LOG_ONLY_PATTERNS = [
    # Table-related questions
    r"\b(what|which|list|show)\b.*\btables?\b",
    r"\btables?\b.*(mentioned|appear|listed|replicated|in the log)",
    r"\bhow many tables\b",
    
    # Record/count questions
    r"\b(how many|count|number of)\b.*(records?|rows?|entries|changes?|operations?)",
    r"\brecord count\b",
    r"\brow count\b",
    r"\btotal (inserts?|updates?|deletes?|merges?)\b",
    
    # Error count questions (not error meaning)
    r"\b(how many|count|number of)\b.*errors?\b",
    r"\berror count\b",
    r"\blist.*errors?\b",
    r"\bshow.*errors?\b",
    
    # Time/duration questions
    r"\b(what time|when did|how long|duration|start time|end time)\b",
    r"\b(first|last|earliest|latest)\b.*(timestamp|time|entry|log)",
    
    # List/show/summarize questions
    r"\b(show me|list|summarize|give me)\b.*(the log|log data|summary)",
    r"\bsummarize\b",
    
    # Performance metrics questions
    r"\b(latency|throughput|performance)\b.*(stats?|metrics?|numbers?|values?)",
    r"\baverage (latency|time|duration)\b",
    r"\b(max|min|p95|p99|percentile)\b.*latency\b",
    
    # Batch questions
    r"\b(batch|batches)\b.*(count|number|how many|size|duration)",
    r"\bhow many batches\b",
    r"\bbatch (size|duration|count)\b",
    
    # Pipeline/CDC metrics
    r"\b(sorter|cdc|pipeline)\b.*(stats?|metrics?|status)\b",
    r"\b(memory|buffer)\b.*(usage|stats?|warnings?)\b",
    
    # Source/target metrics
    r"\b(source|target)\b.*(latency|stats?|metrics?)\b",
    r"\bbottleneck\b",
    
    # Spike/plateau detection
    r"\b(spikes?|plateaus?)\b.*(detected|found|count|how many)",
    
    # Simple factual questions about the log
    r"\bwhat (is|are) the\b.*(error|warning|latency|batch|table)",
    r"\btell me about\b.*(the log|this log|log file)",
]

# Patterns that indicate KB articles are needed for the answer
KB_NEEDED_PATTERNS = [
    # Why/explain questions
    r"\bwhy\b",
    r"\bexplain\b",
    r"\bwhat does .* means?\b",  # Matches "mean" and "means"
    r"\bwhat is .* error\b",
    r"\bwhat .* means?\b",  # Generic "what X means"
    r"\bmeaning of\b",
    
    # Root cause analysis
    r"\broot cause\b",
    r"\bcause of\b",
    r"\breason for\b",
    
    # Fix/resolve questions
    r"\b(fix|resolve|solution|solve)\b",
    r"\bhow (do i|to|can i)\b.*(fix|resolve|solve|handle)",
    r"\bwhat (should|can) i do\b",
    
    # Error code interpretation
    r"\berror code\b",
    r"\b(ORA-|SQL|ODBC|ATT-)\d+",  # Specific error codes with prefix
    r"\berror\b.*\d{3,}",  # Error followed by numeric code (3+ digits)
    r"\b\d{3,}\b.*error",  # Numeric code followed by error
    
    # Best practices
    r"\bbest practice\b",
    r"\brecommend(ed|ation)?\b",
    r"\bshould i\b",
    
    # Configuration help
    r"\bhow to configure\b",
    r"\bsetting for\b",
    r"\bconfiguration\b.*(help|issue|problem)",
    
    # Product knowledge
    r"\bqlik replicate\b",
    r"\battunity\b",
    r"\bdocumentation\b",
    
    # Interpretation/understanding requests
    r"\bwhat is (the|an?|this)\b",  # "what is the", "what is a", "what is this"
    r"\bunderstand\b",
    r"\binterpret\b",
]


def classify_question(question: str) -> Tuple[str, List[str]]:
    """
    Classify a question to determine routing mode and relevant summary sections.
    
    LEGACY FUNCTION: Maps new 3-mode system to old 2-mode for backward compatibility.
    
    New code should use get_answer_mode() which returns AnswerMode enum.
    
    Args:
        question: The user's question text
        
    Returns:
        Tuple of (mode, relevant_sections) where:
        - mode: "LOG_ONLY", "LOG_PLUS_KB", or "AI_REQUIRED"
        - relevant_sections: List of summary section keys to include
    """
    # Use new 3-mode classification
    answer_mode, intent = get_answer_mode(question)
    relevant_sections = _get_relevant_sections(question.lower().strip())
    
    # Map new modes to legacy string format
    mode_mapping = {
        AnswerMode.LOCAL: "LOG_ONLY",
        AnswerMode.KB_FUSION: "LOG_PLUS_KB", 
        # AI is disabled for Smart Search; treat as KB fusion for compatibility
        AnswerMode.AI_REQUIRED: "LOG_PLUS_KB"
    }
    
    return (mode_mapping.get(answer_mode, "LOG_PLUS_KB"), relevant_sections)


def _get_relevant_sections(question: str) -> List[str]:
    """
    Determine which summary sections are relevant to the question.
    
    Args:
        question: Lowercase question text
        
    Returns:
        List of section keys from the performance summary
    """
    sections = []
    
    # Table-related
    if any(word in question for word in ["table", "tables"]):
        sections.extend(["pain_tables", "batch_profile"])
    
    # Record/count/operations
    if any(word in question for word in ["record", "row", "count", "insert", "update", "delete", "merge", "operation"]):
        sections.extend(["batch_profile", "latency_profile"])
    
    # Error-related
    if any(word in question for word in ["error", "warning", "issue", "problem", "fail"]):
        sections.extend(["error_summary", "error_correlation"])
    
    # Performance/latency
    if any(word in question for word in ["latency", "performance", "slow", "fast", "throughput", "speed"]):
        sections.extend(["latency_profile", "bottleneck", "spikes", "plateaus"])
    
    # Batch-related
    if any(word in question for word in ["batch", "batches"]):
        sections.extend(["batch_profile", "batch_issues"])
    
    # CDC/Pipeline
    if any(word in question for word in ["cdc", "pipeline", "sorter", "memory", "buffer", "stream"]):
        sections.extend(["cdc_pipeline"])
    
    # Source/Target
    if any(word in question for word in ["source", "target", "bottleneck", "capture", "apply"]):
        sections.extend(["source_analysis", "bottleneck"])
    
    # Health/status/summary
    if any(word in question for word in ["health", "status", "summary", "overall", "general"]):
        sections.extend(["latency_profile", "bottleneck", "error_summary", "cdc_pipeline", "source_analysis", "recommendations"])
    
    # Spikes/plateaus
    if any(word in question for word in ["spike", "plateau", "anomaly", "unusual"]):
        sections.extend(["spikes", "plateaus"])
    
    # Config
    if any(word in question for word in ["config", "setting", "configuration", "timeout", "thread"]):
        sections.append("config")
    
    # Recommendations
    if any(word in question for word in ["recommend", "suggestion", "advice", "should"]):
        sections.append("recommendations")
    
    # Remove duplicates while preserving order
    seen = set()
    unique_sections = []
    for s in sections:
        if s not in seen:
            seen.add(s)
            unique_sections.append(s)
    
    # If no specific sections identified, include common ones
    if not unique_sections:
        unique_sections = ["latency_profile", "error_summary", "batch_profile"]
    
    return unique_sections


# ============================================================
# Summary Context Builder
# ============================================================

def get_relevant_summary_context(
    question: str,
    summary_data: Dict[str, Any],
    sections: List[str]
) -> str:
    """
    Build formatted context from relevant summary sections.
    
    Args:
        question: The user's question (for additional context)
        summary_data: The performance cockpit summary dictionary
        sections: List of section keys to include
        
    Returns:
        Formatted markdown string with relevant summary data
    """
    if not summary_data:
        return ""
    
    context_parts = ["## Log Analysis Summary\n"]
    
    for section in sections:
        section_content = _format_section(section, summary_data)
        if section_content:
            context_parts.append(section_content)
    
    if len(context_parts) == 1:  # Only header, no content
        return ""
    
    return "\n".join(context_parts)


def _format_section(section_key: str, data: Dict[str, Any]) -> str:
    """
    Format a single summary section as markdown.
    Optimized for AI consumption - concise but information-rich.
    """
    
    if section_key == "latency_profile" and "latency_profile" in data:
        lp = data["latency_profile"]
        if lp.get("data_points", 0) == 0:
            return ""
        
        lines = ["### Latency Profile"]
        lines.append(f"- Data points: {lp.get('data_points', 0):,}")
        
        # Format as compact table for better readability
        components_data = []
        for component in ["source", "handling", "target"]:
            if component in lp:
                stats = lp[component]
                components_data.append(f"{component}: avg {stats.get('avg', 0):.2f}s, max {stats.get('max', 0):.2f}s, p95 {stats.get('p95', 0):.2f}s")
        
        if components_data:
            lines.append("- " + " | ".join(components_data))
        
        return "\n".join(lines) + "\n"
    
    elif section_key == "bottleneck" and "bottleneck" in data:
        bn = data["bottleneck"]
        return f"### Bottleneck Analysis\n- Primary bottleneck: **{bn.get('primary', 'unknown')}**\n"
    
    elif section_key == "error_summary" and "error_summary" in data:
        es = data["error_summary"]
        lines = ["### Error Summary"]
        lines.append(f"- Total errors: {es.get('total', 0):,}")
        
        # Format component breakdown more readably
        if es.get("by_component"):
            by_comp = es['by_component']
            comp_list = sorted(by_comp.items(), key=lambda x: x[1], reverse=True)[:5]
            comp_str = ", ".join([f"{comp}: {count}" for comp, count in comp_list])
            lines.append(f"- By component: {comp_str}")
        
        return "\n".join(lines) + "\n"
    
    elif section_key == "error_correlation" and "error_correlation" in data:
        ec = data["error_correlation"]
        if ec.get("total_correlated_errors", 0) == 0:
            return ""
        lines = ["### Error Correlation with High Latency"]
        lines.append(f"- Errors during high latency: {ec.get('total_correlated_errors', 0)}")
        lines.append(f"- High latency windows: {ec.get('high_latency_windows', 0)}")
        if ec.get("errors_by_type"):
            lines.append(f"- Error types: {json.dumps(ec['errors_by_type'])}")
        return "\n".join(lines) + "\n"
    
    elif section_key == "batch_profile" and "batch_profile" in data:
        bp = data["batch_profile"]
        lines = ["### Batch Analysis"]
        lines.append(f"- Total batches: {bp.get('total_batches', 0):,}")
        
        # Format closure reasons more readably
        if bp.get("closure_reasons"):
            reasons = bp['closure_reasons']
            top_reasons = sorted(reasons.items(), key=lambda x: x[1], reverse=True)[:3]
            reasons_str = ", ".join([f"{reason}: {count}" for reason, count in top_reasons])
            lines.append(f"- Top closure reasons: {reasons_str}")
        
        # More compact size stats
        if bp.get("size_stats"):
            ss = bp["size_stats"]
            size_info = f"avg {ss.get('avg', 0):.0f}, max {ss.get('max', 0)}, total changes {ss.get('total_changes', 0):,}"
            if ss.get("single_record_pct", 0) > 5:  # Only highlight if > 5%
                size_info += f" | ⚠️ {ss.get('single_record_pct', 0):.1f}% single-record"
            lines.append(f"- Batch sizes: {size_info}")
        
        return "\n".join(lines) + "\n"
    
    elif section_key == "batch_issues" and "batch_issues" in data:
        issues = data["batch_issues"]
        if not issues:
            return ""
        lines = ["### Batch Issues Detected"]
        for issue in issues[:5]:
            lines.append(f"- [{issue.get('severity', 'info').upper()}] {issue.get('title', '')}: {issue.get('message', '')}")
        return "\n".join(lines) + "\n"
    
    elif section_key == "pain_tables" and "pain_tables" in data:
        tables = data["pain_tables"]
        if not tables:
            return ""
        lines = ["### Tables with Performance Issues"]
        for table in tables[:5]:
            # Build a more informative description
            table_info = [f"**{table.get('table_name', 'Unknown')}**"]
            
            # Add key metrics
            pain_score = table.get('pain_score', 0)
            if pain_score > 0:
                table_info.append(f"pain score {pain_score:.0f}")
            
            apply_time = table.get('total_apply_time', 0)
            if apply_time > 0:
                table_info.append(f"{apply_time:.1f}s total apply")
            
            one_by_one = table.get('one_by_one_count', 0)
            if one_by_one > 0:
                table_info.append(f"⚠️ {one_by_one} one-by-one")
            
            operations = table.get('total_operations', 0)
            if operations > 0:
                table_info.append(f"{operations:,} ops")
            
            lines.append(f"- {' | '.join(table_info)}")
        
        return "\n".join(lines) + "\n"
    
    elif section_key == "spikes" and "spikes" in data:
        spikes = data["spikes"]
        if spikes.get("count", 0) == 0:
            return ""
        lines = ["### Latency Spikes"]
        lines.append(f"- Detected: {spikes['count']} spikes")
        
        # Show top 3 most severe spikes
        spike_items = spikes.get("items", [])[:3]
        for i, spike in enumerate(spike_items, 1):
            spike_value = spike.get('value', 0)
            multiplier = spike.get('multiplier', 0)
            driver = spike.get('driver', 'unknown')
            line_num = spike.get('line_number', '?')
            lines.append(f"- Spike {i}: {spike_value:.1f}s ({multiplier:.1f}x baseline) at line {line_num}, driven by {driver}")
        
        return "\n".join(lines) + "\n"
    
    elif section_key == "plateaus" and "plateaus" in data:
        plateaus = data["plateaus"]
        if plateaus.get("count", 0) == 0:
            return ""
        lines = ["### Latency Plateaus (Sustained High Latency)"]
        lines.append(f"- Detected: {plateaus['count']} plateau periods")
        
        # Show top 3 longest plateaus
        plateau_items = plateaus.get("items", [])[:3]
        for i, plateau in enumerate(plateau_items, 1):
            avg_lat = plateau.get('avg_latency', 0)
            duration = plateau.get('duration_points', 0)
            start_line = plateau.get('start_line', '?')
            end_line = plateau.get('end_line', '?')
            lines.append(f"- Plateau {i}: avg {avg_lat:.1f}s for {duration} data points (lines {start_line}-{end_line})")
        
        return "\n".join(lines) + "\n"
    
    elif section_key == "cdc_pipeline" and "cdc_pipeline" in data:
        cp = data["cdc_pipeline"]
        lines = ["### CDC Pipeline Health"]
        lines.append(f"- Status: **{cp.get('health_status', 'unknown').upper()}**")
        lines.append(f"- Memory warnings: {cp.get('memory_warnings', 0)}")
        lines.append(f"- Disconnections: {cp.get('disconnections', 0)}")
        lines.append(f"- Reconnections: {cp.get('reconnections', 0)}")
        return "\n".join(lines) + "\n"
    
    elif section_key == "source_analysis" and "source_analysis" in data:
        sa = data["source_analysis"]
        lines = ["### Source Health"]
        lines.append(f"- Status: **{sa.get('health_status', 'unknown').upper()}**")
        lines.append(f"- Reconnects: {sa.get('total_reconnects', 0)}")
        lines.append(f"- Network issues: {sa.get('network_issues', 0)}")
        if sa.get("investigation_hints"):
            lines.append(f"- Hints: {'; '.join(sa['investigation_hints'])}")
        return "\n".join(lines) + "\n"
    
    elif section_key == "recommendations" and "recommendations" in data:
        recs = data["recommendations"]
        if not recs:
            return ""
        lines = ["### Recommendations"]
        
        # Group by priority for better organization
        high_priority = [r for r in recs if r.get('priority', '').lower() == 'high']
        medium_priority = [r for r in recs if r.get('priority', '').lower() == 'medium']
        
        if high_priority:
            lines.append("**High Priority:**")
            for rec in high_priority[:3]:
                title = rec.get('title', '')
                area = rec.get('area', '')
                desc = rec.get('description', '')[:150]
                lines.append(f"- {title} ({area}): {desc}")
        
        if medium_priority and len(high_priority) < 3:
            lines.append("**Medium Priority:**")
            remaining = 5 - len(high_priority)
            for rec in medium_priority[:remaining]:
                title = rec.get('title', '')
                area = rec.get('area', '')
                lines.append(f"- {title} ({area})")
        
        return "\n".join(lines) + "\n"
    
    elif section_key == "config" and "config" in data:
        cfg = data["config"]
        if not cfg:
            return ""
        lines = ["### Task Configuration"]
        for key, value in cfg.items():
            if value is not None:
                lines.append(f"- {key}: {value}")
        return "\n".join(lines) + "\n"
    
    return ""


# ============================================================
# Report Section Extractor
# ============================================================

# Map question keywords to report section headers
REPORT_SECTION_MAPPING = {
    # Health/status questions
    ("health", "status", "overall", "general", "summary"): 
        ["Executive Summary", "Health Score"],
    
    # Issues/problems
    ("issue", "problem", "wrong", "bad", "fix", "resolve"):
        ["Issues & Recommendations", "Key Findings"],
    
    # Performance questions
    ("performance", "latency", "slow", "fast", "throughput", "speed"):
        ["Performance Analysis", "Key Findings"],
    
    # Error questions
    ("error", "warning", "fail"):
        ["Error Code Reference", "Key Findings", "Issues & Recommendations"],
    
    # Recommendations
    ("recommend", "suggestion", "should", "advice", "best practice"):
        ["Issues & Recommendations", "Key Findings"],
}


def get_relevant_report_sections(
    question: str,
    report_content: str
) -> str:
    """
    Extract relevant sections from an existing LLM report.
    
    Args:
        question: The user's question
        report_content: Markdown content from LLMReport
        
    Returns:
        Extracted relevant sections as markdown
    """
    if not report_content:
        return ""
    
    q_lower = question.lower()
    
    # Determine which sections to extract
    sections_to_find = set()
    for keywords, sections in REPORT_SECTION_MAPPING.items():
        if any(kw in q_lower for kw in keywords):
            sections_to_find.update(sections)
    
    # Default sections if none matched
    if not sections_to_find:
        sections_to_find = {"Executive Summary", "Key Findings"}
    
    # Parse the report and extract sections
    extracted = _extract_markdown_sections(report_content, list(sections_to_find))
    
    if not extracted:
        return ""
    
    return "## From Previous Analysis Report\n\n" + extracted


def _extract_markdown_sections(content: str, section_names: List[str]) -> str:
    """
    Extract named sections from markdown content.
    
    Args:
        content: Full markdown content
        section_names: List of section header names to extract
        
    Returns:
        Extracted sections as markdown
    """
    lines = content.split('\n')
    extracted_parts = []
    current_section = None
    current_content = []
    section_level = 0
    
    for line in lines:
        # Check if this is a header
        header_match = re.match(r'^(#{1,4})\s+(.+)$', line)
        
        if header_match:
            # Save previous section if it was one we wanted
            if current_section and current_content:
                extracted_parts.append(f"### {current_section}\n" + '\n'.join(current_content))
            
            header_level = len(header_match.group(1))
            header_text = header_match.group(2).strip()
            
            # Check if this header matches any we're looking for
            matched = False
            for section_name in section_names:
                if section_name.lower() in header_text.lower():
                    current_section = header_text
                    current_content = []
                    section_level = header_level
                    matched = True
                    break
            
            if not matched:
                # If we were in a section and hit a same/higher level header, end the section
                if current_section and header_level <= section_level:
                    current_section = None
                    current_content = []
        else:
            # Add content to current section
            if current_section:
                current_content.append(line)
    
    # Don't forget the last section
    if current_section and current_content:
        extracted_parts.append(f"### {current_section}\n" + '\n'.join(current_content))
    
    # Limit total length to avoid token explosion
    result = '\n\n'.join(extracted_parts)
    if len(result) > 3000:
        result = result[:3000] + "\n\n... (truncated for brevity)"
    
    return result


# ============================================================
# Combined Context Builder
# ============================================================

def build_log_context(
    question: str,
    summary_data: Dict[str, Any],
    report_content: Optional[str] = None,
    errors_context: Optional[List[str]] = None,
    anomalies_context: Optional[List[str]] = None
) -> Tuple[str, str, List[str]]:
    """
    Build complete log context for the AI assistant.
    
    Args:
        question: The user's question
        summary_data: Performance cockpit summary
        report_content: Optional existing LLM report content
        errors_context: Optional list of error context strings
        anomalies_context: Optional list of anomaly context strings
        
    Returns:
        Tuple of (mode, context_string, relevant_sections)
    """
    mode, relevant_sections = classify_question(question)
    
    context_parts = []
    
    # 1. Add relevant summary sections
    summary_context = get_relevant_summary_context(question, summary_data, relevant_sections)
    if summary_context:
        context_parts.append(summary_context)
    
    # 2. Add relevant report sections if available
    if report_content:
        report_context = get_relevant_report_sections(question, report_content)
        if report_context:
            context_parts.append(report_context)
    
    # 3. Add error context if relevant
    if errors_context and any(word in question.lower() for word in ["error", "warning", "fail", "issue"]):
        context_parts.append("## Recent Errors from Log\n")
        for i, err in enumerate(errors_context[:3], 1):
            context_parts.append(f"### Error {i}\n```\n{err[:500]}\n```\n")
    
    # 4. Add anomaly context if relevant
    if anomalies_context and any(word in question.lower() for word in ["anomaly", "spike", "plateau", "unusual", "strange"]):
        context_parts.append("## Detected Anomalies\n")
        for anomaly in anomalies_context[:2]:
            context_parts.append(f"```\n{anomaly[:400]}\n```\n")
    
    full_context = "\n".join(context_parts)
    
    return mode, full_context, relevant_sections

