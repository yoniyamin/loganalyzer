"""
Report Generator - Orchestrates RAG Retrieval and LLM Report Generation

This module ties together:
1. SQLite data retrieval (performance summaries)
2. ChromaDB context retrieval (errors, anomalies)
3. LLM completion for report generation
"""

import json
import logging
import traceback
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from backend.database import (
    LogFile, LogPerformance, LogError, LogStats,
    LogBatch, LogTableStats, LogTaskConfig, LogSorterEvent, LLMConfig
)
from backend.core.analysis import PerformanceCockpit
from backend.llm.vectorstore import get_vector_store, LogVectorStore
from backend.llm.client import get_llm_client, OpenRouterClient, DEFAULT_MODEL
from backend.llm.gemini_client import get_gemini_client, GeminiClient, DEFAULT_GEMINI_MODEL
from backend.llm.prompts import (
    get_messages_for_analysis,
    count_prompt_tokens,
    sanitize_dict,
    sanitize_list,
)

# Configure logging
logger = logging.getLogger(__name__)

# Provider constants
PROVIDER_GEMINI = "gemini"
PROVIDER_OPENROUTER = "openrouter"


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
        gemini_client: Optional[GeminiClient] = None
    ):
        """
        Initialize the report generator.
        
        Args:
            db: SQLAlchemy database session
            vector_store: Optional vector store instance (uses singleton if not provided)
            llm_client: Optional OpenRouter LLM client instance
            gemini_client: Optional Gemini client instance
        """
        self.db = db
        self.vector_store = vector_store or get_vector_store()
        self.llm_client = llm_client or get_llm_client()
        self.gemini_client = gemini_client or get_gemini_client()
        
        # Get provider preference from config
        config = self.db.query(LLMConfig).first()
        self.provider = config.provider if config else PROVIDER_GEMINI
    
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
        
        # Build performance cockpit
        if performance_data:
            cockpit = PerformanceCockpit(
                performance_data=performance_data,
                batches=batch_data,
                table_stats=table_stats_data,
                errors=error_data,
                config=config_data,
                sorter_events=sorter_data
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
            "recommendations": []
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
        
        if model is None:
            model = DEFAULT_GEMINI_MODEL if use_gemini else DEFAULT_MODEL
        
        logger.info(f"Starting report generation for file_id={file_id}, provider={self.provider}, model={model}, quick={quick}")
        
        # Check if the appropriate client is configured
        if use_gemini:
            if not self.gemini_client.is_configured:
                logger.error("Gemini API key not configured")
                raise ValueError("Gemini API key not configured. Please configure in AI Settings.")
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
        
        # Build messages
        try:
            logger.info(f"Building prompt messages (web_search={web_search})...")
            messages = get_messages_for_analysis(
                summary_data=sanitize_dict(summary),
                error_contexts=sanitize_list(context.get("errors", [])),
                anomaly_contexts=sanitize_list(context.get("anomalies", [])),
                file_info=sanitize_dict(file_info) if file_info else None,
                quick=quick,
                web_search=web_search
            )
            logger.debug(f"Message count: {len(messages)}")
        except Exception as e:
            logger.error(f"Error building messages: {e}\n{traceback.format_exc()}")
            raise ValueError(f"Failed to build prompt: {e}")
        
        # Generate completion using appropriate provider
        try:
            provider_name = "Gemini" if use_gemini else "OpenRouter"
            logger.info(f"Calling {provider_name} API with model={model}...")
            
            # Use higher max_tokens for detailed reports
            # Gemini 2.5 Flash supports up to 65K output tokens
            # OpenRouter models typically support 4K-16K
            max_output = 8192 if not quick else 800
            
            if use_gemini:
                result = self.gemini_client.complete(
                    messages=messages,
                    model=model,
                    max_tokens=max_output,
                    temperature=0.3,
                    web_search=web_search
                )
            else:
                result = self.llm_client.complete(
                    messages=messages,
                    model=model,
                    max_tokens=max_output,
                    temperature=0.3,
                    web_search=web_search
                )
            
            logger.info(f"{provider_name} call successful: {result.prompt_tokens} prompt + {result.completion_tokens} completion tokens, cost=${result.cost_usd:.4f}")
        except Exception as e:
            logger.error(f"LLM API call failed: {e}\n{traceback.format_exc()}")
            raise ValueError(f"LLM API call failed: {e}")
        
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
            "web_search": web_search
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

