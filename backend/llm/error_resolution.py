"""
Error resolution helper that combines KB, AI report snippets, and Tavily search.
"""

import re
import logging
from typing import Dict, Any, Optional, List

from sqlalchemy.orm import Session

from backend.database import LLMReport, LogTaskConfig
from backend.llm.vectorstore import get_vector_store
from backend.llm.tavily_client import TavilyClient, format_tavily_sources

logger = logging.getLogger(__name__)


def _extract_relevant_ai_section(
    report_content: str,
    message_summary: str,
    error_code: Optional[str],
    component: Optional[str],
    max_len: int = 800,
) -> Optional[str]:
    """
    Extract the most relevant section from an AI report based on the issue.
    
    Looks for sections that mention the error code, component, or similar keywords.
    Returns a focused excerpt instead of just the first N characters.
    """
    if not report_content:
        return None
    
    # Build search terms from the issue
    search_terms = []
    if error_code:
        search_terms.append(error_code.lower())
    if component:
        search_terms.append(component.lower())
    # Extract key words from message (filter out common words)
    if message_summary:
        words = re.findall(r'\b[a-zA-Z_]{4,}\b', message_summary.lower())
        skip_words = {'error', 'warning', 'failed', 'could', 'cannot', 'unable', 'with', 'from', 'that', 'this', 'when'}
        search_terms.extend([w for w in words if w not in skip_words][:5])
    
    if not search_terms:
        # Fall back to first section
        return _safe_excerpt(report_content, max_len)
    
    # Split into sections (by markdown headers or double newlines)
    sections = re.split(r'\n(?=#{1,3}\s|\*\*[A-Z])', report_content)
    if len(sections) == 1:
        # Try splitting by double newlines
        sections = re.split(r'\n\n+', report_content)
    
    # Score each section by relevance
    scored_sections = []
    for section in sections:
        section_lower = section.lower()
        score = sum(1 for term in search_terms if term in section_lower)
        if score > 0:
            scored_sections.append((score, section.strip()))
    
    if scored_sections:
        # Sort by score descending and take the best matching section(s)
        scored_sections.sort(key=lambda x: -x[0])
        best_sections = []
        total_len = 0
        for score, section in scored_sections:
            if total_len + len(section) > max_len and best_sections:
                break
            best_sections.append(section)
            total_len += len(section)
        
        result = "\n\n".join(best_sections)
        return result[:max_len] + "…" if len(result) > max_len else result
    
    # Fallback: return first portion
    return _safe_excerpt(report_content, max_len)


def _get_task_db_hint(db: Session, file_id: int) -> Optional[str]:
    config = (
        db.query(LogTaskConfig)
        .filter(LogTaskConfig.file_id == file_id)
        .first()
    )
    if not config:
        return None

    hints = []
    if config.target_type:
        hints.append(config.target_type)
    if config.source_type:
        hints.append(config.source_type)

    if not hints:
        return None

    # Deduplicate and join
    return " / ".join(dict.fromkeys(hints))


def _looks_like_db_error(text: str) -> bool:
    lowered = text.lower()
    return any(
        token in lowered
        for token in ["odbc", "oci", "sql_error", "sqlstate", "rtcode", "retcode"]
    )


def _strip_log_prefix(text: str) -> str:
    """
    Strip the log line prefix (line number, timestamp, thread, component) from error text.
    
    Example input:
    00013432: 2025-12-10T17:40:59:568174 [TARGET_LOAD     ]T:  RetCode: SQL_ERROR...
    
    Output:
    RetCode: SQL_ERROR...
    """
    if not text:
        return text
    
    # Pattern to match log prefix: optional line num, timestamp, [COMPONENT], severity indicator
    # Format: NNNNNNNN: YYYY-MM-DDTHH:MM:SS:NNNNNN [COMPONENT      ]X:
    prefix_pattern = r'^[\d]+:\s*\d{4}-\d{2}-\d{2}T[\d:]+\s*\[[^\]]+\]\s*[TEWID]:\s*'
    cleaned = re.sub(prefix_pattern, '', text.strip())
    
    # If the pattern didn't match, try a simpler approach - find common error indicators
    if cleaned == text.strip():
        # Look for common error message starts
        for indicator in ['RetCode:', 'Error:', 'Failed', 'Unable', 'Cannot', 'Could not']:
            idx = text.find(indicator)
            if idx > 0:
                cleaned = text[idx:]
                break
    
    return cleaned.strip()


def _build_query(
    message_summary: str,
    error_code: Optional[str],
    db_hint: Optional[str],
    component: Optional[str],
    full_error_text: Optional[str] = None,
) -> str:
    # Use full error text if provided, otherwise fall back to summary
    error_text = (full_error_text or message_summary or "").strip()
    
    # Strip log prefix (timestamp, thread, component) from the error text
    error_text = _strip_log_prefix(error_text)
    
    # Limit to reasonable length but keep more context than before
    if len(error_text) > 300:
        error_text = error_text[:300]
    
    parts = ["Qlik Replicate", error_text]
    if error_code and error_code not in error_text:
        parts.append(error_code.strip())
    if component and component not in error_text:
        parts.append(component.strip())
    if db_hint and _looks_like_db_error(error_text + " " + (error_code or "")):
        parts.append(db_hint)
    return " ".join([p for p in parts if p])


def _safe_excerpt(text: Optional[str], limit: int = 1200) -> Optional[str]:
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def resolve_issue(
    db: Session,
    file_id: int,
    *,
    message_summary: str,
    error_code: Optional[str] = None,
    context_snippet: Optional[str] = None,
    component: Optional[str] = None,
    tavily_api_key: Optional[str] = None,
    full_error_text: Optional[str] = None,
    custom_query: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Resolve an issue by aggregating KB, AI report snippet, and Tavily answer.
    """
    response: Dict[str, Any] = {
        "kb": {"matches": []},
        "ai_report": None,
        "tavily": None,
    }

    db_hint = _get_task_db_hint(db, file_id)
    # Use custom query if provided, otherwise build from error details
    if custom_query:
        query = custom_query
    else:
        query = _build_query(message_summary, error_code, db_hint, component, full_error_text)
    response["query"] = query

    # KB retrieval via dedicated KB collection (not log embeddings)
    try:
        vector_store = get_vector_store()
        # Use query_kb() to search the actual KB articles collection
        kb_matches = vector_store.query_kb(
            query=query,
            n_results=5,
        )
        normalized_matches: List[Dict[str, Any]] = []
        for item in kb_matches:
            # KB results have title, url, content, similarity
            normalized_matches.append(
                {
                    "content": item.get("content", "")[:600],
                    "source": item.get("title") or item.get("metadata", {}).get("source", "KB Article"),
                    "distance": item.get("distance"),
                    "similarity": item.get("similarity", 0),
                    "url": item.get("url") or item.get("metadata", {}).get("url"),
                }
            )
        # Filter to only matches with good similarity (>0.5 for direct matches)
        normalized_matches = [m for m in normalized_matches if m.get("similarity", 0) > 0.5]
        response["kb"]["matches"] = normalized_matches
    except Exception as e:
        logger.warning("KB lookup failed: %s", e)
        response["kb"]["error"] = str(e)

    # AI report snippet - extract relevant section
    try:
        latest_report: Optional[LLMReport] = (
            db.query(LLMReport)
            .filter(LLMReport.file_id == file_id)
            .order_by(LLMReport.generated_at.desc())
            .first()
        )
        if latest_report and latest_report.report_content:
            # Extract the most relevant section based on error/component
            excerpt = _extract_relevant_ai_section(
                latest_report.report_content,
                message_summary,
                error_code,
                component,
                max_len=600,
            )
            if excerpt:
                response["ai_report"] = {
                    "report_id": latest_report.id,
                    "excerpt": excerpt,
                }
    except Exception as e:
        logger.warning("AI report lookup failed: %s", e)

    # Tavily search
    if tavily_api_key:
        client = TavilyClient(api_key=tavily_api_key)
        try:
            tavily_data = client.advanced_answer(query)
            response["tavily"] = {
                "answer": tavily_data.get("answer"),
                "sources": format_tavily_sources(tavily_data),
            }
        except Exception as e:
            response["tavily_error"] = str(e)
        response["tavily_configured"] = True
    else:
        response["tavily_configured"] = False
        response["tavily_status"] = "not_searched"  # Means search wasn't requested, not that key is missing

    # Context echo for UI
    response["context"] = _safe_excerpt(context_snippet, limit=800)

    return response

