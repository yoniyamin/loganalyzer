"""
Local Query Engine - Answer Questions from SQLite Data Without AI

This module implements the "Zero-LLM-First" philosophy:
- Answer 80%+ of questions locally from indexed log data
- No token cost for factual questions (counts, lists, searches)
- No sanitization needed for local answers

Routing Modes:
- LOCAL: Answer directly from SQLite data
- KB_FUSION: Combine local facts with KB articles
- AI_REQUIRED: Complex reasoning that needs AI model
"""

import re
import json
import logging
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple, NamedTuple
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import func, text

from backend.database import (
    LogFile, LogError, LogPerformance, LogBatch, 
    LogTableStats, LogSorterEvent, LogTaskConfig, LogStats
)

logger = logging.getLogger(__name__)


# =============================================================================
# Answer Modes - The Core of Zero-LLM-First
# =============================================================================

class AnswerMode(Enum):
    """
    Three-tier routing for questions.
    
    LOCAL: Answer from SQLite, no AI, no sanitization needed
    KB_FUSION: Answer from log facts + KB articles, no AI, no sanitization
    AI_REQUIRED: Complex reasoning, requires AI, SANITIZE before sending
    """
    LOCAL = "local"
    KB_FUSION = "kb"
    AI_REQUIRED = "ai"


@dataclass
class LocalAnswer:
    """Result from local query engine."""
    answer: str
    source: str = "local"
    confidence: str = "high"
    data: Optional[Dict[str, Any]] = None
    query_type: Optional[str] = None
    tokens_used: int = 0  # Always 0 for local answers


@dataclass 
class QueryIntent:
    """Extracted intent from user question."""
    type: str  # COUNT, LIST, SEARCH, STATS, EXPLAIN, FIX
    entity: Optional[str] = None  # errors, tables, batches, etc.
    filters: Optional[Dict[str, Any]] = None
    raw_question: str = ""


# =============================================================================
# Intent Classification Patterns
# =============================================================================

# Questions that can be answered locally (no AI needed)
LOCAL_INTENT_PATTERNS = {
    # INFO intents - specific factual questions about task/log properties
    "INFO": [
        (r"\b(what|what's|tell me)\b.*\b(task|name)\b.*\b(name|task|called)\b", "task_name"),
        (r"\btask\s*name\b", "task_name"),
        (r"\bname of (the |this |)task\b", "task_name"),
        (r"\b(what|which)\b.*\b(source|source endpoint)\b", "source"),
        (r"\bsource (endpoint|type|database|db)\b", "source"),
        (r"\b(what|which)\b.*\b(target|target endpoint|destination)\b", "target"),
        (r"\btarget (endpoint|type|database|db)\b", "target"),
        (r"\b(what|which)\b.*\b(version|replicate version)\b", "version"),
        (r"\bversion (of |)(replicate|qlik|software)\b", "version"),
        (r"\b(what|which)\b.*\b(server|host|machine)\b", "server"),
        (r"\b(run|running|execution) mode\b", "run_mode"),
        (r"\bstart mode\b", "start_mode"),
        (r"\b(what|which)\b.*\b(mode|modes?)\b", "run_mode"),
        (r"\bwhat os\b|\boperating system\b", "os_info"),
        (r"\b(when|what time).*\b(start|begin|began)\b", "start_time"),
        (r"\b(when|what time).*\b(end|finish|stop|complete)\b", "end_time"),
        (r"\b(how long|duration|runtime)\b", "duration"),
        (r"\b(full load|cdc|change data capture)\b.*(status|complete|done|running)", "replication_status"),
    ],
    
    # COUNT intents
    "COUNT": [
        (r"\b(how many|count|number of|total)\b.*\b(errors?|warnings?)\b", "errors"),
        (r"\b(how many|count|number of|total)\b.*\b(tables?)\b", "tables"),
        (r"\b(how many|count|number of|total)\b.*\b(batch|batches)\b", "batches"),
        (r"\b(how many|count|number of|total)\b.*\b(inserts?|updates?|deletes?|merges?)\b", "operations"),
        (r"\b(how many|count|number of|total)\b.*\b(records?|rows?|entries)\b", "records"),
        (r"\b(how many|count|number of|total)\b.*\b(lines?)\b", "lines"),
        (r"\berror count\b", "errors"),
        (r"\btable count\b", "tables"),
    ],
    
    # LIST intents - expanded to catch more phrasings
    "LIST": [
        (r"\b(what|which|list|show|display|tell me)\b.*\b(tables?)\b", "tables"),
        (r"\b(what|which|list|show|tell me|give me)\b.*\b(errors?)\b", "errors"),
        (r"\berrors?\b.*(what|mean|in the log|found|occurred|happening)", "errors"),
        (r"\bwhat.*errors?\b", "errors"),  # "what are the errors", "what errors"
        (r"\b(what|which|list|show)\b.*\b(components?)\b", "components"),
        (r"\b(list|show)\b.*\b(batch|batches)\b.*\b(closure|reasons?)\b", "batch_reasons"),
        (r"\btables?\b.*(mentioned|appear|listed|replicated|in the log)", "tables"),
        (r"\b(any|are there)\b.*\b(errors?|issues?|problems?)\b", "errors"),
        (r"\btell me about\b.*(errors?|issues?)", "errors"),
        (r"\bwhat (is|are) (the |)(issue|problem|error)", "errors"),
    ],
    
    # STATS intents
    "STATS": [
        (r"\b(what|what's|show)\b.*\b(latency|latencies)\b", "latency"),
        (r"\b(average|avg|mean|max|min|p95|p99)\b.*\b(latency)\b", "latency"),
        (r"\b(performance|throughput)\b.*(stats?|metrics?|numbers?)", "performance"),
        (r"\bbottleneck\b", "bottleneck"),
        (r"\b(source|target|handling)\b.*\b(latency)\b", "latency"),
        (r"\b(slow|fast|speed|performance)\b", "performance"),
    ],
    
    # SEARCH intents - search raw log content
    "SEARCH": [
        (r"\b(what|which)\b.*\b(odbc|driver|drivers)\b", "odbc_drivers"),
        (r"\b(license|licensed)\b", "license"),
        (r"\bserver\b.*\b(name|info)\b", "server_info"),
        # Generic search patterns - extract keyword from question
        (r"\b(anything|something|find|search|look for|show me|any mention)\b.*(about|for|regarding|related to|of|with)\b", "generic_search"),
        (r"\b(is there|are there|can you find|do you see)\b.*(mention|reference|info|information)\b", "generic_search"),
        (r"\bconnection string\b", "connection_string"),
        (r"\b(what|where)\b.*(connection string|conn string)\b", "connection_string"),
        (r"\bfind\b.*\b(in the log|in log)\b", "generic_search"),
        (r"\bsearch (for |the log for |)", "generic_search"),
    ],
    
    # TIME intents
    "TIME": [
        (r"\b(when|what time|start time|end time|first|last)\b", "timestamps"),
        (r"\b(earliest|latest)\b.*\b(timestamp|time|entry)\b", "timestamps"),
    ],
    
    # SUMMARY intents - expanded
    "SUMMARY": [
        (r"\b(summarize|summary|overview)\b", "summary"),
        (r"\btell me about\b.*(the log|this log|log file)", "summary"),
        (r"\b(health|status)\b.*\b(check|report)\b", "health"),
        (r"\bwhat('s| is) (in |)(the |this |)log\b", "summary"),
        (r"\b(give me|show me) (a |)summary\b", "summary"),
    ],
}

# Questions that need KB articles (but not necessarily AI)
KB_NEEDED_PATTERNS = [
    r"\bwhat does\b.*\bmeans?\b",
    r"\bwhat is\b.*(error|code|message)",
    r"\b(ORA-|SQL|ODBC|ATT-)\d+",  # Error codes
    r"\bknown issue\b",
    r"\bdocumentation\b",
]

# Questions that require AI reasoning
AI_REQUIRED_PATTERNS = [
    r"\bwhy\b",
    r"\bexplain\b.*\b(root cause|reason)\b",
    r"\banalyze\b",
    r"\bwhat should i do\b",
    r"\brecommend\b",
    r"\bhow (do i|to|can i)\b.*(fix|resolve|solve)",
    r"\broot cause\b",
    r"\bbest practice\b",
]


# =============================================================================
# Intent Classification
# =============================================================================

def classify_intent(question: str) -> Tuple[AnswerMode, QueryIntent]:
    """
    Classify a question to determine how to answer it.
    
    Returns:
        Tuple of (AnswerMode, QueryIntent)
    """
    q_lower = question.lower().strip()
    
    # Check for AI-required patterns first (they take priority)
    for pattern in AI_REQUIRED_PATTERNS:
        if re.search(pattern, q_lower):
            return (AnswerMode.AI_REQUIRED, QueryIntent(
                type="COMPLEX",
                raw_question=question
            ))
    
    # Check for KB-needed patterns
    for pattern in KB_NEEDED_PATTERNS:
        if re.search(pattern, q_lower):
            return (AnswerMode.KB_FUSION, QueryIntent(
                type="KB_LOOKUP",
                raw_question=question
            ))
    
    # Check for local intent patterns
    for intent_type, patterns in LOCAL_INTENT_PATTERNS.items():
        for pattern, entity in patterns:
            if re.search(pattern, q_lower):
                return (AnswerMode.LOCAL, QueryIntent(
                    type=intent_type,
                    entity=entity,
                    raw_question=question
                ))
    
    # Default: try KB fusion first, then AI if needed
    return (AnswerMode.KB_FUSION, QueryIntent(
        type="GENERAL",
        raw_question=question
    ))


# =============================================================================
# Local Query Functions
# =============================================================================

def answer_locally(
    question: str,
    file_id: int,
    db: Session
) -> Optional[LocalAnswer]:
    """
    Try to answer a question from local SQLite data.
    
    Returns:
        LocalAnswer if answerable locally, None if AI needed.
    """
    mode, intent = classify_intent(question)
    
    if mode == AnswerMode.AI_REQUIRED:
        return None  # AI required
    
    # Route to appropriate handler based on intent type
    handlers = {
        "INFO": _handle_info_query,
        "COUNT": _handle_count_query,
        "LIST": _handle_list_query,
        "STATS": _handle_stats_query,
        "SEARCH": _handle_search_query,
        "TIME": _handle_time_query,
        "SUMMARY": _handle_summary_query,
    }
    
    handler = handlers.get(intent.type)
    if handler:
        try:
            result = handler(intent, file_id, db)
            if result:
                return result
        except Exception as e:
            logger.warning(f"Local query handler failed: {e}")
    
    # FALLBACK: For GENERAL/KB_LOOKUP intents, try to provide useful local info
    # Check if question mentions errors/issues - provide error summary
    q_lower = question.lower()
    if any(word in q_lower for word in ['error', 'issue', 'problem', 'fail', 'wrong']):
        try:
            return _handle_list_query(QueryIntent(type="LIST", entity="errors", raw_question=question), file_id, db)
        except Exception as e:
            logger.warning(f"Fallback error handler failed: {e}")
    
    # Check if question mentions tables
    if any(word in q_lower for word in ['table', 'replicat']):
        try:
            return _handle_list_query(QueryIntent(type="LIST", entity="tables", raw_question=question), file_id, db)
        except Exception as e:
            logger.warning(f"Fallback tables handler failed: {e}")
    
    # Check if question is generally about the log
    if any(word in q_lower for word in ['log', 'summary', 'overview', 'what']):
        try:
            return _handle_summary_query(QueryIntent(type="SUMMARY", entity="summary", raw_question=question), file_id, db)
        except Exception as e:
            logger.warning(f"Fallback summary handler failed: {e}")
    
    return None


def _get_log_summary_data(file_id: int, db: Session) -> Optional[Dict[str, Any]]:
    """
    Fetch parsed log summary data using the same logic as the API endpoint.
    Returns task info, version, endpoints, status, etc.
    """
    import re
    
    file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not file or not file.file_path:
        return None
    
    try:
        with open(file.file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()[:200]  # Only scan first 200 lines for header info
    except Exception:
        return None
    
    summary = {
        'task_name': None,
        'version': None,
        'server': None,
        'host': None,
        'os_info': None,
        'source_endpoint': None,
        'source_type': None,
        'target_endpoint': None, 
        'target_type': None,
        'running_mode': None,
        'start_mode': None,
        'start_time': None,
        'full_load_complete': False,
        'cdc_started': False,
    }
    
    for line in lines:
        # Task Server Log line - extract task info
        if 'Task Server Log -' in line and not summary['task_name']:
            task_match = re.search(r'Task Server Log - (\S+)\s+\(V([\d.]+)\s+(\S+)', line)
            if task_match:
                summary['task_name'] = task_match.group(1)
                summary['version'] = task_match.group(2)
                summary['host'] = task_match.group(3)
                summary['server'] = task_match.group(3)
                
                # Extract OS info
                os_match = re.search(r'V[\d.]+\s+\S+\s+(.+?)(?:,\s+Revision:|,\s+PID:)', line)
                if os_match:
                    summary['os_info'] = os_match.group(1).strip()
        
        # Running mode
        if "Task '" in line and "running" in line:
            mode_match = re.search(r"Task '([^']+)' running (.+?) in (.+?) mode", line)
            if mode_match:
                summary['task_name'] = summary['task_name'] or mode_match.group(1)
                summary['running_mode'] = mode_match.group(2).strip()
                summary['start_mode'] = mode_match.group(3).strip()
        
        # Source endpoint info
        if 'Source endpoint' in line:
            src_match = re.search(r"Source endpoint '([^']+)'", line)
            if src_match:
                summary['source_endpoint'] = src_match.group(1)
            # Try to get source type
            provider_match = re.search(r'using provider\s*\([\'"]([^\'"]+)', line)
            if provider_match:
                summary['source_type'] = provider_match.group(1)
        
        # Target endpoint info
        if 'Target endpoint' in line:
            tgt_match = re.search(r"Target endpoint '([^']+)'", line)
            if tgt_match:
                summary['target_endpoint'] = tgt_match.group(1)
            provider_match = re.search(r'using provider\s*\([\'"]([^\'"]+)', line)
            if provider_match:
                summary['target_type'] = provider_match.group(1)
        
        # Full load complete
        if 'Full load complete' in line or 'Full Load completed' in line:
            summary['full_load_complete'] = True
        
        # CDC started
        if 'Change Data Capture' in line and ('started' in line or 'Starting' in line):
            summary['cdc_started'] = True
    
    # Also try to extract from filename if task_name not found
    if not summary['task_name'] and file.filename:
        # Common pattern: reptask_TASKNAME.log
        name_match = re.search(r'reptask_(.+?)\.log', file.filename, re.IGNORECASE)
        if name_match:
            summary['task_name'] = name_match.group(1)
    
    return summary


def _handle_info_query(intent: QueryIntent, file_id: int, db: Session) -> Optional[LocalAnswer]:
    """Handle INFO type questions - specific factual information about the task/log."""
    entity = intent.entity
    question = intent.raw_question.lower()
    
    # Get the parsed log summary
    summary = _get_log_summary_data(file_id, db)
    if not summary:
        return None
    
    # Also get the LogTaskConfig for additional info
    task_config = db.query(LogTaskConfig).filter(LogTaskConfig.file_id == file_id).first()
    
    # Handle different entity types
    if entity == "task_name":
        task_name = summary.get('task_name')
        if task_name:
            return LocalAnswer(
                answer=f"**Task Name:** {task_name}",
                confidence="high",
                data={"task_name": task_name},
                query_type="INFO"
            )
        return LocalAnswer(
            answer="Could not determine the task name from the log file.",
            confidence="low",
            query_type="INFO"
        )
    
    elif entity == "source":
        source_ep = summary.get('source_endpoint')
        source_type = summary.get('source_type') or (task_config.source_type if task_config else None)
        if source_ep or source_type:
            parts = []
            if source_ep:
                parts.append(f"**Source Endpoint:** {source_ep}")
            if source_type:
                parts.append(f"**Source Type:** {source_type}")
            return LocalAnswer(
                answer="\n".join(parts),
                confidence="high",
                data={"source_endpoint": source_ep, "source_type": source_type},
                query_type="INFO"
            )
        return LocalAnswer(
            answer="Source endpoint information not found in the log.",
            confidence="low",
            query_type="INFO"
        )
    
    elif entity == "target":
        target_ep = summary.get('target_endpoint')
        target_type = summary.get('target_type') or (task_config.target_type if task_config else None)
        if target_ep or target_type:
            parts = []
            if target_ep:
                parts.append(f"**Target Endpoint:** {target_ep}")
            if target_type:
                parts.append(f"**Target Type:** {target_type}")
            return LocalAnswer(
                answer="\n".join(parts),
                confidence="high",
                data={"target_endpoint": target_ep, "target_type": target_type},
                query_type="INFO"
            )
        return LocalAnswer(
            answer="Target endpoint information not found in the log.",
            confidence="low",
            query_type="INFO"
        )
    
    elif entity == "version":
        version = summary.get('version')
        if version:
            return LocalAnswer(
                answer=f"**Qlik Replicate Version:** {version}",
                confidence="high",
                data={"version": version},
                query_type="INFO"
            )
        return LocalAnswer(
            answer="Version information not found in the log.",
            confidence="low",
            query_type="INFO"
        )
    
    elif entity == "server":
        server = summary.get('server') or summary.get('host')
        os_info = summary.get('os_info')
        if server:
            parts = [f"**Server/Host:** {server}"]
            if os_info:
                parts.append(f"**Operating System:** {os_info}")
            return LocalAnswer(
                answer="\n".join(parts),
                confidence="high",
                data={"server": server, "os_info": os_info},
                query_type="INFO"
            )
        return LocalAnswer(
            answer="Server information not found in the log.",
            confidence="low",
            query_type="INFO"
        )
    
    elif entity == "run_mode":
        running_mode = summary.get('running_mode')
        start_mode = summary.get('start_mode')
        if running_mode or start_mode:
            parts = []
            if running_mode:
                parts.append(f"**Running Mode:** {running_mode}")
            if start_mode:
                parts.append(f"**Start Mode:** {start_mode}")
            return LocalAnswer(
                answer="\n".join(parts),
                confidence="high",
                data={"running_mode": running_mode, "start_mode": start_mode},
                query_type="INFO"
            )
        return LocalAnswer(
            answer="Run mode information not found in the log.",
            confidence="low",
            query_type="INFO"
        )
    
    elif entity == "start_mode":
        start_mode = summary.get('start_mode')
        if start_mode:
            return LocalAnswer(
                answer=f"**Start Mode:** {start_mode}",
                confidence="high",
                data={"start_mode": start_mode},
                query_type="INFO"
            )
        return LocalAnswer(
            answer="Start mode information not found in the log.",
            confidence="low",
            query_type="INFO"
        )
    
    elif entity == "os_info":
        os_info = summary.get('os_info')
        if os_info:
            return LocalAnswer(
                answer=f"**Operating System:** {os_info}",
                confidence="high",
                data={"os_info": os_info},
                query_type="INFO"
            )
        return LocalAnswer(
            answer="Operating system information not found in the log.",
            confidence="low",
            query_type="INFO"
        )
    
    elif entity == "replication_status":
        full_load = summary.get('full_load_complete')
        cdc = summary.get('cdc_started')
        
        status_parts = []
        if full_load:
            status_parts.append("✅ Full Load: **Complete**")
        else:
            status_parts.append("⏳ Full Load: **Not Complete / In Progress**")
        
        if cdc:
            status_parts.append("✅ CDC (Change Data Capture): **Started**")
        else:
            status_parts.append("⏸️ CDC (Change Data Capture): **Not Started**")
        
        return LocalAnswer(
            answer="\n".join(status_parts),
            confidence="high",
            data={"full_load_complete": full_load, "cdc_started": cdc},
            query_type="INFO"
        )
    
    # Fallback - try to provide comprehensive task info
    parts = []
    if summary.get('task_name'):
        parts.append(f"**Task Name:** {summary['task_name']}")
    if summary.get('version'):
        parts.append(f"**Version:** {summary['version']}")
    if summary.get('source_endpoint'):
        parts.append(f"**Source:** {summary['source_endpoint']}")
    if summary.get('target_endpoint'):
        parts.append(f"**Target:** {summary['target_endpoint']}")
    if summary.get('running_mode'):
        parts.append(f"**Mode:** {summary['running_mode']}")
    
    if parts:
        return LocalAnswer(
            answer="\n".join(parts),
            confidence="medium",
            data=summary,
            query_type="INFO"
        )
    
    return None


def _handle_count_query(intent: QueryIntent, file_id: int, db: Session) -> Optional[LocalAnswer]:
    """Handle COUNT type questions."""
    entity = intent.entity
    
    if entity == "errors":
        count = db.query(func.count(LogError.id)).filter(
            LogError.file_id == file_id
        ).scalar() or 0
        
        return LocalAnswer(
            answer=f"Found **{count:,}** errors in the log file.",
            data={"error_count": count},
            query_type="COUNT_ERRORS"
        )
    
    elif entity == "tables":
        count = db.query(func.count(LogTableStats.id)).filter(
            LogTableStats.file_id == file_id
        ).scalar() or 0
        
        return LocalAnswer(
            answer=f"Found **{count}** tables in the log file.",
            data={"table_count": count},
            query_type="COUNT_TABLES"
        )
    
    elif entity == "batches":
        count = db.query(func.count(LogBatch.id)).filter(
            LogBatch.file_id == file_id
        ).scalar() or 0
        
        return LocalAnswer(
            answer=f"Found **{count:,}** batches in the log file.",
            data={"batch_count": count},
            query_type="COUNT_BATCHES"
        )
    
    elif entity == "operations":
        stats = db.query(LogTableStats).filter(
            LogTableStats.file_id == file_id
        ).all()
        
        totals = {
            "inserts": sum(t.total_inserts or 0 for t in stats),
            "updates": sum(t.total_updates or 0 for t in stats),
            "deletes": sum(t.total_deletes or 0 for t in stats),
            "merges": sum(t.total_merges or 0 for t in stats),
        }
        total_ops = sum(totals.values())
        
        return LocalAnswer(
            answer=f"Found **{total_ops:,}** total operations:\n"
                   f"- Inserts: {totals['inserts']:,}\n"
                   f"- Updates: {totals['updates']:,}\n"
                   f"- Deletes: {totals['deletes']:,}\n"
                   f"- Merges: {totals['merges']:,}",
            data=totals,
            query_type="COUNT_OPERATIONS"
        )
    
    elif entity == "lines":
        file = db.query(LogFile).filter(LogFile.id == file_id).first()
        if file:
            return LocalAnswer(
                answer=f"The log file has **{file.line_count:,}** lines.",
                data={"line_count": file.line_count},
                query_type="COUNT_LINES"
            )
    
    return None


def _handle_list_query(intent: QueryIntent, file_id: int, db: Session) -> Optional[LocalAnswer]:
    """Handle LIST type questions."""
    entity = intent.entity
    
    if entity == "tables":
        tables = db.query(LogTableStats).filter(
            LogTableStats.file_id == file_id
        ).order_by(LogTableStats.total_apply_time_seconds.desc()).all()
        
        if not tables:
            return LocalAnswer(
                answer="No tables found in the log file.",
                data={"tables": []},
                query_type="LIST_TABLES"
            )
        
        table_list = [t.table_name for t in tables]
        answer = f"Found **{len(tables)}** tables in the log:\n\n"
        for t in tables[:20]:  # Limit to top 20
            ops = (t.total_inserts or 0) + (t.total_updates or 0) + (t.total_deletes or 0) + (t.total_merges or 0)
            answer += f"- **{t.table_name}**: {ops:,} operations, {t.total_apply_time_seconds or 0:.1f}s apply time\n"
        
        if len(tables) > 20:
            answer += f"\n... and {len(tables) - 20} more tables."
        
        return LocalAnswer(
            answer=answer,
            data={"tables": table_list, "count": len(tables)},
            query_type="LIST_TABLES"
        )
    
    elif entity == "errors":
        errors = db.query(LogError).filter(
            LogError.file_id == file_id
        ).order_by(LogError.timestamp.desc()).limit(10).all()
        
        if not errors:
            return LocalAnswer(
                answer="No errors found in the log file.",
                data={"errors": []},
                query_type="LIST_ERRORS"
            )
        
        total_count = db.query(func.count(LogError.id)).filter(
            LogError.file_id == file_id
        ).scalar() or 0
        
        answer = f"Found **{total_count:,}** errors. Here are the most recent:\n\n"
        for e in errors:
            text_preview = (e.text or "")[:100] + "..." if len(e.text or "") > 100 else (e.text or "")
            answer += f"- Line {e.line_number}: `{text_preview}`\n"
        
        return LocalAnswer(
            answer=answer,
            data={"error_count": total_count, "sample_errors": [e.text for e in errors]},
            query_type="LIST_ERRORS"
        )
    
    elif entity == "components":
        stats = db.query(LogStats).filter(
            LogStats.file_id == file_id
        ).all()
        
        components = list(set(s.component for s in stats if s.component))
        
        if not components:
            return LocalAnswer(
                answer="No components found in the log file.",
                data={"components": []},
                query_type="LIST_COMPONENTS"
            )
        
        answer = f"Found **{len(components)}** components:\n\n"
        for comp in sorted(components):
            answer += f"- {comp}\n"
        
        return LocalAnswer(
            answer=answer,
            data={"components": components},
            query_type="LIST_COMPONENTS"
        )
    
    elif entity == "batch_reasons":
        batches = db.query(LogBatch).filter(
            LogBatch.file_id == file_id
        ).all()
        
        if not batches:
            return LocalAnswer(
                answer="No batch data found in the log file.",
                data={"closure_reasons": {}},
                query_type="LIST_BATCH_REASONS"
            )
        
        reasons = {}
        for b in batches:
            reason = b.closure_reason or "Unknown"
            reasons[reason] = reasons.get(reason, 0) + 1
        
        answer = f"Batch closure reasons ({len(batches):,} total batches):\n\n"
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            pct = (count / len(batches)) * 100
            answer += f"- **{reason}**: {count:,} ({pct:.1f}%)\n"
        
        return LocalAnswer(
            answer=answer,
            data={"closure_reasons": reasons, "total_batches": len(batches)},
            query_type="LIST_BATCH_REASONS"
        )
    
    return None


def _handle_stats_query(intent: QueryIntent, file_id: int, db: Session) -> Optional[LocalAnswer]:
    """Handle STATS type questions."""
    entity = intent.entity
    
    if entity in ("latency", "performance"):
        perf = db.query(LogPerformance).filter(
            LogPerformance.file_id == file_id
        ).all()
        
        if not perf:
            return LocalAnswer(
                answer="No performance data found in the log file.",
                data={},
                query_type="STATS_LATENCY"
            )
        
        # Calculate stats
        source_latencies = [p.source_latency for p in perf if p.source_latency is not None]
        handling_latencies = [p.handling_latency for p in perf if p.handling_latency is not None]
        target_latencies = [p.target_latency for p in perf if p.target_latency is not None]
        
        def calc_stats(values):
            if not values:
                return {"avg": 0, "max": 0, "min": 0, "count": 0}
            sorted_vals = sorted(values)
            return {
                "avg": sum(values) / len(values),
                "max": max(values),
                "min": min(values),
                "p95": sorted_vals[int(len(sorted_vals) * 0.95)] if len(sorted_vals) > 1 else sorted_vals[0],
                "count": len(values)
            }
        
        stats = {
            "source": calc_stats(source_latencies),
            "handling": calc_stats(handling_latencies),
            "target": calc_stats(target_latencies),
            "data_points": len(perf)
        }
        
        answer = f"**Latency Statistics** ({len(perf):,} data points):\n\n"
        answer += "| Component | Avg | Max | P95 |\n"
        answer += "|-----------|-----|-----|-----|\n"
        for comp in ["source", "handling", "target"]:
            s = stats[comp]
            answer += f"| {comp.title()} | {s['avg']:.2f}s | {s['max']:.2f}s | {s.get('p95', 0):.2f}s |\n"
        
        return LocalAnswer(
            answer=answer,
            data=stats,
            query_type="STATS_LATENCY"
        )
    
    elif entity == "bottleneck":
        perf = db.query(LogPerformance).filter(
            LogPerformance.file_id == file_id
        ).all()
        
        if not perf:
            return LocalAnswer(
                answer="No performance data available to determine bottleneck.",
                data={},
                query_type="STATS_BOTTLENECK"
            )
        
        # Calculate average latencies
        avg_source = sum(p.source_latency or 0 for p in perf) / len(perf)
        avg_handling = sum(p.handling_latency or 0 for p in perf) / len(perf)
        avg_target = sum(p.target_latency or 0 for p in perf) / len(perf)
        
        bottleneck = "source" if avg_source >= max(avg_handling, avg_target) else \
                    "handling" if avg_handling >= max(avg_source, avg_target) else "target"
        
        answer = f"**Primary Bottleneck: {bottleneck.upper()}**\n\n"
        answer += f"Average latencies:\n"
        answer += f"- Source: {avg_source:.2f}s\n"
        answer += f"- Handling: {avg_handling:.2f}s\n"
        answer += f"- Target: {avg_target:.2f}s\n"
        
        return LocalAnswer(
            answer=answer,
            data={"bottleneck": bottleneck, "avg_source": avg_source, 
                  "avg_handling": avg_handling, "avg_target": avg_target},
            query_type="STATS_BOTTLENECK"
        )
    
    return None


def _handle_search_query(intent: QueryIntent, file_id: int, db: Session) -> Optional[LocalAnswer]:
    """Handle SEARCH type questions - search raw log content."""
    entity = intent.entity
    question = intent.raw_question
    
    # Get the file path
    file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not file or not file.file_path:
        return None
    
    try:
        import os
        if not os.path.exists(file.file_path):
            return None
        
        if entity == "odbc_drivers":
            # Search for ODBC driver information
            with open(file.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(500000)  # First 500KB
            
            # Common ODBC driver patterns
            driver_patterns = [
                r"(?:ODBC|Driver).*?=.*?([^;}\n]+)",
                r"using\s+driver[:\s]+([^\n]+)",
                r"driver\s*:\s*([^\n]+)",
            ]
            
            drivers = set()
            for pattern in driver_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                drivers.update(m.strip() for m in matches if m.strip())
            
            if drivers:
                answer = f"Found **{len(drivers)}** ODBC driver references:\n\n"
                for d in sorted(drivers):
                    answer += f"- {d}\n"
                return LocalAnswer(answer=answer, data={"drivers": list(drivers)}, query_type="SEARCH_ODBC")
            else:
                return LocalAnswer(answer="No ODBC driver information found in the log.", data={}, query_type="SEARCH_ODBC")
        
        elif entity == "license":
            with open(file.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(100000)  # First 100KB typically has license info
            
            # Search for license lines
            license_pattern = r"Licensed to[^\n]+"
            matches = re.findall(license_pattern, content, re.IGNORECASE)
            
            if matches:
                answer = "**License Information:**\n\n"
                for m in matches[:5]:
                    answer += f"- {m}\n"
                return LocalAnswer(answer=answer, data={"license_lines": matches}, query_type="SEARCH_LICENSE")
            else:
                return LocalAnswer(answer="No license information found in the log.", data={}, query_type="SEARCH_LICENSE")
        
        elif entity == "version":
            with open(file.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(50000)  # First 50KB
            
            # Search for version info
            version_pattern = r"V\d+\.\d+\.\d+\.\d+"
            matches = re.findall(version_pattern, content)
            
            if matches:
                versions = list(set(matches))
                answer = f"**Version Information:** {', '.join(versions)}"
                return LocalAnswer(answer=answer, data={"versions": versions}, query_type="SEARCH_VERSION")
            else:
                return LocalAnswer(answer="No version information found in the log.", data={}, query_type="SEARCH_VERSION")
        
        elif entity == "connection_string":
            # Search for connection string information
            return _search_log_for_keywords(
                file.file_path, 
                ["connection string", "conn string", "DRIVER=", "DSN="], 
                question,
                file_id=file_id,
                db=db
            )
        
        elif entity == "generic_search":
            # Extract keywords from the question and search
            keywords = _extract_search_keywords(question)
            if keywords:
                return _search_log_for_keywords(
                    file.file_path, 
                    keywords, 
                    question,
                    file_id=file_id,
                    db=db
                )
            else:
                return LocalAnswer(
                    answer="I couldn't identify what to search for. Try asking: 'anything about [keyword]?' or 'find [keyword] in the log'",
                    confidence="low",
                    query_type="SEARCH_GENERIC"
                )
    
    except Exception as e:
        logger.warning(f"Search query failed: {e}")
        return None
    
    return None


def _extract_search_keywords(question: str) -> List[str]:
    """
    Extract search keywords from a natural language question.
    Examples:
    - "anything about connection string?" -> ["connection string"]
    - "find timeout errors in the log" -> ["timeout", "errors"]
    - "is there any mention of deadlock?" -> ["deadlock"]
    """
    q_lower = question.lower()
    
    # Patterns to extract the subject of the search
    extraction_patterns = [
        r"anything (?:about|on|regarding|related to|with) ['\"]?(.+?)['\"]?\??$",
        r"anything (?:about|on|regarding|related to|with) (.+?)(?:\?|$| in the)",
        r"find ['\"]?(.+?)['\"]? in (?:the |this )?log",
        r"search (?:for |the log for )['\"]?(.+?)['\"]?(?:\?|$)",
        r"is there (?:any |a )?(?:mention|reference|info|information) (?:of|about|on) ['\"]?(.+?)['\"]?\??$",
        r"(?:can you |do you |)(?:find|see|show) ['\"]?(.+?)['\"]? in (?:the |this )?log",
        r"look for ['\"]?(.+?)['\"]?(?:\?|$| in)",
        r"(?:any|some) (?:mention|info|information|reference) (?:of|about) ['\"]?(.+?)['\"]?\??$",
    ]
    
    for pattern in extraction_patterns:
        match = re.search(pattern, q_lower)
        if match:
            keyword = match.group(1).strip()
            # Clean up common stop words from the end
            keyword = re.sub(r'\s+(in the log|in log|please|thanks)$', '', keyword)
            if keyword and len(keyword) > 2:
                # Split multi-word phrases but keep them as one keyword too
                words = keyword.split()
                if len(words) > 1:
                    return [keyword]  # Keep phrase together
                return [keyword]
    
    # Fallback: look for quoted strings
    quoted = re.findall(r'["\']([^"\']+)["\']', question)
    if quoted:
        return quoted
    
    # Last resort: extract nouns/technical terms after common patterns
    tech_terms = re.findall(r'\b(connection string|timeout|deadlock|error|warning|exception|failure|latency|bulk|batch|cdc|full load|endpoint|driver|odbc|sql|insert|update|delete|merge|table|schema)\b', q_lower)
    if tech_terms:
        return list(set(tech_terms))
    
    return []


def _search_analysis_reports(file_id: int, keywords: List[str], db: Session) -> List[Dict[str, Any]]:
    """
    Search through existing analysis reports (AI summaries, etc.) for keyword matches.
    Returns list of matching sections with source attribution.
    """
    from backend.database import LLMReport
    
    matches = []
    
    # Get all reports for this file
    reports = db.query(LLMReport).filter(LLMReport.file_id == file_id).all()
    
    for report in reports:
        if not report.report_content:
            continue
        
        content = report.report_content
        content_lower = content.lower()
        
        # Check if any keyword is in the report
        for keyword in keywords:
            if keyword.lower() in content_lower:
                # Find the paragraph/section containing the keyword
                paragraphs = content.split('\n\n')
                for para in paragraphs:
                    if keyword.lower() in para.lower() and len(para.strip()) > 20:
                        # Clean up the paragraph
                        clean_para = para.strip()
                        if len(clean_para) > 500:
                            # Find the sentence containing the keyword
                            sentences = re.split(r'(?<=[.!?])\s+', clean_para)
                            for sentence in sentences:
                                if keyword.lower() in sentence.lower():
                                    clean_para = sentence.strip()
                                    break
                        
                        matches.append({
                            'source': 'AI Analysis Report',
                            'content': clean_para,
                            'keyword': keyword,
                            'report_id': report.id
                        })
                        break  # One match per keyword per report
    
    return matches


def _search_error_entries(file_id: int, keywords: List[str], db: Session) -> List[Dict[str, Any]]:
    """
    Search through indexed error entries for keyword matches.
    """
    matches = []
    
    errors = db.query(LogError).filter(LogError.file_id == file_id).all()
    
    for error in errors:
        if not error.text:
            continue
        
        text_lower = error.text.lower()
        for keyword in keywords:
            if keyword.lower() in text_lower:
                matches.append({
                    'source': 'Error Log',
                    'line_num': error.line_number,
                    'content': error.text.strip(),
                    'keyword': keyword
                })
                break
    
    return matches[:5]  # Limit to 5 error matches


def _search_log_for_keywords(file_path: str, keywords: List[str], original_question: str, 
                              file_id: int = None, db: Session = None) -> Optional[LocalAnswer]:
    """
    Search log file and analysis reports for lines containing any of the keywords.
    Returns formatted answer with matching lines, prioritizing report quotes.
    """
    all_sources = []
    report_matches = []
    error_matches = []
    log_matches = []
    
    # FIRST: Search existing analysis reports (if db available)
    if db and file_id:
        report_matches = _search_analysis_reports(file_id, keywords, db)
        error_matches = _search_error_entries(file_id, keywords, db)
    
    # SECOND: Search raw log file
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        seen_content = set()  # Deduplicate similar lines
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            for keyword in keywords:
                if keyword.lower() in line_lower:
                    # Normalize the line for deduplication
                    normalized = re.sub(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', '', line)
                    normalized = re.sub(r'[0-9a-fA-F]{8}:', '', normalized).strip()
                    
                    if normalized not in seen_content:
                        seen_content.add(normalized)
                        log_matches.append({
                            'source': 'Raw Log',
                            'line_num': i + 1,
                            'content': line.strip(),
                            'keyword': keyword
                        })
                    break
            
            # Limit log matches
            if len(log_matches) >= 8:
                break
    
    except Exception as e:
        logger.warning(f"Log file search failed: {e}")
    
    # Build combined answer
    keyword_display = ', '.join(f'**{k}**' for k in keywords)
    total_matches = len(report_matches) + len(error_matches) + len(log_matches)
    
    if total_matches == 0:
        return LocalAnswer(
            answer=f"No information found about {keyword_display} in the log or analysis reports.",
            confidence="high",
            data={"keywords": keywords, "matches": []},
            query_type="SEARCH_GENERIC"
        )
    
    answer_parts = [f"Found information about {keyword_display}:\n"]
    
    # Add report matches first (highest priority - already analyzed)
    if report_matches:
        answer_parts.append("\n### 📊 From Analysis Reports:\n")
        for match in report_matches[:3]:  # Limit to 3
            content = match['content']
            if len(content) > 300:
                content = content[:300] + "..."
            answer_parts.append(f"> {content}\n")
            answer_parts.append(f"*— Source: {match['source']}*\n\n")
    
    # Add error matches
    if error_matches:
        answer_parts.append("\n### ⚠️ From Error Entries:\n")
        for match in error_matches[:3]:
            content = match['content']
            if len(content) > 200:
                content = content[:200] + "..."
            answer_parts.append(f"**Line {match['line_num']}:**\n```\n{content}\n```\n\n")
    
    # Add raw log matches
    if log_matches:
        answer_parts.append("\n### 📄 From Raw Log:\n")
        for match in log_matches[:5]:
            content = match['content']
            if len(content) > 200:
                content = content[:200] + "..."
            answer_parts.append(f"**Line {match['line_num']}:**\n```\n{content}\n```\n\n")
    
    return LocalAnswer(
        answer=''.join(answer_parts),
        confidence="high",
        data={
            "keywords": keywords,
            "report_matches": len(report_matches),
            "error_matches": len(error_matches),
            "log_matches": len(log_matches)
        },
        query_type="SEARCH_GENERIC"
    )


def _handle_time_query(intent: QueryIntent, file_id: int, db: Session) -> Optional[LocalAnswer]:
    """Handle TIME type questions."""
    # Get first and last timestamps from performance data
    first_perf = db.query(LogPerformance).filter(
        LogPerformance.file_id == file_id
    ).order_by(LogPerformance.timestamp.asc()).first()
    
    last_perf = db.query(LogPerformance).filter(
        LogPerformance.file_id == file_id
    ).order_by(LogPerformance.timestamp.desc()).first()
    
    if not first_perf or not last_perf:
        # Try errors table
        first_err = db.query(LogError).filter(
            LogError.file_id == file_id
        ).order_by(LogError.timestamp.asc()).first()
        
        last_err = db.query(LogError).filter(
            LogError.file_id == file_id
        ).order_by(LogError.timestamp.desc()).first()
        
        if first_err and last_err:
            duration = (last_err.timestamp - first_err.timestamp).total_seconds() if last_err.timestamp and first_err.timestamp else 0
            answer = f"**Log Time Range:**\n\n"
            answer += f"- Start: {first_err.timestamp}\n"
            answer += f"- End: {last_err.timestamp}\n"
            answer += f"- Duration: {duration/3600:.1f} hours ({duration/60:.0f} minutes)"
            return LocalAnswer(answer=answer, data={
                "start_time": str(first_err.timestamp),
                "end_time": str(last_err.timestamp),
                "duration_seconds": duration
            }, query_type="TIME_RANGE")
        
        return LocalAnswer(answer="No timestamp data found in the log.", data={}, query_type="TIME_RANGE")
    
    duration = (last_perf.timestamp - first_perf.timestamp).total_seconds() if last_perf.timestamp and first_perf.timestamp else 0
    
    answer = f"**Log Time Range:**\n\n"
    answer += f"- Start: {first_perf.timestamp}\n"
    answer += f"- End: {last_perf.timestamp}\n"
    answer += f"- Duration: {duration/3600:.1f} hours ({duration/60:.0f} minutes)"
    
    return LocalAnswer(
        answer=answer,
        data={
            "start_time": str(first_perf.timestamp),
            "end_time": str(last_perf.timestamp),
            "duration_seconds": duration
        },
        query_type="TIME_RANGE"
    )


def _handle_summary_query(intent: QueryIntent, file_id: int, db: Session) -> Optional[LocalAnswer]:
    """Handle SUMMARY type questions - provide an overview."""
    file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not file:
        return None
    
    # Gather all stats
    error_count = db.query(func.count(LogError.id)).filter(LogError.file_id == file_id).scalar() or 0
    table_count = db.query(func.count(LogTableStats.id)).filter(LogTableStats.file_id == file_id).scalar() or 0
    batch_count = db.query(func.count(LogBatch.id)).filter(LogBatch.file_id == file_id).scalar() or 0
    perf_count = db.query(func.count(LogPerformance.id)).filter(LogPerformance.file_id == file_id).scalar() or 0
    
    # Get operation totals
    table_stats = db.query(LogTableStats).filter(LogTableStats.file_id == file_id).all()
    total_ops = sum(
        (t.total_inserts or 0) + (t.total_updates or 0) + 
        (t.total_deletes or 0) + (t.total_merges or 0) 
        for t in table_stats
    )
    
    # Health assessment based on error count and performance
    health = "Healthy" if error_count < 10 else "Warning" if error_count < 100 else "Critical"
    
    answer = f"## Log Summary: {file.filename}\n\n"
    answer += f"**Health Status: {health}**\n\n"
    answer += f"### Overview\n"
    answer += f"- **File Size:** {file.size_bytes:,} bytes\n"
    answer += f"- **Lines:** {file.line_count:,}\n"
    answer += f"- **Tables:** {table_count}\n"
    answer += f"- **Batches:** {batch_count:,}\n"
    answer += f"- **Total Operations:** {total_ops:,}\n"
    answer += f"- **Errors:** {error_count:,}\n"
    answer += f"- **Performance Data Points:** {perf_count:,}\n"
    
    return LocalAnswer(
        answer=answer,
        data={
            "filename": file.filename,
            "health": health,
            "error_count": error_count,
            "table_count": table_count,
            "batch_count": batch_count,
            "total_operations": total_ops,
            "line_count": file.line_count
        },
        query_type="SUMMARY"
    )


# =============================================================================
# Utility Functions
# =============================================================================

def get_answer_mode(question: str) -> AnswerMode:
    """
    Quickly determine the answer mode for a question.
    
    Returns:
        AnswerMode enum value
    """
    mode, _ = classify_intent(question)
    return mode
