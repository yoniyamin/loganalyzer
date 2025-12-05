"""
Prompt Templates for Log Analysis Report Generation

Contains system prompts and templates for generating insightful
log analysis reports using LLMs.
"""

from typing import Dict, Any, List, Optional
import json
import re


# ============================================================
# DATA SANITIZATION - Remove sensitive information
# ============================================================

def sanitize_text(text: str) -> str:
    """
    Remove sensitive information from text before sending to LLM.
    
    Removes/masks:
    - Server names and domain names (e.g., HSP-DBM-APP05.cs.sbsit.eu)
    - License information (company names)
    - IP addresses
    - File paths that might reveal server structure
    - Email addresses
    - Connection strings with credentials
    """
    if not text:
        return text
    
    result = text
    
    # 1. Mask license information (e.g., "Licensed to Company Name")
    result = re.sub(
        r'Licensed to\s+([^,]+)',
        'Licensed to [COMPANY]',
        result,
        flags=re.IGNORECASE
    )
    
    # 2. Mask server/host names with domains (e.g., server.domain.com, SERVER-NAME.corp.local)
    # Match hostname patterns like: name.domain.tld or NAME-01.subdomain.domain.tld
    result = re.sub(
        r'\b([A-Za-z0-9][-A-Za-z0-9]*\.)+[A-Za-z]{2,}\b',
        '[SERVER]',
        result
    )
    
    # 3. Mask IP addresses (IPv4)
    result = re.sub(
        r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        '[IP_ADDRESS]',
        result
    )
    
    # 4. Mask IPv6 addresses
    result = re.sub(
        r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b',
        '[IP_ADDRESS]',
        result
    )
    
    # 5. Mask Windows UNC paths (e.g., \\server\share)
    result = re.sub(
        r'\\\\[^\s\\]+\\[^\s]*',
        '[UNC_PATH]',
        result
    )
    
    # 6. Mask Windows file paths that might reveal server structure
    # Keep the general structure but mask specific server/user names
    # Note: re.sub replacement also interprets backslashes, so use double escaping
    result = re.sub(
        r'C:\\Program Files\\[^\\]+\\[^\\]+\\data\\tasks\\',
        r'C:\\Program Files\\[APP]\\[INSTANCE]\\data\\tasks\\',
        result,
        flags=re.IGNORECASE
    )
    
    # 7. Mask email addresses
    result = re.sub(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        '[EMAIL]',
        result
    )
    
    # 8. Mask UID/user names in connection strings
    result = re.sub(
        r'UID=([^;]+)',
        'UID=[USER]',
        result,
        flags=re.IGNORECASE
    )
    
    # 9. Mask database server names in connection strings
    result = re.sub(
        r'(SYSTEM|SERVER|HOST|Data Source)=([^;]+)',
        r'\1=[SERVER]',
        result,
        flags=re.IGNORECASE
    )
    
    # 10. Mask HTTPPath and similar cloud resource identifiers
    result = re.sub(
        r'HTTPPath=\{[^}]+\}',
        'HTTPPath={[REDACTED]}',
        result,
        flags=re.IGNORECASE
    )
    
    # 11. Mask Azure/AWS/GCP resource identifiers
    result = re.sub(
        r'adb-\d+\.\d+\.[a-z]+\.[a-z]+\.[a-z]+',
        '[CLOUD_RESOURCE]',
        result
    )
    
    return result


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively sanitize all string values in a dictionary.
    """
    if not data:
        return data
    
    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = sanitize_text(value)
        elif isinstance(value, dict):
            result[key] = sanitize_dict(value)
        elif isinstance(value, list):
            result[key] = sanitize_list(value)
        else:
            result[key] = value
    return result


def sanitize_list(data: List[Any]) -> List[Any]:
    """
    Recursively sanitize all string values in a list.
    """
    if not data:
        return data
    
    result = []
    for item in data:
        if isinstance(item, str):
            result.append(sanitize_text(item))
        elif isinstance(item, dict):
            result.append(sanitize_dict(item))
        elif isinstance(item, list):
            result.append(sanitize_list(item))
        else:
            result.append(item)
    return result


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

## Response Guidelines
1. Be concise but thorough - focus on what matters
2. Prioritize findings by severity (Critical > Warning > Info)
3. Always provide actionable recommendations
4. Use technical terminology appropriately
5. Reference specific metrics and line numbers when available
6. Format your response in clean Markdown

## Report Structure
Always structure your analysis with these sections:
1. **Executive Summary** - 2-3 sentence overview
2. **Key Findings** - Bulleted list of important discoveries
3. **Performance Analysis** - Latency, throughput, bottlenecks
4. **Issues & Recommendations** - Problems found and how to fix them
5. **Health Score** - Overall assessment (Healthy/Warning/Critical)
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
- Links to relevant Qlik Community posts or documentation

## Response Guidelines
1. Be concise but thorough - focus on what matters
2. Prioritize findings by severity (Critical > Warning > Info)
3. Always provide actionable recommendations
4. Use technical terminology appropriately
5. Reference specific metrics and line numbers when available
6. Format your response in clean Markdown
7. **Include web search results** for error codes and issues

## Report Structure
Always structure your analysis with these sections:
1. **Executive Summary** - 2-3 sentence overview
2. **Key Findings** - Bulleted list of important discoveries
3. **Performance Analysis** - Latency, throughput, bottlenecks
4. **Issues & Recommendations** - Problems found with web-sourced solutions
5. **Error Code Reference** - Explanation of any error codes found (from web search)
6. **Health Score** - Overall assessment (Healthy/Warning/Critical)
"""


def build_analysis_prompt(
    summary_data: Dict[str, Any],
    error_contexts: List[str],
    anomaly_contexts: List[str],
    file_info: Optional[Dict[str, Any]] = None
) -> str:
    """
    Build the user prompt for log analysis.
    
    Args:
        summary_data: Performance cockpit and analysis data
        error_contexts: List of error messages with context
        anomaly_contexts: List of detected anomalies
        file_info: Optional file metadata (name, size, line count)
    
    Returns:
        Formatted prompt string (sanitized of sensitive data)
    """
    # === SANITIZE ALL INPUT DATA ===
    # Remove sensitive information like server names, IPs, company names
    summary_data = sanitize_dict(summary_data)
    error_contexts = sanitize_list(error_contexts)
    anomaly_contexts = sanitize_list(anomaly_contexts)
    if file_info:
        file_info = sanitize_dict(file_info)
    
    sections = []
    
    # File info header (only include non-sensitive info)
    if file_info:
        # Only include filename (which is usually just the log file name, not path)
        filename = file_info.get('filename', 'Unknown')
        # Extra sanitization for filename - remove any path components
        if '\\' in filename:
            filename = filename.split('\\')[-1]
        if '/' in filename:
            filename = filename.split('/')[-1]
        
        sections.append(f"""## Log File Information
- **Filename**: {filename}
- **Size**: {file_info.get('size_bytes', 0):,} bytes
- **Lines**: {file_info.get('line_count', 0):,}
""")
    
    # Performance Summary
    sections.append("## Performance Summary")
    
    if "latency_profile" in summary_data:
        lp = summary_data["latency_profile"]
        sections.append("""
### Latency Profile
| Metric | Source | Handling | Target |
|--------|--------|----------|--------|""")
        
        for metric in ["avg", "max", "p95", "p99"]:
            src = lp.get("source", {}).get(metric, 0)
            hdl = lp.get("handling", {}).get(metric, 0)
            tgt = lp.get("target", {}).get(metric, 0)
            sections.append(f"| {metric.upper()} | {src:.2f}s | {hdl:.2f}s | {tgt:.2f}s |")
        
        sections.append(f"\nData points analyzed: {lp.get('data_points', 0)}")
    
    # Bottleneck Analysis
    if "bottleneck" in summary_data:
        bn = summary_data["bottleneck"]
        sections.append(f"""
### Bottleneck Analysis
- **Primary Bottleneck**: {bn.get('primary', 'Unknown')}
""")
        if bn.get('periods'):
            sections.append("Recent bottleneck periods:")
            for period in bn['periods'][:3]:
                sections.append(f"  - {period.get('start_time', '?')} to {period.get('end_time', '?')}: "
                              f"{period.get('bottleneck', 'unknown')} "
                              f"(source: {period.get('source_avg', 0):.1f}s, handling: {period.get('handling_avg', 0):.1f}s)")
    
    # Spikes and Plateaus
    if "spikes" in summary_data:
        spikes = summary_data["spikes"]
        if spikes.get("count", 0) > 0:
            sections.append(f"""
### Latency Spikes
Detected **{spikes['count']} spikes**. Top spikes:""")
            for spike in spikes.get("items", [])[:5]:
                sections.append(f"- Line {spike.get('line_number', '?')}: {spike.get('value', 0):.1f}s "
                              f"({spike.get('multiplier', 0):.1f}x baseline, driver: {spike.get('driver', '?')})")
    
    if "plateaus" in summary_data:
        plateaus = summary_data["plateaus"]
        if plateaus.get("count", 0) > 0:
            sections.append(f"""
### Latency Plateaus
Detected **{plateaus['count']} sustained high-latency periods**:""")
            for plateau in plateaus.get("items", [])[:3]:
                sections.append(f"- Lines {plateau.get('start_line', '?')}-{plateau.get('end_line', '?')}: "
                              f"avg {plateau.get('avg_latency', 0):.1f}s for {plateau.get('duration_points', 0)} readings")
    
    # Batch Analysis
    if "batch_profile" in summary_data:
        bp = summary_data["batch_profile"]
        sections.append(f"""
### Batch Processing
- **Total Batches**: {bp.get('total_batches', 0)}
- **Closure Reasons**: {json.dumps(bp.get('closure_reasons', {}))}
""")
        if "size_stats" in bp:
            ss = bp["size_stats"]
            sections.append(f"- Batch sizes: avg={ss.get('avg', 0):.0f}, max={ss.get('max', 0)}, "
                          f"single-record={ss.get('single_record_pct', 0):.1f}%")
    
    if "batch_issues" in summary_data and summary_data["batch_issues"]:
        sections.append("\n**Batch Issues Detected:**")
        for issue in summary_data["batch_issues"]:
            sections.append(f"- [{issue.get('severity', 'info').upper()}] {issue.get('title', '')}: {issue.get('message', '')}")
    
    # Pain Tables
    if "pain_tables" in summary_data and summary_data["pain_tables"]:
        sections.append("""
### Tables with Performance Issues""")
        for table in summary_data["pain_tables"][:5]:
            sections.append(f"- **{table.get('table_name', 'Unknown')}**: "
                          f"pain_score={table.get('pain_score', 0):.0f}, "
                          f"apply_time={table.get('total_apply_time', 0):.1f}s, "
                          f"one-by-one={table.get('one_by_one_count', 0)}")
    
    # CDC Pipeline Status
    if "cdc_pipeline" in summary_data:
        cp = summary_data["cdc_pipeline"]
        sections.append(f"""
### CDC Pipeline Health
- **Status**: {cp.get('health_status', 'unknown').upper()}
- Memory warnings: {cp.get('memory_warnings', 0)}
- Disconnections: {cp.get('disconnections', 0)}
- Reconnections: {cp.get('reconnections', 0)}
""")
    
    # Source Analysis
    if "source_analysis" in summary_data:
        sa = summary_data["source_analysis"]
        sections.append(f"""
### Source Health
- **Status**: {sa.get('health_status', 'unknown').upper()}
- Reconnects: {sa.get('total_reconnects', 0)}
- Network issues: {sa.get('network_issues', 0)}
- Contention issues: {sa.get('contention_issues', 0)}
""")
        if sa.get('investigation_hints'):
            sections.append("Investigation hints: " + "; ".join(sa['investigation_hints']))
    
    # Error Summary
    if "error_summary" in summary_data:
        es = summary_data["error_summary"]
        sections.append(f"""
### Error Summary
- **Total Errors**: {es.get('total', 0)}
- By component: {json.dumps(es.get('by_component', {}))}
""")
    
    # Error Correlation
    if "error_correlation" in summary_data:
        ec = summary_data["error_correlation"]
        if ec.get('total_correlated_errors', 0) > 0:
            sections.append(f"""
### Errors During High Latency
- Correlated errors: {ec.get('total_correlated_errors', 0)}
- High latency windows: {ec.get('high_latency_windows', 0)}
- Error types: {json.dumps(ec.get('errors_by_type', {}))}
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
    
    # Error Contexts from RAG
    if error_contexts:
        sections.append("""
## Error Context Samples
The following are sample errors with surrounding context from the log:
""")
        for i, ctx in enumerate(error_contexts[:5], 1):
            sections.append(f"### Error Sample {i}")
            sections.append(f"```\n{ctx[:1500]}\n```\n")
    
    # Anomaly Contexts from RAG
    if anomaly_contexts:
        sections.append("""
## Detected Anomalies
""")
        for ctx in anomaly_contexts[:3]:
            sections.append(f"```\n{ctx[:1000]}\n```\n")
    
    # Final instruction
    sections.append("""
---

## Your Task

Based on the above log analysis data, provide a comprehensive report that:

1. Summarizes the overall health and performance of this replication task
2. Identifies the root causes of any issues
3. Provides specific, actionable recommendations
4. Estimates the severity and urgency of any problems found

Focus on what a support engineer or DBA would need to know to troubleshoot and optimize this replication task.
""")
    
    return "\n".join(sections)


def build_quick_summary_prompt(summary_data: Dict[str, Any]) -> str:
    """
    Build a prompt for a quick summary (fewer tokens, faster response).
    
    Args:
        summary_data: Performance cockpit data
    
    Returns:
        Formatted prompt string (sanitized of sensitive data)
    """
    # Sanitize input data
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
    web_search: bool = False
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
    
    Returns:
        List of message dicts ready for the LLM API
    """
    if quick:
        return [
            {"role": "system", "content": QUICK_SUMMARY_SYSTEM},
            {"role": "user", "content": build_quick_summary_prompt(summary_data)}
        ]
    
    user_prompt = build_analysis_prompt(
        summary_data=summary_data,
        error_contexts=error_contexts,
        anomaly_contexts=anomaly_contexts,
        file_info=file_info
    )
    
    # Use web search system prompt if enabled
    system_prompt = SYSTEM_PROMPT_WITH_WEB_SEARCH if web_search else SYSTEM_PROMPT
    
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

