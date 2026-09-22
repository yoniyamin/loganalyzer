"""
Report Generator - Orchestrates RAG Retrieval and LLM Report Generation

This module ties together:
1. SQLite data retrieval (performance summaries)
2. ChromaDB context retrieval (errors, anomalies)
3. LLM completion for report generation
"""

import base64
import json
import logging
import time as _time
import traceback
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from backend.database import (
    LogFile, LogPerformance, LogError, LogStats,
    LogBatch, LogTableStats, LogTaskConfig, LogSorterEvent, LogOracleRedoRead, LogOracleRedoLogSession,
    LogLineMeta, LLMConfig,
)
from backend.core.analysis import PerformanceCockpit
from backend.core.extractors import analyze_full_load_file, condense_full_load_for_llm
from backend.llm.vectorstore import get_vector_store, LogVectorStore
from backend.llm.client import get_llm_client, OpenRouterClient, DEFAULT_MODEL, openrouter_model_supports_vision
from backend.llm.gemini_client import get_gemini_client, GeminiClient, DEFAULT_GEMINI_MODEL, gemini_model_supports_vision
from backend.llm.lmstudio_client import get_lmstudio_client, LMStudioClient, DEFAULT_LMSTUDIO_BASE_URL, LMSTUDIO_DEFAULT_MAX_TOKENS, LMSTUDIO_REPORT_MAX_TEMPERATURE
from backend.llm.openai_api_client import (
    get_openai_api_client,
    OpenAIApiClient,
    DEFAULT_OPENAI_API_BASE_URL,
    OPENAI_API_DEFAULT_MAX_TOKENS,
    OPENAI_API_REPORT_MAX_TEMPERATURE,
)
from backend.llm.prompts import (
    get_messages_for_analysis,
    count_prompt_tokens,
    sanitize_dict,
    sanitize_list,
    extract_error_codes_for_prompt,
)
from backend.llm.tavily_client import TavilyClient

# Configure logging
logger = logging.getLogger(__name__)

# Provider constants
PROVIDER_GEMINI = "gemini"
PROVIDER_OPENROUTER = "openrouter"
PROVIDER_LMSTUDIO = "lmstudio"
PROVIDER_OPENAI_API = "openai_api"
LOCAL_LLM_PROVIDERS = frozenset({PROVIDER_LMSTUDIO, PROVIDER_OPENAI_API})

# Brief pause before retrying local LLMs that return empty on first FLM request.
LOCAL_EMPTY_RESPONSE_RETRY_DELAY_SECONDS = 0.5


def _is_empty_completion(result) -> bool:
    return not (getattr(result, "content", None) or "").strip()


# ---------------------------------------------------------------------------
# In-memory progress tracking (keyed by file_id)
# ---------------------------------------------------------------------------
import threading
import time as _time

from backend.llm.generation_cancel import GenerationCancelled, begin as begin_generation, check_cancelled, clear as clear_generation_cancel

_progress_lock = threading.Lock()
_progress_store: Dict[int, Dict[str, Any]] = {}


def set_progress(file_id: int, phase: str, detail: str = "", **extra):
    with _progress_lock:
        _progress_store[file_id] = {
            "phase": phase,
            "detail": detail,
            "updated_at": _time.time(),
            **extra,
        }


def get_progress(file_id: int) -> Optional[Dict[str, Any]]:
    with _progress_lock:
        return _progress_store.get(file_id)


def clear_progress(file_id: int):
    with _progress_lock:
        _progress_store.pop(file_id, None)


@dataclass
class ReportPromptBundle:
    """All data needed to execute (or preview) a report LLM call."""
    messages: List[Dict[str, str]]
    est_tokens: int
    context_stats: Dict[str, int] = field(default_factory=dict)
    prompt_text: str = ""
    provider: str = ""
    compact: bool = False
    focus_mode: Optional[str] = None
    web_search: bool = False
    quick: bool = False
    chart_image_data: Optional[bytes] = None
    kb_context: List[Dict[str, Any]] = field(default_factory=list)
    release_notes_context: List[Dict[str, Any]] = field(default_factory=list)
    payload_format: str = "markdown"


class ReportGenerator:
    """
    Generates LLM-powered analysis reports for log files.
    
    Workflow:
    1. Fetch structured data from SQLite
    2. Build performance cockpit summary
    3. Retrieve relevant context from ChromaDB
    4. Generate report via Gemini or OpenRouter LLM
    """
    
    def __init__(
        self,
        db: Session,
        vector_store: Optional[LogVectorStore] = None,
        llm_client: Optional[OpenRouterClient] = None,
        gemini_client: Optional[GeminiClient] = None,
        lmstudio_client: Optional[LMStudioClient] = None,
        openai_api_client: Optional[OpenAIApiClient] = None,
    ):
        """
        Initialize the report generator.
        
        Args:
            db: SQLAlchemy database session
            vector_store: Optional vector store instance (uses singleton if not provided)
            llm_client: Optional OpenRouter LLM client instance
            gemini_client: Optional Gemini client instance
            lmstudio_client: Optional LM Studio client instance
            openai_api_client: Optional OpenAI-compatible local client instance
        """
        self.db = db
        self.vector_store = vector_store or get_vector_store()
        self.llm_client = llm_client or get_llm_client()
        self.gemini_client = gemini_client or get_gemini_client()
        self.lmstudio_client = lmstudio_client or get_lmstudio_client()
        self.openai_api_client = openai_api_client or get_openai_api_client()
        
        # Get provider preference from config; sync local server URLs and parameters
        config = self.db.query(LLMConfig).first()
        self.provider = (config.provider or PROVIDER_GEMINI).strip().lower() if config else PROVIDER_GEMINI
        if config and self.provider == PROVIDER_LMSTUDIO:
            lmstudio_url = getattr(config, "lmstudio_base_url", None) or DEFAULT_LMSTUDIO_BASE_URL
            self.lmstudio_client.set_base_url(lmstudio_url)
        if config and self.provider == PROVIDER_OPENAI_API:
            oa_url = getattr(config, "openai_api_base_url", None) or DEFAULT_OPENAI_API_BASE_URL
            self.openai_api_client.set_base_url(oa_url)
            encrypted_key = getattr(config, "openai_api_key_encrypted", None)
            if encrypted_key:
                try:
                    key = base64.b64decode(encrypted_key.encode()).decode().strip()
                    if key:
                        self.openai_api_client.set_api_key(key)
                except Exception:
                    pass
        # Store user-configured overrides (None = use hardcoded defaults)
        self.lmstudio_temperature: Optional[float] = getattr(config, "lmstudio_temperature", None) if config else None
        self.lmstudio_max_tokens: Optional[int] = getattr(config, "lmstudio_max_tokens", None) if config else None
        self.openai_api_temperature: Optional[float] = getattr(config, "openai_api_temperature", None) if config else None
        self.openai_api_max_tokens: Optional[int] = getattr(config, "openai_api_max_tokens", None) if config else None
        if self.provider in LOCAL_LLM_PROVIDERS:
            self.sanitize_log_payload = False
        else:
            cloud_raw = getattr(config, "sanitize_log_for_cloud_llm", True) if config else True
            self.sanitize_log_payload = bool(cloud_raw) if cloud_raw is not None else True
    
    def get_file_info(self, file_id: int) -> Optional[Dict[str, Any]]:
        """Get basic file information."""
        file = self.db.query(LogFile).filter(LogFile.id == file_id).first()
        if not file:
            return None
        
        return {
            "id": file.id,
            "filename": file.filename,
            "size_bytes": file.size_bytes,
            "line_count": file.line_count,
            "status": file.status
        }
    
    def _sanitize_log_bundle(
        self,
        summary: Dict[str, Any],
        merged_errors: List[str],
        anomalies: List[str],
        file_info: Optional[Dict[str, Any]],
    ):
        """Apply PII redaction to report prompt inputs when `sanitize_log_payload` is enabled."""
        if self.sanitize_log_payload:
            return (
                sanitize_dict(summary),
                sanitize_list(merged_errors),
                sanitize_list(anomalies),
                sanitize_dict(file_info) if file_info else None,
            )
        return summary, merged_errors, anomalies, file_info
    
    def build_performance_summary(self, file_id: int) -> Dict[str, Any]:
        """
        Build the performance cockpit summary from database.
        
        Args:
            file_id: ID of the log file
        
        Returns:
            Performance cockpit summary dictionary
        """
        # Fetch performance data
        perf_records = self.db.query(LogPerformance).filter(
            LogPerformance.file_id == file_id
        ).order_by(LogPerformance.timestamp).all()
        
        performance_data = [
            {
                "timestamp": p.timestamp,
                "source_latency": p.source_latency,
                "handling_latency": p.handling_latency,
                "target_latency": p.target_latency,
                "line_number": p.line_number
            }
            for p in perf_records
        ]
        
        # Fetch batches
        batches = self.db.query(LogBatch).filter(
            LogBatch.file_id == file_id
        ).all()
        
        batch_data = [
            {
                "closure_reason": b.closure_reason,
                "duration_seconds": b.duration_seconds,
                "changes_count": b.changes_count,
                "tables": b.tables
            }
            for b in batches
        ]
        
        # Fetch table stats
        table_stats = self.db.query(LogTableStats).filter(
            LogTableStats.file_id == file_id
        ).all()
        
        table_stats_data = [
            {
                "table_name": t.table_name,
                "total_inserts": t.total_inserts,
                "total_updates": t.total_updates,
                "total_deletes": t.total_deletes,
                "total_merges": t.total_merges,
                "total_apply_time_seconds": t.total_apply_time_seconds,
                "avg_apply_time_seconds": t.avg_apply_time_seconds,
                "max_apply_time_seconds": t.max_apply_time_seconds,
                "one_by_one_count": t.one_by_one_count,
                "has_pk": t.has_pk,
                "error_count": t.error_count
            }
            for t in table_stats
        ]
        
        # Fetch errors
        errors = self.db.query(LogError).filter(
            LogError.file_id == file_id
        ).all()
        
        error_data = [
            {
                "timestamp": e.timestamp,
                "component": e.component,
                "text": e.text,
                "line_number": e.line_number
            }
            for e in errors
        ]
        
        # Fetch sorter events
        sorter_events = self.db.query(LogSorterEvent).filter(
            LogSorterEvent.file_id == file_id
        ).all()
        
        sorter_data = [
            {
                "event_type": s.event_type,
                "timestamp": s.timestamp,
                "value": s.value,
                "details": s.details
            }
            for s in sorter_events
        ]
        
        config_data = self._get_task_config_dict(file_id)
        
        oracle_rows = self.db.query(LogOracleRedoRead).filter(
            LogOracleRedoRead.file_id == file_id
        ).all()
        oracle_redo_reads = [
            {
                "timestamp": r.timestamp,
                "line_number": r.line_number,
                "thread_id": r.thread_id,
                "bytes_read": r.bytes_read,
                "read_ms": r.read_ms,
                "source_location": r.source_location,
            }
            for r in oracle_rows
        ]
        
        session_rows = self.db.query(LogOracleRedoLogSession).filter(
            LogOracleRedoLogSession.file_id == file_id
        ).all()
        oracle_redo_log_sessions = [
            {
                "thread_id": s.thread_id,
                "redo_path": s.redo_path,
                "line_open": s.line_open,
                "line_close": s.line_close,
                "timestamp_open": s.timestamp_open,
                "timestamp_close": s.timestamp_close,
                "duration_seconds": s.duration_seconds,
            }
            for s in session_rows
        ]
        
        # Build performance cockpit
        if performance_data or oracle_redo_reads or oracle_redo_log_sessions:
            cockpit = PerformanceCockpit(
                performance_data=performance_data,
                batches=batch_data,
                table_stats=table_stats_data,
                errors=error_data,
                config=config_data,
                sorter_events=sorter_data,
                oracle_redo_reads=oracle_redo_reads,
                oracle_redo_log_sessions=oracle_redo_log_sessions,
            )
            summary = cockpit.generate_summary()
        else:
            # Return minimal summary if no performance data
            summary = {
                "latency_profile": {"data_points": 0},
                "bottleneck": {"primary": "unknown"},
                "spikes": {"count": 0, "items": []},
                "plateaus": {"count": 0, "items": []},
                "batch_profile": {"total_batches": len(batch_data)},
                "error_summary": {"total": len(error_data)},
                "recommendations": [],
                "config": config_data,
                "oracle_redo_read_analysis": {
                    "total_events": 0,
                    "has_red_flags": False,
                    "high_variance_groups": [],
                },
                "oracle_redo_log_processing": {
                    "session_count": 0,
                    "duration_seconds_stats": None,
                    "longest_sessions": [],
                },
            }

        fl_ctx = self._build_full_load_context(file_id)
        if fl_ctx:
            summary["full_load_activity"] = fl_ctx
        return summary

    def _build_full_load_context(self, file_id: int) -> Optional[Dict[str, Any]]:
        """Scan the raw log for full-load activity and return condensed LLM context."""
        try:
            f = self.db.query(LogFile).filter(LogFile.id == file_id).first()
            if not f or not f.file_path:
                return None
            import os
            if not os.path.exists(f.file_path):
                return None
            report = analyze_full_load_file(f.file_path)
            return condense_full_load_for_llm(report)
        except Exception as e:
            logger.warning(f"Full load context unavailable for file_id={file_id}: {e}")
            return None
    
    def embed_file_content(self, file_id: int) -> Dict[str, int]:
        """
        Embed log file content into the vector store.
        
        This includes:
        - Performance summary
        - Error contexts
        - Detected anomalies
        
        Args:
            file_id: ID of the log file
        
        Returns:
            Dictionary with counts of embedded items
        """
        counts = {"summaries": 0, "errors": 0, "anomalies": 0}
        
        # Get and embed performance summary
        summary = self.build_performance_summary(file_id)
        
        self.vector_store.add_summary(file_id, summary, "performance_cockpit")
        counts["summaries"] += 1
        
        # Embed batch analysis separately
        if "batch_profile" in summary:
            self.vector_store.add_summary(
                file_id,
                {"batch_profile": summary["batch_profile"], "batch_issues": summary.get("batch_issues", [])},
                "batch_analysis"
            )
            counts["summaries"] += 1

        # Embed full-load activity separately when present
        fl = summary.get("full_load_activity")
        if fl and fl.get("available"):
            self.vector_store.add_summary(file_id, fl, "full_load_activity")
            counts["summaries"] += 1
        
        # Embed error contexts
        errors = self.db.query(LogError).filter(
            LogError.file_id == file_id
        ).limit(50).all()  # Limit to avoid too many embeddings
        
        for error in errors:
            self.vector_store.add_error_context(
                file_id=file_id,
                error_text=error.text or "",
                context_before=[],  # We don't have context stored in DB
                context_after=[],
                line_number=error.line_number,
                component=error.component,
                timestamp=error.timestamp.isoformat() if error.timestamp else None
            )
            counts["errors"] += 1
        
        # Embed anomalies (spikes and plateaus)
        if "spikes" in summary and summary["spikes"].get("items"):
            for i, spike in enumerate(summary["spikes"]["items"][:10]):
                self.vector_store.add_anomaly(
                    file_id=file_id,
                    anomaly_type="latency_spike",
                    description=f"Latency spike of {spike.get('value', 0):.1f}s "
                               f"({spike.get('multiplier', 0):.1f}x baseline) "
                               f"driven by {spike.get('driver', 'unknown')}",
                    details=spike,
                    line_numbers=[spike.get('line_number')] if spike.get('line_number') else None
                )
                counts["anomalies"] += 1
        
        if "plateaus" in summary and summary["plateaus"].get("items"):
            for plateau in summary["plateaus"]["items"][:5]:
                self.vector_store.add_anomaly(
                    file_id=file_id,
                    anomaly_type="latency_plateau",
                    description=f"Sustained high latency of {plateau.get('avg_latency', 0):.1f}s "
                               f"for {plateau.get('duration_points', 0)} readings",
                    details=plateau,
                    line_numbers=[plateau.get('start_line'), plateau.get('end_line')]
                )
                counts["anomalies"] += 1
        
        return counts
    
    def _get_task_config_dict(self, file_id: int) -> Dict[str, Any]:
        """Full task configuration extracted at indexing time."""
        config = self.db.query(LogTaskConfig).filter(
            LogTaskConfig.file_id == file_id
        ).first()
        if not config:
            return {}
        return {
            "bulk_timeout_ms": config.bulk_timeout_ms,
            "bulk_timeout_min_ms": config.bulk_timeout_min_ms,
            "bulk_max_file_size_kb": config.bulk_max_file_size_kb,
            "parallel_apply_threads": config.parallel_apply_threads,
            "stream_buffer_size": config.stream_buffer_size,
            "stream_buffers_number": config.stream_buffers_number,
            "stop_on_memory_limit": config.stop_on_memory_limit,
            "target_type": config.target_type,
            "source_type": config.source_type,
            "apply_mode": config.apply_mode,
            "merge_enabled": config.merge_enabled,
        }

    def _get_endpoint_types(self, file_id: int, summary: Dict[str, Any]) -> Dict[str, str]:
        """Extract source/target endpoint types from task config or summary."""
        cfg = summary.get("config") or self._get_task_config_dict(file_id)
        source_type = cfg.get("source_type") or ""
        target_type = cfg.get("target_type") or ""

        if not source_type and "source_analysis" in summary:
            source_type = summary["source_analysis"].get("source_type", "")
        if not target_type and "target_analysis" in summary:
            target_type = summary["target_analysis"].get("target_type", "")

        return {"source": source_type, "target": target_type}

    def _sqlite_error_excerpts(self, file_id: int, limit: int = 40) -> List[str]:
        """Structured error lines from SQLite (always include in LLM prompt)."""
        rows = (
            self.db.query(LogError)
            .filter(LogError.file_id == file_id)
            .order_by(LogError.line_number.asc())
            .limit(limit)
            .all()
        )
        out: List[str] = []
        for e in rows:
            body = (e.text or "").strip()
            if not body:
                continue
            ts = e.timestamp.strftime("%Y-%m-%d %H:%M:%S") if e.timestamp else ""
            comp = e.component or "UNKNOWN"
            line = e.line_number if e.line_number is not None else "?"
            body_one = " ".join(body.split())
            if len(body_one) > 3500:
                body_one = body_one[:3497] + "..."
            out.append(f"LINE {line} | {ts} | {comp}\n{body_one}")
        return out

    def _warning_excerpts_from_meta(self, file_id: int, limit: int = 15) -> List[str]:
        """Fetch recent warning lines via LogLineMeta severity=W."""
        rows = (
            self.db.query(LogLineMeta)
            .filter(LogLineMeta.file_id == file_id, LogLineMeta.severity == "W")
            .order_by(LogLineMeta.line_number.desc())
            .limit(limit)
            .all()
        )
        if not rows:
            return []

        from backend.core.reader import LogReader

        try:
            reader = LogReader(self.db, file_id)
        except ValueError:
            return []

        out: List[str] = []
        for row in reversed(rows):
            try:
                ctx = reader.read_lines_centered(row.line_number, before=0, after=0)
                lines = ctx.get("lines") or []
                body = lines[0].strip() if lines else ""
            except Exception:
                body = ""
            if not body:
                continue
            ts = row.timestamp.strftime("%Y-%m-%d %H:%M:%S") if row.timestamp else ""
            comp = row.component or "UNKNOWN"
            body_one = " ".join(body.split())
            if len(body_one) > 3500:
                body_one = body_one[:3497] + "..."
            out.append(f"LINE {row.line_number} | {ts} | {comp}\n{body_one}")
        return out

    def merge_error_contexts(
        self,
        file_id: int,
        rag_errors: Optional[List[str]],
        cap: int = 30,
        focus_mode: Optional[str] = None,
    ) -> List[str]:
        """Prefer SQLite rows (full text + line) then unique RAG chunks."""
        primary = self._sqlite_error_excerpts(file_id)
        warning_meta = (
            self._warning_excerpts_from_meta(file_id, limit=20)
            if focus_mode == "errors"
            else []
        )
        merged: List[str] = []
        seen: set[str] = set()
        sources = warning_meta + primary + (rag_errors or [])
        for block in sources:
            if not block or not str(block).strip():
                continue
            key = str(block)[:240].lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(str(block))
            if len(merged) >= cap:
                break
        return merged

    def _distinct_error_snippets(self, file_id: int, max_snippets: int = 6) -> List[str]:
        """Short unique message snippets to drive KB / semantic search."""
        rows = (
            self.db.query(LogError)
            .filter(LogError.file_id == file_id)
            .order_by(LogError.line_number.asc())
            .limit(45)
            .all()
        )
        out: List[str] = []
        seen: set[str] = set()
        for r in rows:
            t = (r.text or "").strip().replace("\n", " ")
            if len(t) < 18:
                continue
            sig = t[:80].lower()
            if sig in seen:
                continue
            seen.add(sig)
            out.append(t[:240])
            if len(out) >= max_snippets:
                break
        return out

    def get_release_notes_context(
        self,
        file_id: int,
        summary: Dict[str, Any],
        max_results: int = 8
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant release notes from the indexed collection and
        optionally supplement with a live Tavily web search.

        Returns a de-duplicated list of release note entries.
        """
        endpoints = self._get_endpoint_types(file_id, summary)
        source_type = endpoints["source"]
        target_type = endpoints["target"]

        queries = []
        if source_type:
            queries.append(f"Qlik Replicate {source_type} source endpoint new feature enhancement")
        if target_type:
            queries.append(f"Qlik Replicate {target_type} target endpoint new feature enhancement")

        error_summary = summary.get("error_summary", {})
        if error_summary.get("by_component"):
            top_components = sorted(
                error_summary["by_component"].items(), key=lambda x: x[1], reverse=True
            )[:2]
            for comp, _ in top_components:
                queries.append(f"Qlik Replicate {comp} fix improvement")

        if not queries:
            queries = ["Qlik Replicate new feature improvement enhancement"]

        results = []
        seen_urls = set()

        endpoint_filter = source_type or target_type or None
        per_query = max(3, max_results // len(queries) + 1)

        for q in queries:
            try:
                hits = self.vector_store.query_release_notes(
                    query=q,
                    n_results=per_query,
                    endpoint_filter=endpoint_filter,
                )
                for h in hits:
                    url = h.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        results.append(h)
            except Exception as e:
                logger.debug(f"Release notes query failed for '{q}': {e}")

        # Broader fallback without endpoint filter if too few results
        if len(results) < 3 and endpoint_filter:
            for q in queries[:2]:
                try:
                    hits = self.vector_store.query_release_notes(query=q, n_results=per_query)
                    for h in hits:
                        url = h.get("url", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            results.append(h)
                except Exception:
                    pass

        # Tavily supplement
        try:
            tavily = TavilyClient()
            if tavily.is_configured and (source_type or target_type):
                parts = ["Qlik Replicate release notes fix"]
                if source_type:
                    parts.append(source_type)
                if target_type:
                    parts.append(target_type)
                tavily_query = " ".join(parts)

                tavily_result = tavily.advanced_answer(
                    query=tavily_query, max_results=3, search_depth="basic"
                )
                for src in tavily_result.get("results", []):
                    url = src.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        results.append({
                            "content": src.get("content", ""),
                            "title": src.get("title", "Web result"),
                            "url": url,
                            "version": "",
                            "fix_id": "",
                            "similarity": 0.5,
                            "metadata": {"source": "tavily_web_search"},
                        })
        except Exception as e:
            logger.debug(f"Tavily release notes search failed: {e}")

        results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        return results[:max_results]

    def get_kb_context(
        self,
        file_id: int,
        summary: Dict[str, Any],
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Query the KB for articles relevant to detected errors, endpoint
        types, and performance symptoms.

        Uses a multi-strategy approach:
        1. Error code queries (most precise — short codes embed well)
        2. Symptom keyword queries (extracted from error text, not raw log)
        3. Endpoint + component queries (contextual)
        4. Performance symptom queries (when telemetry present)
        """
        import re

        queries_high: List[str] = []   # precise, run first
        queries_medium: List[str] = [] # symptom-level
        queries_broad: List[str] = []  # contextual / fallback

        endpoints = self._get_endpoint_types(file_id, summary)
        source_type = endpoints["source"]
        target_type = endpoints["target"]

        # --- Strategy 1: Error code-based queries (high precision) ---
        error_snippets = self._distinct_error_snippets(file_id, max_snippets=8)
        code_hits = extract_error_codes_for_prompt(error_snippets)
        for code in code_hits[:6]:
            queries_high.append(f"Qlik Replicate error {code}")

        # Extract SQLSTATE and NativeError values directly
        _sqlstate_re = re.compile(r"SqlState:\s*(\w+)", re.IGNORECASE)
        _native_re = re.compile(r"NativeError:\s*(\d+)", re.IGNORECASE)
        _vendor_re = re.compile(
            r"\b(SAP\s*ASE|Oracle|SQL\s*Server|PostgreSQL|MySQL|DB2|Sybase|ODBC)\b",
            re.IGNORECASE,
        )

        sqlstates: set = set()
        native_errors: set = set()
        vendors: set = set()

        combined_error_text = " ".join(error_snippets)
        for m in _sqlstate_re.finditer(combined_error_text):
            sqlstates.add(m.group(1).upper())
        for m in _native_re.finditer(combined_error_text):
            native_errors.add(m.group(1))
        for m in _vendor_re.finditer(combined_error_text):
            vendors.add(m.group(1).strip())

        for state in list(sqlstates)[:3]:
            queries_high.append(f"SQLSTATE {state} Qlik Replicate")
        for ne in list(native_errors)[:3]:
            queries_high.append(f"NativeError {ne} ODBC timeout Qlik Replicate")

        # --- Strategy 2: Symptom keyword extraction ---
        _symptom_patterns = [
            (re.compile(r"command\s+has\s+timed?\s*out", re.I), "ODBC command timeout"),
            (re.compile(r"FETCH.{0,20}table.{0,10}data", re.I), "fetch table data error"),
            (re.compile(r"stream\s+component.*terminat", re.I), "stream component terminated"),
            (re.compile(r"source\s+loop", re.I), "source loop error"),
            (re.compile(r"recoverable\s+error", re.I), "task recoverable error"),
            (re.compile(r"one.by.one|1by1", re.I), "one by one apply fallback"),
            (re.compile(r"PK\s*conflict|primary\s*key.*violat", re.I), "primary key conflict target"),
            (re.compile(r"ORA-\d{5}", re.I), "Oracle ORA error"),
            (re.compile(r"supplemental\s+logging", re.I), "supplemental logging"),
            (re.compile(r"memory.*warning|swap.*disk", re.I), "sorter memory warning"),
            (re.compile(r"disconnect|connection\s+(lost|reset|closed)", re.I), "connection lost disconnection"),
        ]

        for pat, symptom in _symptom_patterns:
            if pat.search(combined_error_text):
                vendor_ctx = list(vendors)[0] if vendors else ""
                queries_medium.append(
                    f"Qlik Replicate {vendor_ctx} {symptom} troubleshooting".strip()
                )

        # Vendor + endpoint specific queries
        for vendor in list(vendors)[:2]:
            if source_type:
                queries_medium.append(f"Qlik Replicate {vendor} {source_type} source configuration")
            else:
                queries_medium.append(f"Qlik Replicate {vendor} source endpoint troubleshooting")

        # --- Strategy 3: Component and endpoint queries (broader) ---
        if source_type:
            queries_broad.append(f"Qlik Replicate {source_type} source endpoint")
        if target_type:
            queries_broad.append(f"Qlik Replicate {target_type} target endpoint")

        error_summary = summary.get("error_summary", {})
        if error_summary.get("by_component"):
            top = sorted(error_summary["by_component"].items(), key=lambda x: x[1], reverse=True)[:3]
            for comp, _ in top:
                queries_broad.append(f"Qlik Replicate {comp} error troubleshooting")

        if summary.get("cdc_pipeline", {}).get("memory_warnings", 0) > 0:
            queries_broad.append("Qlik Replicate sorter CDC memory warning troubleshooting")

        # --- Strategy 4: Performance symptom queries ---
        lp_dp = (summary.get("latency_profile") or {}).get("data_points", 0) or 0
        has_latency_telemetry = lp_dp > 0
        if has_latency_telemetry and (
            summary.get("spikes", {}).get("count", 0) > 0
            or summary.get("plateaus", {}).get("count", 0) > 0
            or summary.get("bottleneck", {}).get("primary", "unknown") not in ("unknown", "balanced", "")
        ):
            bottleneck = summary.get("bottleneck", {}).get("primary", "") or ""
            queries_broad.append(f"Qlik Replicate high latency {bottleneck} performance troubleshooting")

        if (
            summary.get("oracle_redo_read_analysis") or {}
        ).get("has_red_flags") or (
            summary.get("oracle_redo_log_processing") or {}
        ).get("session_count", 0) > 0:
            queries_broad.append("Qlik Replicate Oracle source redo archived log performance")

        # Combine queries in priority order
        all_queries = queries_high + queries_medium + queries_broad
        if not all_queries:
            all_queries = ["Qlik Replicate troubleshooting"]

        results = []
        seen_urls: set = set()

        # Run high-priority queries with more results per query
        for q in queries_high[:8]:
            try:
                hits = self.vector_store.query_kb(query=q, n_results=5)
                for h in hits:
                    url = h.get("url", "")
                    if url and url not in seen_urls and h.get("similarity", 0) >= 0.22:
                        seen_urls.add(url)
                        results.append(h)
            except Exception as e:
                logger.debug(f"KB query (high) failed for '{q}': {e}")

        # Medium and broad queries
        for q in (queries_medium + queries_broad)[:10]:
            try:
                hits = self.vector_store.query_kb(query=q, n_results=4)
                for h in hits:
                    url = h.get("url", "")
                    if url and url not in seen_urls and h.get("similarity", 0) >= 0.25:
                        seen_urls.add(url)
                        results.append(h)
            except Exception as e:
                logger.debug(f"KB query (medium/broad) failed for '{q}': {e}")

        results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        return results[:max_results]

    def get_rag_context(
        self,
        file_id: int,
        query: Optional[str] = None,
        *,
        query_driven: bool = False,
    ) -> Dict[str, List[str]]:
        """
        Retrieve relevant context from the log vector store (chroma_db/).

        When ``query_driven`` is True (Phase 7 insufficiency fallback), only
        semantic similarity search runs — no bulk metadata fetch.
        """
        if query_driven and query:
            context: Dict[str, List[str]] = {
                "summaries": [],
                "errors": [],
                "anomalies": [],
            }
            similar = self.vector_store.query_similar(
                query=query,
                file_id=file_id,
                n_results=8,
            )
            for item in similar:
                if item["type"] == "error":
                    context["errors"].append(item["content"])
                elif item["type"] == "anomaly":
                    context["anomalies"].append(item["content"])
                elif item["type"] == "summary":
                    context["summaries"].append(item["content"])
            return context

        context = self.vector_store.get_file_context(file_id, max_items=10)

        if query:
            similar = self.vector_store.query_similar(
                query=query,
                file_id=file_id,
                n_results=5,
            )
            for item in similar:
                if item["type"] == "error":
                    context["errors"].append(item["content"])
                elif item["type"] == "anomaly":
                    context["anomalies"].append(item["content"])

        return context
    
    def estimate_cost(
        self,
        file_id: int,
        model: str = DEFAULT_MODEL,
        quick: bool = False,
        web_search: bool = False,
        focus_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Estimate the cost of generating a report.

        Uses the unified build_report_messages() so the token count matches
        the real report prompt (including KB, release notes, focus mode, etc.).
        """
        bundle = self.build_report_messages(
            file_id,
            quick=quick,
            web_search=web_search,
            focus_mode=focus_mode,
            model=model,
            include_chart=False,
            fetch_external=True,
            cancel_check=False,
        )

        # Provider-aware pricing
        use_gemini = self.provider == PROVIDER_GEMINI
        use_local = self.provider in LOCAL_LLM_PROVIDERS

        if use_local:
            return {
                "model": model or "(local)",
                "model_name": model or "(local)",
                "prompt_tokens": bundle.est_tokens,
                "completion_tokens": 1200,
                "total_tokens": bundle.est_tokens + 1200,
                "estimated_cost_usd": 0.0,
            }
        elif use_gemini:
            model_info = self.gemini_client.get_model_info(model)
            if model_info:
                cost = model_info.estimate_cost(bundle.est_tokens, 1200)
            else:
                cost = 0.0
            return {
                "model": model,
                "model_name": model_info.name if model_info else model,
                "prompt_tokens": bundle.est_tokens,
                "completion_tokens": 1200,
                "total_tokens": bundle.est_tokens + 1200,
                "estimated_cost_usd": round(cost, 6),
            }
        else:
            return self.llm_client.estimate_cost(
                model_id=model,
                prompt_tokens=bundle.est_tokens,
                estimated_completion_tokens=1200,
            )
    
    def build_report_messages(
        self,
        file_id: int,
        *,
        quick: bool = False,
        web_search: bool = False,
        focus_mode: Optional[str] = None,
        model: Optional[str] = None,
        include_chart: bool = True,
        fetch_external: bool = True,
        cancel_check: bool = True,
        payload_format: Optional[str] = "markdown",
        include_graph: bool = True,
    ) -> ReportPromptBundle:
        """
        Build the complete prompt for report generation (single source of truth).

        Used by generate_report, estimate_cost, prompt-preview, and compare.
        """
        from backend.llm.payload_formats import normalize_payload_format

        payload_format = normalize_payload_format(payload_format)
        use_gemini = self.provider == PROVIDER_GEMINI
        use_lmstudio = self.provider == PROVIDER_LMSTUDIO
        use_openai_api = self.provider == PROVIDER_OPENAI_API
        use_local = self.provider in LOCAL_LLM_PROVIDERS

        if model is None:
            if use_gemini:
                model = DEFAULT_GEMINI_MODEL
            elif use_local:
                model = ""
            else:
                model = DEFAULT_MODEL

        # --- file info ---
        file_info = self.get_file_info(file_id)
        if not file_info:
            raise ValueError(f"File {file_id} not found")

        if cancel_check:
            check_cancelled(file_id)

        # --- performance summary ---
        try:
            summary = self.build_performance_summary(file_id)
        except Exception as e:
            logger.error(f"Error building performance summary: {e}\n{traceback.format_exc()}")
            raise ValueError(f"Failed to build performance summary: {e}")

        if cancel_check:
            check_cancelled(file_id)

        # --- log embedding fallback (Phase 7: insufficiency-triggered only) ---
        from backend.database import LogLineMeta
        from backend.llm.evidence_insufficiency import (
            DEFAULT_MERGE_CAP,
            assess_evidence_insufficiency,
            build_semantic_retrieval_query,
            insufficiency_metrics,
        )
        from backend.llm.prompts import extract_error_codes_for_prompt

        db_error_count = self.db.query(LogError).filter(
            LogError.file_id == file_id,
        ).count()
        warning_count = self.db.query(LogLineMeta).filter(
            LogLineMeta.file_id == file_id,
            LogLineMeta.severity == "W",
        ).count()
        sqlite_excerpts = self._sqlite_error_excerpts(file_id)

        insufficiency = assess_evidence_insufficiency(
            quick=quick,
            focus_mode=focus_mode,
            db_error_count=db_error_count,
            sqlite_excerpt_count=len(sqlite_excerpts),
            warning_count=warning_count,
            merge_cap=DEFAULT_MERGE_CAP,
        )
        insufficiency_stats = insufficiency_metrics(insufficiency)

        context: Dict[str, List[str]] = {"errors": [], "anomalies": []}
        if insufficiency.insufficient:
            try:
                stats = self.vector_store.get_stats(file_id)
                if stats.get("total", 0) == 0:
                    self.embed_file_content(file_id)
                snippets = self._distinct_error_snippets(file_id)
                codes = extract_error_codes_for_prompt(snippets)
                retrieval_query = build_semantic_retrieval_query(
                    error_snippets=snippets,
                    error_codes=codes,
                    focus_mode=focus_mode,
                    reasons=insufficiency.reasons,
                )
                context = self.get_rag_context(
                    file_id,
                    retrieval_query,
                    query_driven=True,
                )
                logger.info(
                    "Log embedding fallback file_id=%s reasons=%s query=%r",
                    file_id,
                    insufficiency.reasons,
                    retrieval_query[:80],
                )
            except Exception as e:
                logger.warning(f"Log embedding fallback failed (continuing): {e}")

        if cancel_check:
            check_cancelled(file_id)

        merged_errors = self.merge_error_contexts(
            file_id,
            context.get("errors", []),
            focus_mode=focus_mode,
        )
        warning_contexts = (
            self._warning_excerpts_from_meta(file_id, limit=12)
            if focus_mode == "errors"
            else []
        )

        # --- release notes (optional external fetch) ---
        release_notes_context: List[Dict[str, Any]] = []
        if fetch_external:
            try:
                release_notes_context = self.get_release_notes_context(file_id, summary)
            except Exception as e:
                logger.warning(f"Error getting release notes context (continuing anyway): {e}")

        # --- KB context (optional external fetch) ---
        kb_context: List[Dict[str, Any]] = []
        if fetch_external:
            try:
                kb_context = self.get_kb_context(file_id, summary)
            except Exception as e:
                logger.warning(f"Error getting KB context (continuing anyway): {e}")

        # --- tuning reference ---
        tuning_reference = None
        try:
            from backend.llm.ar_props_lookup import format_tuning_reference
            from backend.llm.evidence_compiler import detect_tuning_modes

            endpoints = self._get_endpoint_types(file_id, summary)
            modes = detect_tuning_modes(
                summary,
                merged_errors,
                focus_mode=focus_mode,
            )
            tuning_parts: List[str] = []
            source_type = endpoints.get("source", "")
            target_type = endpoints.get("target", "")

            full_tuning = focus_mode == "configuration"
            if "timeout" in modes and source_type:
                ref = format_tuning_reference(
                    source_type, role="" if full_tuning else "SOURCE",
                )
                if ref:
                    tuning_parts.append(ref)
            if "batch" in modes and target_type:
                ref = format_tuning_reference(
                    target_type, role="" if full_tuning else "TARGET",
                )
                if ref:
                    tuning_parts.append(ref)
            if not tuning_parts and source_type:
                ref = format_tuning_reference(source_type, role="SOURCE")
                if ref:
                    tuning_parts.append(ref)
            if not tuning_parts and target_type:
                ref = format_tuning_reference(target_type, role="TARGET")
                if ref:
                    tuning_parts.append(ref)

            if tuning_parts:
                tuning_reference = "\n\n".join(tuning_parts)
        except Exception as e:
            logger.debug(f"ar_props tuning reference lookup failed (using fallback): {e}")

        if cancel_check:
            check_cancelled(file_id)

        graph_context = None
        graph_metrics: Dict[str, Any] = {}
        try:
            from backend.llm.graph_enrichment import (
                build_gated_graph_context,
                graph_enrichment_metrics,
            )
            graph_result = build_gated_graph_context(
                self.db,
                file_id,
                merged_errors,
                focus_mode=focus_mode,
                include_graph=include_graph,
            )
            graph_metrics = graph_enrichment_metrics(graph_result)
            if graph_result.injected:
                graph_context = graph_result.xml_block
        except Exception as e:
            logger.debug(f"Graph enrichment skipped: {e}")

        # --- build messages ---
        compact = self.provider in LOCAL_LLM_PROVIDERS
        sd, ec, ac, fi = self._sanitize_log_bundle(
            summary,
            merged_errors,
            context.get("anomalies", []),
            file_info,
        )
        messages = get_messages_for_analysis(
            summary_data=sd,
            error_contexts=ec,
            anomaly_contexts=ac,
            file_info=fi,
            quick=quick,
            web_search=web_search,
            release_notes_context=release_notes_context,
            kb_context=kb_context,
            sanitize_log_payload=self.sanitize_log_payload,
            compact=compact,
            focus_mode=focus_mode,
            tuning_reference=tuning_reference,
            warning_contexts=warning_contexts,
            payload_format=payload_format,
            graph_context=graph_context,
        )
        est_tokens = count_prompt_tokens(messages)
        logger.info(
            "Prompt composition: provider=%s compact=%s focus=%s | "
            "errors=%d anomalies=%d kb=%d release_notes=%d graph=%s | "
            "est_prompt_tokens=%d",
            self.provider, compact, focus_mode or "default",
            len(merged_errors),
            len(context.get("anomalies", [])),
            len(kb_context),
            len(release_notes_context),
            "yes" if graph_metrics.get("graph_injected") else "no",
            est_tokens,
        )

        # --- optional chart rendering ---
        chart_image_data = None
        if include_chart and not quick:
            supports_vision = (
                (use_gemini and gemini_model_supports_vision(model))
                or (not use_gemini and not use_local and openrouter_model_supports_vision(model))
            )
            if supports_vision:
                try:
                    from backend.llm.chart_renderer import render_latency_chart, is_available as chart_available
                    if chart_available():
                        chart_image_data = render_latency_chart(self.db, file_id)
                        if chart_image_data:
                            for msg in messages:
                                if msg["role"] == "user":
                                    msg["content"] = (
                                        "**Attached: Latency Over Time graph** - This chart shows source, "
                                        "target, and handling latency trends over the log period. Reference "
                                        "this graph in your Performance Analysis section.\n\n"
                                        + msg["content"]
                                    )
                                    break
                except Exception as e:
                    logger.warning(f"Chart rendering failed (continuing without image): {e}")

        # --- build prompt text for preview ---
        prompt_text = "\n\n".join(
            f"[{m['role'].upper()}]\n{m['content']}" for m in messages
        )

        context_stats = {
            "errors": len(merged_errors),
            "anomalies": len(context.get("anomalies", [])),
            "kb": len(kb_context),
            "release_notes": len(release_notes_context),
            **graph_metrics,
            **insufficiency_stats,
        }

        return ReportPromptBundle(
            messages=messages,
            est_tokens=est_tokens,
            context_stats=context_stats,
            prompt_text=prompt_text,
            provider=self.provider,
            compact=compact,
            focus_mode=focus_mode,
            web_search=web_search,
            quick=quick,
            chart_image_data=chart_image_data,
            kb_context=kb_context,
            release_notes_context=release_notes_context,
            payload_format=payload_format,
        )

    def generate_report(
        self,
        file_id: int,
        model: Optional[str] = None,
        quick: bool = False,
        web_search: bool = False,
        focus_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate an LLM analysis report for a log file.
        
        Args:
            file_id: ID of the log file
            model: Model to use (defaults to configured default)
            quick: If True, generate a quick summary instead of full report
            web_search: If True, enable web search for additional context
            focus_mode: Optional analysis focus (general_review, performance, errors, configuration)
        
        Returns:
            Report result dictionary
        """
        gen_t0 = _time.perf_counter()

        # Determine which provider and model to use
        use_gemini = self.provider == PROVIDER_GEMINI
        use_lmstudio = self.provider == PROVIDER_LMSTUDIO
        use_openai_api = self.provider == PROVIDER_OPENAI_API
        use_local = self.provider in LOCAL_LLM_PROVIDERS

        if model is None:
            if use_gemini:
                model = DEFAULT_GEMINI_MODEL
            elif use_local:
                model = ""
            else:
                model = DEFAULT_MODEL
        
        logger.info(f"Starting report generation for file_id={file_id}, provider={self.provider}, model={model}, quick={quick}")
        begin_generation(file_id, kind="report")
        set_progress(file_id, "preparing", "Collecting log data and building context...")

        # Check if the appropriate client is configured
        if use_gemini:
            if not self.gemini_client.is_configured:
                logger.error("Gemini API key not configured")
                raise ValueError("Gemini API key not configured. Please configure in AI Settings.")
        elif use_local:
            pass
        else:
            if not self.llm_client.is_configured:
                logger.error("OpenRouter API key not configured")
                raise ValueError("OpenRouter API key not configured. Please configure in AI Settings.")

        # Build the full prompt bundle via the unified builder
        bundle = self.build_report_messages(
            file_id,
            quick=quick,
            web_search=web_search,
            focus_mode=focus_mode,
            model=model,
            include_chart=True,
            fetch_external=True,
            cancel_check=True,
        )
        messages = bundle.messages
        est_tokens = bundle.est_tokens
        kb_context = bundle.kb_context
        release_notes_context = bundle.release_notes_context
        chart_image_data = bundle.chart_image_data

        set_progress(
            file_id, "building_prompt",
            f"Assembling prompt ({bundle.context_stats.get('errors', 0)} errors, {bundle.context_stats.get('kb', 0)} KB articles)...",
            errors=bundle.context_stats.get("errors", 0),
            kb=bundle.context_stats.get("kb", 0),
            release_notes=bundle.context_stats.get("release_notes", 0),
        )

        check_cancelled(file_id)

        validation_result = None

        # Generate completion using appropriate provider
        try:
            if use_gemini:
                provider_name = "Gemini"
            elif use_lmstudio:
                provider_name = "LM Studio"
            elif use_openai_api:
                provider_name = "OpenAI API"
            else:
                provider_name = "OpenRouter"

            set_progress(
                file_id, "generating",
                f"Waiting for {provider_name} response...",
                provider=provider_name,
                model=model or "default",
                est_prompt_tokens=est_tokens,
            )
            logger.info(f"Calling {provider_name} API with model={model}...")
            
            # LM Studio local models can degrade at very long outputs; cap the default.
            # User-configured lmstudio_max_tokens overrides the per-call default.
            local_temp = 0.3
            if use_lmstudio:
                default_max = LMSTUDIO_DEFAULT_MAX_TOKENS if not quick else 350
                max_output = self.lmstudio_max_tokens if self.lmstudio_max_tokens is not None else default_max
                local_temp = self.lmstudio_temperature if self.lmstudio_temperature is not None else 0.3
                if local_temp > LMSTUDIO_REPORT_MAX_TEMPERATURE:
                    logger.info(
                        "Clamping LM Studio report temperature %.2f → %.2f",
                        local_temp,
                        LMSTUDIO_REPORT_MAX_TEMPERATURE,
                    )
                    local_temp = LMSTUDIO_REPORT_MAX_TEMPERATURE
            elif use_openai_api:
                default_max = OPENAI_API_DEFAULT_MAX_TOKENS if not quick else 350
                max_output = self.openai_api_max_tokens if self.openai_api_max_tokens is not None else default_max
                local_temp = self.openai_api_temperature if self.openai_api_temperature is not None else 0.3
                if local_temp > OPENAI_API_REPORT_MAX_TEMPERATURE:
                    logger.info(
                        "Clamping OpenAI API report temperature %.2f → %.2f",
                        local_temp,
                        OPENAI_API_REPORT_MAX_TEMPERATURE,
                    )
                    local_temp = OPENAI_API_REPORT_MAX_TEMPERATURE
            else:
                max_output = 8192 if not quick else 800

            def _call_llm(use_web_search: bool, call_messages: Optional[List[Dict[str, str]]] = None):
                msgs = call_messages if call_messages is not None else messages
                if use_gemini:
                    return self.gemini_client.complete(
                        messages=msgs,
                        model=model,
                        max_tokens=max_output,
                        temperature=0.3,
                        web_search=use_web_search,
                        image_data=chart_image_data if call_messages is None else None,
                        cancel_file_id=file_id,
                    )
                elif use_lmstudio:
                    return self.lmstudio_client.complete(
                        messages=msgs,
                        model=model,
                        max_tokens=max_output,
                        temperature=local_temp,
                        cancel_file_id=file_id,
                    )
                elif use_openai_api:
                    return self.openai_api_client.complete(
                        messages=msgs,
                        model=model,
                        max_tokens=max_output,
                        temperature=local_temp,
                        cancel_file_id=file_id,
                    )
                else:
                    return self.llm_client.complete(
                        messages=msgs,
                        model=model,
                        max_tokens=max_output,
                        temperature=0.3,
                        web_search=use_web_search,
                        image_data=chart_image_data if call_messages is None else None,
                        cancel_file_id=file_id,
                    )
            
            llm_t0 = _time.perf_counter()
            result = _call_llm(web_search)

            # Retry without web_search if response was empty (grounding conflict).
            if _is_empty_completion(result) and web_search and not use_local:
                logger.warning(
                    "Empty response with web_search enabled (finish_reason=%s). "
                    "Retrying without web search...",
                    result.finish_reason,
                )
                result = _call_llm(False)

            # LM Studio can return empty on first request; OpenAI API (FLM) retries
            # inside openai_api_client.complete() on a shared HTTP session.
            elif _is_empty_completion(result) and use_lmstudio:
                logger.warning(
                    "Empty response from %s (finish_reason=%s). Retrying once...",
                    provider_name,
                    result.finish_reason,
                )
                _time.sleep(LOCAL_EMPTY_RESPONSE_RETRY_DELAY_SECONDS)
                result = _call_llm(web_search)

            if _is_empty_completion(result):
                if use_openai_api:
                    raise ValueError(
                        f"{provider_name} returned an empty report after FLM retries. "
                        "The FLM server returned no output (often a prompt-cache miss). "
                        "Keep FLM running and try generating again."
                    )
                raise ValueError(
                    f"{provider_name} returned an empty report after retry. "
                    "Try generating again."
                )

            llm_duration_seconds = round(_time.perf_counter() - llm_t0, 2)
            generation_duration_seconds = round(_time.perf_counter() - gen_t0, 2)
            
            logger.info(
                "%s call successful: %d prompt + %d completion tokens, cost=$%.4f, llm_time=%.1fs",
                provider_name, result.prompt_tokens, result.completion_tokens,
                result.cost_usd, llm_duration_seconds,
            )

            from backend.llm.report_formatter import normalize_report_markdown

            normalized_content, format_fixes = normalize_report_markdown(result.content)
            if format_fixes:
                logger.info(
                    "Report markdown normalized for file_id=%s: %s",
                    file_id,
                    "; ".join(format_fixes[:5]),
                )
                result.content = normalized_content

            if not quick:
                from backend.llm.report_validator import (
                    build_validation_context,
                    validate_and_correct,
                )

                validation_ctx = build_validation_context(
                    self.db,
                    file_id,
                    bundle,
                    max_completion_tokens=max_output,
                )
                validation_result = validate_and_correct(
                    result.content,
                    validation_ctx,
                    messages,
                    input_tokens=result.prompt_tokens,
                    output_tokens=result.completion_tokens,
                    llm_call=lambda msgs: _call_llm(False, msgs),
                )
                if validation_result.correction_applied:
                    result.content = validation_result.final_content
                    result.prompt_tokens += validation_result.correction_prompt_tokens
                    result.completion_tokens += validation_result.correction_completion_tokens
                    result.cost_usd = (result.cost_usd or 0) + validation_result.correction_cost_usd
                    logger.info(
                        "Report validation correction applied (passed=%s, score=%.1f)",
                        validation_result.passed,
                        validation_result.grade.score,
                    )
                elif not validation_result.passed:
                    logger.warning(
                        "Report validation did not pass (normalized=%.2f): %s",
                        validation_result.grade.metrics.get("normalized_score", 0),
                        "; ".join(validation_result.issues[:5]),
                    )

            set_progress(
                file_id, "done",
                f"Completed — {result.completion_tokens} tokens generated",
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                llm_duration_seconds=llm_duration_seconds,
                generation_duration_seconds=generation_duration_seconds,
            )
        except GenerationCancelled:
            set_progress(file_id, "cancelled", "Report generation cancelled")
            raise
        except Exception as e:
            set_progress(file_id, "error", str(e)[:200])
            logger.error(f"LLM API call failed: {e}\n{traceback.format_exc()}")
            raise ValueError(f"LLM API call failed: {e}")
        
        # Build reference lists with source tags
        kb_refs = []
        for kb in kb_context:
            meta = kb.get("metadata", {})
            src = "web" if isinstance(meta, dict) and meta.get("source") == "tavily_web_search" else "chromadb"
            kb_refs.append({
                "title": kb.get("title", ""),
                "url": kb.get("url", ""),
                "source": src,
                "snippet": (kb.get("content", "") or "")[:200],
            })

        rn_refs = []
        for rn in release_notes_context:
            meta = rn.get("metadata", {})
            src = "web" if isinstance(meta, dict) and meta.get("source") == "tavily_web_search" else "chromadb"
            rn_refs.append({
                "title": rn.get("title", ""),
                "url": rn.get("url", ""),
                "source": src,
                "snippet": (rn.get("content", "") or "")[:200],
                "version": rn.get("version", ""),
                "fix_id": rn.get("fix_id", ""),
            })

        chart_b64 = None
        if chart_image_data:
            chart_b64 = base64.b64encode(chart_image_data).decode("utf-8")

        check_cancelled(file_id)

        out: Dict[str, Any] = {
            "file_id": file_id,
            "model_used": result.model,
            "report_content": result.content,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.total_tokens,
            "cost_usd": result.cost_usd,
            "generated_at": datetime.utcnow().isoformat(),
            "quick": quick,
            "web_search": web_search,
            "focus_mode": focus_mode,
            "llm_duration_seconds": llm_duration_seconds,
            "generation_duration_seconds": generation_duration_seconds,
            "chart_image_base64": chart_b64,
            "kb_references": kb_refs if kb_refs else None,
            "release_notes_references": rn_refs if rn_refs else None,
        }
        if validation_result is not None:
            out["validation"] = validation_result.to_dict()
        return out


def generate_report_for_file(
    db: Session,
    file_id: int,
    model: Optional[str] = None,
    quick: bool = False,
    web_search: bool = False
) -> Dict[str, Any]:
    """
    Convenience function to generate a report for a file.
    
    Args:
        db: Database session
        file_id: ID of the log file
        model: Optional model override
        quick: If True, generate quick summary
        web_search: If True, enable web search for additional context
    
    Returns:
        Report result dictionary
    """
    generator = ReportGenerator(db)
    return generator.generate_report(file_id, model=model, quick=quick, web_search=web_search)

