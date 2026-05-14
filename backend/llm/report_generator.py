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
import traceback
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from backend.database import (
    LogFile, LogPerformance, LogError, LogStats,
    LogBatch, LogTableStats, LogTaskConfig, LogSorterEvent, LogOracleRedoRead, LogOracleRedoLogSession, LLMConfig
)
from backend.core.analysis import PerformanceCockpit
from backend.llm.vectorstore import get_vector_store, LogVectorStore
from backend.llm.client import get_llm_client, OpenRouterClient, DEFAULT_MODEL, openrouter_model_supports_vision
from backend.llm.gemini_client import get_gemini_client, GeminiClient, DEFAULT_GEMINI_MODEL, gemini_model_supports_vision
from backend.llm.lmstudio_client import get_lmstudio_client, LMStudioClient, DEFAULT_LMSTUDIO_BASE_URL, LMSTUDIO_DEFAULT_MAX_TOKENS
from backend.llm.prompts import (
    get_messages_for_analysis,
    count_prompt_tokens,
    sanitize_dict,
    sanitize_list,
)
from backend.llm.tavily_client import TavilyClient

# Configure logging
logger = logging.getLogger(__name__)

# Provider constants
PROVIDER_GEMINI = "gemini"
PROVIDER_OPENROUTER = "openrouter"
PROVIDER_LMSTUDIO = "lmstudio"


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
    ):
        """
        Initialize the report generator.
        
        Args:
            db: SQLAlchemy database session
            vector_store: Optional vector store instance (uses singleton if not provided)
            llm_client: Optional OpenRouter LLM client instance
            gemini_client: Optional Gemini client instance
            lmstudio_client: Optional LM Studio client instance
        """
        self.db = db
        self.vector_store = vector_store or get_vector_store()
        self.llm_client = llm_client or get_llm_client()
        self.gemini_client = gemini_client or get_gemini_client()
        self.lmstudio_client = lmstudio_client or get_lmstudio_client()
        
        # Get provider preference from config; sync LM Studio URL and parameters
        config = self.db.query(LLMConfig).first()
        self.provider = config.provider if config else PROVIDER_GEMINI
        if config and self.provider == PROVIDER_LMSTUDIO:
            lmstudio_url = getattr(config, "lmstudio_base_url", None) or DEFAULT_LMSTUDIO_BASE_URL
            self.lmstudio_client.set_base_url(lmstudio_url)
        # Store user-configured overrides (None = use hardcoded defaults)
        self.lmstudio_temperature: Optional[float] = getattr(config, "lmstudio_temperature", None) if config else None
        self.lmstudio_max_tokens: Optional[int] = getattr(config, "lmstudio_max_tokens", None) if config else None
    
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
        
        # Fetch task config
        config = self.db.query(LogTaskConfig).filter(
            LogTaskConfig.file_id == file_id
        ).first()
        
        config_data = {}
        if config:
            config_data = {
                "bulk_timeout_ms": config.bulk_timeout_ms,
                "parallel_apply_threads": config.parallel_apply_threads,
                "target_type": config.target_type,
                "source_type": config.source_type,
                "merge_enabled": config.merge_enabled
            }
        
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
            return cockpit.generate_summary()
        
        # Return minimal summary if no performance data
        return {
            "latency_profile": {"data_points": 0},
            "bottleneck": {"primary": "unknown"},
            "spikes": {"count": 0, "items": []},
            "plateaus": {"count": 0, "items": []},
            "batch_profile": {"total_batches": len(batch_data)},
            "error_summary": {"total": len(error_data)},
            "recommendations": [],
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
    
    def _get_endpoint_types(self, file_id: int, summary: Dict[str, Any]) -> Dict[str, str]:
        """Extract source/target endpoint types from task config or summary."""
        config = self.db.query(LogTaskConfig).filter(
            LogTaskConfig.file_id == file_id
        ).first()

        source_type = ""
        target_type = ""
        if config:
            source_type = config.source_type or ""
            target_type = config.target_type or ""

        if not source_type and "source_analysis" in summary:
            source_type = summary["source_analysis"].get("source_type", "")
        if not target_type and "target_analysis" in summary:
            target_type = summary["target_analysis"].get("target_type", "")

        return {"source": source_type, "target": target_type}

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
        """
        queries = []
        endpoints = self._get_endpoint_types(file_id, summary)
        source_type = endpoints["source"]
        target_type = endpoints["target"]

        if source_type:
            queries.append(f"Qlik Replicate {source_type} source")
        if target_type:
            queries.append(f"Qlik Replicate {target_type} target")

        error_summary = summary.get("error_summary", {})
        if error_summary.get("by_component"):
            top = sorted(error_summary["by_component"].items(), key=lambda x: x[1], reverse=True)[:3]
            for comp, _ in top:
                queries.append(f"Qlik Replicate {comp} error troubleshooting")

        has_perf_issues = (
            summary.get("spikes", {}).get("count", 0) > 0
            or summary.get("plateaus", {}).get("count", 0) > 0
            or summary.get("bottleneck", {}).get("primary", "unknown") != "unknown"
        )
        if has_perf_issues:
            bottleneck = summary.get("bottleneck", {}).get("primary", "")
            queries.append(f"Qlik Replicate high latency {bottleneck} performance troubleshooting")
            if summary.get("cdc_pipeline", {}).get("memory_warnings", 0) > 0:
                queries.append("Qlik Replicate memory pressure CDC")

        if not queries:
            queries = ["Qlik Replicate troubleshooting"]

        results = []
        seen_urls = set()

        for q in queries[:5]:
            try:
                hits = self.vector_store.query_kb(query=q, n_results=4)
                for h in hits:
                    url = h.get("url", "")
                    if url and url not in seen_urls and h.get("similarity", 0) >= 0.25:
                        seen_urls.add(url)
                        results.append(h)
            except Exception as e:
                logger.debug(f"KB query failed for '{q}': {e}")

        results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        return results[:max_results]

    def get_rag_context(self, file_id: int, query: Optional[str] = None) -> Dict[str, List[str]]:
        """
        Retrieve relevant context from the vector store.
        
        Args:
            file_id: ID of the log file
            query: Optional query to focus retrieval
        
        Returns:
            Dictionary with error and anomaly contexts
        """
        # Get all context for this file
        context = self.vector_store.get_file_context(file_id, max_items=10)
        
        # If a specific query is provided, also do similarity search
        if query:
            similar = self.vector_store.query_similar(
                query=query,
                file_id=file_id,
                n_results=5
            )
            
            # Add similar results to context
            for item in similar:
                if item["type"] == "error":
                    context["errors"].append(item["content"])
                elif item["type"] == "anomaly":
                    context["anomalies"].append(item["content"])
        
        return context
    
    def estimate_cost(
        self,
        file_id: int,
        model: str = DEFAULT_MODEL
    ) -> Dict[str, Any]:
        """
        Estimate the cost of generating a report.
        
        Args:
            file_id: ID of the log file
            model: Model to use for estimation
        
        Returns:
            Cost estimation details
        """
        # Build the prompt to count tokens
        summary = self.build_performance_summary(file_id)
        file_info = self.get_file_info(file_id)
        context = self.get_rag_context(file_id)
        
        messages = get_messages_for_analysis(
            summary_data=sanitize_dict(summary),
            error_contexts=sanitize_list(context.get("errors", [])),
            anomaly_contexts=sanitize_list(context.get("anomalies", [])),
            file_info=sanitize_dict(file_info) if file_info else None
        )
        
        prompt_tokens = count_prompt_tokens(messages)
        
        return self.llm_client.estimate_cost(
            model_id=model,
            prompt_tokens=prompt_tokens,
            estimated_completion_tokens=1200
        )
    
    def generate_report(
        self,
        file_id: int,
        model: Optional[str] = None,
        quick: bool = False,
        web_search: bool = False
    ) -> Dict[str, Any]:
        """
        Generate an LLM analysis report for a log file.
        
        Args:
            file_id: ID of the log file
            model: Model to use (defaults to configured default)
            quick: If True, generate a quick summary instead of full report
            web_search: If True, enable web search for additional context
        
        Returns:
            Report result dictionary
        """
        # Determine which provider and model to use
        use_gemini = self.provider == PROVIDER_GEMINI
        use_lmstudio = self.provider == PROVIDER_LMSTUDIO

        if model is None:
            if use_gemini:
                model = DEFAULT_GEMINI_MODEL
            elif use_lmstudio:
                model = ""  # LM Studio uses whatever model is loaded; empty = server default
            else:
                model = DEFAULT_MODEL
        
        logger.info(f"Starting report generation for file_id={file_id}, provider={self.provider}, model={model}, quick={quick}")
        
        # Check if the appropriate client is configured
        if use_gemini:
            if not self.gemini_client.is_configured:
                logger.error("Gemini API key not configured")
                raise ValueError("Gemini API key not configured. Please configure in AI Settings.")
        elif use_lmstudio:
            pass  # LM Studio: no key required; connection is validated at test-connection time
        else:
            if not self.llm_client.is_configured:
                logger.error("OpenRouter API key not configured")
                raise ValueError("OpenRouter API key not configured. Please configure in AI Settings.")
        
        # Get file info
        try:
            file_info = self.get_file_info(file_id)
            if not file_info:
                logger.error(f"File {file_id} not found")
                raise ValueError(f"File {file_id} not found")
            logger.debug(f"File info: {file_info.get('filename', 'unknown')}")
        except Exception as e:
            logger.error(f"Error getting file info: {e}\n{traceback.format_exc()}")
            raise ValueError(f"Failed to get file info: {e}")
        
        # Build performance summary
        try:
            logger.info("Building performance summary...")
            summary = self.build_performance_summary(file_id)
            logger.debug(f"Summary keys: {list(summary.keys()) if summary else 'None'}")
        except Exception as e:
            logger.error(f"Error building performance summary: {e}\n{traceback.format_exc()}")
            raise ValueError(f"Failed to build performance summary: {e}")
        
        # Ensure embeddings exist
        try:
            stats = self.vector_store.get_stats(file_id)
            if stats.get("total", 0) == 0:
                logger.info("Embedding file content...")
                self.embed_file_content(file_id)
        except Exception as e:
            logger.warning(f"Error with embeddings (continuing anyway): {e}")
            # Don't fail - embeddings are nice to have but not required
        
        # Get RAG context
        try:
            context = self.get_rag_context(file_id)
            logger.debug(f"RAG context: errors={len(context.get('errors', []))}, anomalies={len(context.get('anomalies', []))}")
        except Exception as e:
            logger.warning(f"Error getting RAG context (continuing anyway): {e}")
            context = {"errors": [], "anomalies": []}

        # Get release notes context
        release_notes_context = []
        try:
            logger.info("Fetching release notes context...")
            release_notes_context = self.get_release_notes_context(file_id, summary)
            logger.debug(f"Release notes context: {len(release_notes_context)} entries")
        except Exception as e:
            logger.warning(f"Error getting release notes context (continuing anyway): {e}")

        # Get KB context
        kb_context = []
        try:
            logger.info("Fetching KB context...")
            kb_context = self.get_kb_context(file_id, summary)
            logger.debug(f"KB context: {len(kb_context)} articles")
        except Exception as e:
            logger.warning(f"Error getting KB context (continuing anyway): {e}")
        
        # Build messages
        try:
            logger.info(f"Building prompt messages (web_search={web_search})...")
            messages = get_messages_for_analysis(
                summary_data=sanitize_dict(summary),
                error_contexts=sanitize_list(context.get("errors", [])),
                anomaly_contexts=sanitize_list(context.get("anomalies", [])),
                file_info=sanitize_dict(file_info) if file_info else None,
                quick=quick,
                web_search=web_search,
                release_notes_context=release_notes_context,
                kb_context=kb_context,
            )
            logger.debug(f"Message count: {len(messages)}")
        except Exception as e:
            logger.error(f"Error building messages: {e}\n{traceback.format_exc()}")
            raise ValueError(f"Failed to build prompt: {e}")
        
        # Render latency chart image for vision-capable models
        chart_image_data = None
        supports_vision = (
            (use_gemini and gemini_model_supports_vision(model))
            or (not use_gemini and not use_lmstudio and openrouter_model_supports_vision(model))
            # LM Studio vision support is not detected per-model yet; skip chart rendering
        )
        if supports_vision and not quick:
            try:
                from backend.llm.chart_renderer import render_latency_chart, is_available as chart_available
                if chart_available():
                    logger.info("Rendering latency chart for vision model...")
                    chart_image_data = render_latency_chart(self.db, file_id)
                    if chart_image_data:
                        logger.info(f"Chart rendered: {len(chart_image_data)} bytes")
                        for msg in messages:
                            if msg["role"] == "user":
                                msg["content"] = (
                                    "**Attached: Latency Over Time graph** - This chart shows source, "
                                    "target, and handling latency trends over the log period. Reference "
                                    "this graph in your Performance Analysis section.\n\n"
                                    + msg["content"]
                                )
                                break
                    else:
                        logger.info("Chart renderer returned no data (no performance data for this file)")
                else:
                    logger.info("Chart rendering skipped: plotly/kaleido not installed (pip install plotly kaleido)")
            except ImportError:
                logger.info("Chart rendering skipped: plotly/kaleido not installed (pip install plotly kaleido)")
            except Exception as e:
                logger.warning(f"Chart rendering failed (continuing without image): {e}")
        elif not supports_vision:
            logger.debug(f"Chart rendering skipped: model {model} does not support vision")
        elif quick:
            logger.debug("Chart rendering skipped: quick report mode")

        # Generate completion using appropriate provider
        try:
            if use_gemini:
                provider_name = "Gemini"
            elif use_lmstudio:
                provider_name = "LM Studio"
            else:
                provider_name = "OpenRouter"
            logger.info(f"Calling {provider_name} API with model={model}...")
            
            # LM Studio local models can degrade at very long outputs; cap the default.
            # User-configured lmstudio_max_tokens overrides the per-call default.
            if use_lmstudio:
                default_max = LMSTUDIO_DEFAULT_MAX_TOKENS if not quick else 350
                max_output = self.lmstudio_max_tokens if self.lmstudio_max_tokens is not None else default_max
                lmstudio_temp = self.lmstudio_temperature if self.lmstudio_temperature is not None else 0.3
            else:
                max_output = 8192 if not quick else 800
                lmstudio_temp = 0.3  # unused for non-lmstudio paths

            def _call_llm(use_web_search: bool):
                if use_gemini:
                    return self.gemini_client.complete(
                        messages=messages,
                        model=model,
                        max_tokens=max_output,
                        temperature=0.3,
                        web_search=use_web_search,
                        image_data=chart_image_data,
                    )
                elif use_lmstudio:
                    # LM Studio handles web search via its own Tavily MCP;
                    # the app does not inject Tavily results separately.
                    return self.lmstudio_client.complete(
                        messages=messages,
                        model=model,
                        max_tokens=max_output,
                        temperature=lmstudio_temp,
                    )
                else:
                    return self.llm_client.complete(
                        messages=messages,
                        model=model,
                        max_tokens=max_output,
                        temperature=0.3,
                        web_search=use_web_search,
                        image_data=chart_image_data,
                    )
            
            result = _call_llm(web_search)
            
            # Retry without web_search if response was empty (grounding conflict).
            # Skip retry for LM Studio — web_search param is ignored there.
            if (
                result.completion_tokens == 0
                and not result.content.strip()
                and web_search
                and not use_lmstudio
            ):
                logger.warning(
                    f"Empty response with web_search enabled (finish_reason={result.finish_reason}). "
                    "Retrying without web search..."
                )
                result = _call_llm(False)
            
            logger.info(f"{provider_name} call successful: {result.prompt_tokens} prompt + {result.completion_tokens} completion tokens, cost=${result.cost_usd:.4f}")
        except Exception as e:
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

        return {
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
            "chart_image_base64": chart_b64,
            "kb_references": kb_refs if kb_refs else None,
            "release_notes_references": rn_refs if rn_refs else None,
        }


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

