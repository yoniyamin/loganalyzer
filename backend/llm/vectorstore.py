"""
ChromaDB Vector Store for Log Analysis RAG

Provides embedding storage and retrieval for:
- Log summaries (performance cockpit data, batch analysis)
- Error contexts (error messages with surrounding lines)
- Anomaly sections (latency spikes, plateaus, unusual patterns)

All data is sanitized before embedding to remove sensitive information.
Uses the centralized sanitizer module for PII detection and anonymization.
"""

import os
import json
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime

import chromadb
from chromadb.config import Settings

from backend.llm.sanitizer import sanitize_text as _sanitize_for_embedding


# Default ChromaDB persist directory
CHROMA_PERSIST_DIR = os.environ.get(
    "CHROMA_PERSIST_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "chroma_db")
)

# Collection names
COLLECTION_SUMMARIES = "log_summaries"
COLLECTION_ERRORS = "error_contexts"
COLLECTION_ANOMALIES = "anomaly_sections"
COLLECTION_KB = "qlik_replicate_kb"  # KB articles from kb-assistant
COLLECTION_RELEASE_NOTES = "qlik_replicate_release_notes"  # Release notes from kb-assistant


def _version_sort_key(v: str):
    """Convert 'November 2024' to (2024, 11) for sorting."""
    import re
    _M = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
          "july":7,"august":8,"september":9,"october":10,"november":11,"december":12}
    m = re.search(r'(\w+)\s+(\d{4})', v)
    if m:
        return (int(m.group(2)), _M.get(m.group(1).lower(), 0))
    return (0, 0)


class LogVectorStore:
    """
    Vector store for log analysis using ChromaDB.
    
    Uses local embeddings (all-MiniLM-L6-v2) which are free and don't require API calls.
    """
    
    def __init__(self, persist_directory: Optional[str] = None):
        """
        Initialize the vector store.
        
        Args:
            persist_directory: Directory to persist ChromaDB data.
                             Defaults to ./chroma_db in project root.
        """
        self.persist_dir = persist_directory or CHROMA_PERSIST_DIR
        
        # Ensure directory exists
        os.makedirs(self.persist_dir, exist_ok=True)
        
        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Get or create collections
        self._init_collections()
    
    def _init_collections(self):
        """Initialize the three collections for different content types."""
        # Summaries collection - for structured performance data
        self.summaries = self.client.get_or_create_collection(
            name=COLLECTION_SUMMARIES,
            metadata={"description": "Log performance summaries and analysis"}
        )
        
        # Errors collection - for error messages with context
        self.errors = self.client.get_or_create_collection(
            name=COLLECTION_ERRORS,
            metadata={"description": "Error and warning messages with context"}
        )
        
        # Anomalies collection - for detected anomalies
        self.anomalies = self.client.get_or_create_collection(
            name=COLLECTION_ANOMALIES,
            metadata={"description": "Latency spikes, plateaus, and anomalies"}
        )
    
    def _generate_id(self, file_id: int, content_type: str, index: int) -> str:
        """Generate a unique ID for a document."""
        return f"file_{file_id}_{content_type}_{index}"
    
    def _content_hash(self, content: str) -> str:
        """Generate a hash of content for deduplication."""
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    def add_summary(
        self,
        file_id: int,
        summary_data: Dict[str, Any],
        summary_type: str = "performance_cockpit"
    ) -> str:
        """
        Add a log summary to the vector store.
        
        Args:
            file_id: ID of the log file
            summary_data: Dictionary containing summary data
            summary_type: Type of summary (e.g., "performance_cockpit", "batch_analysis")
        
        Returns:
            Document ID
        """
        # Convert dict to readable text for embedding
        content = self._format_summary_for_embedding(summary_data, summary_type)
        # Sanitize to remove sensitive information
        content = _sanitize_for_embedding(content)
        doc_id = self._generate_id(file_id, f"summary_{summary_type}", 0)
        
        # Check if already exists and update
        existing = self.summaries.get(ids=[doc_id])
        if existing and existing['ids']:
            self.summaries.update(
                ids=[doc_id],
                documents=[content],
                metadatas=[{
                    "file_id": file_id,
                    "summary_type": summary_type,
                    "updated_at": datetime.utcnow().isoformat(),
                    "content_hash": self._content_hash(content)
                }]
            )
        else:
            self.summaries.add(
                ids=[doc_id],
                documents=[content],
                metadatas=[{
                    "file_id": file_id,
                    "summary_type": summary_type,
                    "created_at": datetime.utcnow().isoformat(),
                    "content_hash": self._content_hash(content)
                }]
            )
        
        return doc_id
    
    def _format_summary_for_embedding(self, data: Dict[str, Any], summary_type: str) -> str:
        """Format summary data as readable text for embedding (sanitized)."""
        lines = [f"Log Analysis Summary - Type: {summary_type}"]
        
        if summary_type == "performance_cockpit":
            # Format performance cockpit data
            if "latency_profile" in data:
                lp = data["latency_profile"]
                lines.append("\n## Latency Profile")
                for key in ["source", "handling", "target"]:
                    if key in lp:
                        stats = lp[key]
                        lines.append(f"- {key.title()}: avg={stats.get('avg', 0):.2f}s, "
                                   f"max={stats.get('max', 0):.2f}s, p95={stats.get('p95', 0):.2f}s")
            
            if "bottleneck" in data:
                lines.append(f"\n## Bottleneck: {data['bottleneck'].get('primary', 'unknown')}")
            
            if "recommendations" in data:
                lines.append("\n## Recommendations")
                for rec in data["recommendations"][:5]:  # Top 5
                    lines.append(f"- [{rec.get('priority', 'medium')}] {rec.get('title', '')}: {rec.get('description', '')}")
        
        elif summary_type == "batch_analysis":
            if "batch_profile" in data:
                bp = data["batch_profile"]
                lines.append(f"\n## Batch Statistics")
                lines.append(f"- Total batches: {bp.get('total_batches', 0)}")
                if "closure_reasons" in bp:
                    lines.append(f"- Closure reasons: {json.dumps(bp['closure_reasons'])}")
        
        elif summary_type == "error_summary":
            if "error_summary" in data:
                es = data["error_summary"]
                lines.append(f"\n## Error Summary")
                lines.append(f"- Total errors: {es.get('total', 0)}")
                if "by_component" in es:
                    lines.append(f"- By component: {json.dumps(es['by_component'])}")
        
        else:
            # Generic formatting for other types
            lines.append(f"\nData: {json.dumps(data, indent=2, default=str)[:2000]}")
        
        return "\n".join(lines)
    
    def add_error_context(
        self,
        file_id: int,
        error_text: str,
        context_before: List[str],
        context_after: List[str],
        line_number: int,
        component: Optional[str] = None,
        timestamp: Optional[str] = None
    ) -> str:
        """
        Add an error with its surrounding context to the vector store.
        
        Args:
            file_id: ID of the log file
            error_text: The error/warning message
            context_before: Lines before the error
            context_after: Lines after the error
            line_number: Line number in the log file
            component: Log component (e.g., TARGET_APPLY)
            timestamp: Timestamp of the error
        
        Returns:
            Document ID
        """
        # Sanitize input text
        error_text = _sanitize_for_embedding(error_text)
        context_before = [_sanitize_for_embedding(line) for line in context_before]
        context_after = [_sanitize_for_embedding(line) for line in context_after]
        
        # Build context document
        lines = []
        if timestamp:
            lines.append(f"Timestamp: {timestamp}")
        if component:
            lines.append(f"Component: {component}")
        lines.append(f"Line: {line_number}")
        lines.append("\n--- Context Before ---")
        lines.extend(context_before[-5:])  # Last 5 lines before
        lines.append("\n--- ERROR/WARNING ---")
        lines.append(error_text)
        lines.append("\n--- Context After ---")
        lines.extend(context_after[:5])  # First 5 lines after
        
        content = "\n".join(lines)
        content_hash = self._content_hash(content)
        doc_id = f"file_{file_id}_error_{line_number}_{content_hash}"
        
        # Check if already exists
        existing = self.errors.get(ids=[doc_id])
        if not existing or not existing['ids']:
            self.errors.add(
                ids=[doc_id],
                documents=[content],
                metadatas=[{
                    "file_id": file_id,
                    "line_number": line_number,
                    "component": component or "UNKNOWN",
                    "timestamp": timestamp or "",
                    "created_at": datetime.utcnow().isoformat()
                }]
            )
        
        return doc_id
    
    def add_anomaly(
        self,
        file_id: int,
        anomaly_type: str,
        description: str,
        details: Dict[str, Any],
        line_numbers: Optional[List[int]] = None
    ) -> str:
        """
        Add an anomaly detection result to the vector store.
        
        Args:
            file_id: ID of the log file
            anomaly_type: Type of anomaly (e.g., "latency_spike", "plateau", "disconnect")
            description: Human-readable description
            details: Additional details about the anomaly
            line_numbers: Relevant line numbers in the log
        
        Returns:
            Document ID
        """
        # Sanitize description
        description = _sanitize_for_embedding(description)
        
        # Sanitize details dict by converting to string and back
        details_str = json.dumps(details, indent=2, default=str)
        details_str = _sanitize_for_embedding(details_str)
        
        content = f"""Anomaly Detection: {anomaly_type}

Description: {description}

Details:
{details_str}

Relevant lines: {line_numbers or []}
"""
        
        content_hash = self._content_hash(content)
        doc_id = f"file_{file_id}_anomaly_{anomaly_type}_{content_hash}"
        
        existing = self.anomalies.get(ids=[doc_id])
        if not existing or not existing['ids']:
            self.anomalies.add(
                ids=[doc_id],
                documents=[content],
                metadatas=[{
                    "file_id": file_id,
                    "anomaly_type": anomaly_type,
                    "line_numbers": json.dumps(line_numbers or []),
                    "created_at": datetime.utcnow().isoformat()
                }]
            )
        
        return doc_id
    
    def query_similar(
        self,
        query: str,
        file_id: Optional[int] = None,
        n_results: int = 5,
        collection: str = "all"
    ) -> List[Dict[str, Any]]:
        """
        Query for similar content across collections.
        
        Args:
            query: Query text
            file_id: Optional file ID to filter results
            n_results: Number of results per collection
            collection: Which collection(s) to query: "all", "summaries", "errors", "anomalies"
        
        Returns:
            List of matching documents with metadata
        """
        results = []
        where_filter = {"file_id": file_id} if file_id else None
        
        collections_to_query = []
        if collection == "all":
            collections_to_query = [
                (self.summaries, "summary"),
                (self.errors, "error"),
                (self.anomalies, "anomaly")
            ]
        elif collection == "summaries":
            collections_to_query = [(self.summaries, "summary")]
        elif collection == "errors":
            collections_to_query = [(self.errors, "error")]
        elif collection == "anomalies":
            collections_to_query = [(self.anomalies, "anomaly")]
        
        for coll, coll_type in collections_to_query:
            try:
                query_result = coll.query(
                    query_texts=[query],
                    n_results=n_results,
                    where=where_filter
                )
                
                if query_result and query_result['documents']:
                    for i, doc in enumerate(query_result['documents'][0]):
                        results.append({
                            "type": coll_type,
                            "content": doc,
                            "metadata": query_result['metadatas'][0][i] if query_result['metadatas'] else {},
                            "distance": query_result['distances'][0][i] if query_result.get('distances') else None
                        })
            except Exception as e:
                # Collection might be empty
                continue
        
        # Sort by distance (lower is better)
        results.sort(key=lambda x: x.get('distance', float('inf')))
        
        return results[:n_results * 2]  # Return top results across all collections
    
    def get_file_context(self, file_id: int, max_items: int = 10) -> Dict[str, List[str]]:
        """
        Get all embedded context for a specific file.
        
        Args:
            file_id: ID of the log file
            max_items: Maximum items to retrieve per collection
        
        Returns:
            Dictionary with context from each collection
        """
        context = {
            "summaries": [],
            "errors": [],
            "anomalies": []
        }
        
        for coll, key in [(self.summaries, "summaries"), 
                          (self.errors, "errors"), 
                          (self.anomalies, "anomalies")]:
            try:
                result = coll.get(
                    where={"file_id": file_id},
                    limit=max_items
                )
                if result and result['documents']:
                    context[key] = result['documents']
            except Exception:
                continue
        
        return context
    
    def delete_file_embeddings(self, file_id: int) -> int:
        """
        Delete all embeddings for a specific file.
        
        Args:
            file_id: ID of the log file
        
        Returns:
            Number of documents deleted
        """
        deleted = 0
        
        for coll in [self.summaries, self.errors, self.anomalies]:
            try:
                # Get IDs to delete
                result = coll.get(where={"file_id": file_id})
                if result and result['ids']:
                    coll.delete(ids=result['ids'])
                    deleted += len(result['ids'])
            except Exception:
                continue
        
        return deleted
    
    def get_stats(self, file_id: Optional[int] = None) -> Dict[str, int]:
        """
        Get statistics about stored embeddings.
        
        Args:
            file_id: Optional file ID to filter stats
        
        Returns:
            Dictionary with counts per collection
        """
        stats = {}
        
        for coll, name in [(self.summaries, "summaries"), 
                           (self.errors, "errors"), 
                           (self.anomalies, "anomalies")]:
            try:
                if file_id:
                    result = coll.get(where={"file_id": file_id})
                    stats[name] = len(result['ids']) if result and result['ids'] else 0
                else:
                    stats[name] = coll.count()
            except Exception:
                stats[name] = 0
        
        stats["total"] = sum(stats.values())
        return stats
    
    def query_kb(
        self,
        query: str,
        n_results: int = 3,
        source_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Query KB articles for troubleshooting suggestions.
        
        This queries the qlik_replicate_kb collection populated by kb-assistant.
        Use this to find relevant KB articles when analyzing errors or anomalies.
        
        Args:
            query: Query text (e.g., error message or symptom description)
            n_results: Number of results to return
            source_filter: Optional filter by source type ('kb_article' or 'markdown')
        
        Returns:
            List of matching KB articles with metadata and relevance score
        """
        try:
            kb_collection = self.client.get_or_create_collection(
                name=COLLECTION_KB,
                metadata={"description": "Qlik Replicate Knowledge Base articles"}
            )
            
            where_filter = {"source": source_filter} if source_filter else None
            
            results = kb_collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filter
            )
            
            # Format results
            formatted = []
            if results and results['documents'] and results['documents'][0]:
                for i, doc in enumerate(results['documents'][0]):
                    distance = results['distances'][0][i] if results.get('distances') else 0
                    similarity = max(0, 1 - distance)  # Convert distance to similarity
                    
                    formatted.append({
                        "content": doc,
                        "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                        "distance": distance,
                        "similarity": similarity,
                        "title": results['metadatas'][0][i].get("title", "Unknown") if results['metadatas'] else "Unknown",
                        "url": results['metadatas'][0][i].get("url", "") if results['metadatas'] else ""
                    })
            
            return formatted
        
        except Exception as e:
            # KB collection might not exist yet (kb-assistant not run)
            return []
    
    def get_kb_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the KB collection.
        
        Returns:
            Dictionary with KB stats or empty dict if KB not initialized
        """
        try:
            kb_collection = self.client.get_or_create_collection(name=COLLECTION_KB)
            return {
                "kb_documents": kb_collection.count(),
                "collection_name": COLLECTION_KB
            }
        except Exception:
            return {"kb_documents": 0, "collection_name": COLLECTION_KB}

    def query_release_notes(
        self,
        query: str,
        n_results: int = 5,
        endpoint_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Query release notes for fixes relevant to a given query.
        
        Args:
            query: Query text (e.g., error message, endpoint type, symptom)
            n_results: Number of results to return
            endpoint_filter: Optional filter by endpoint type (e.g. 'Oracle', 'Snowflake')
        
        Returns:
            List of matching release note entries with metadata and relevance score
        """
        try:
            rn_collection = self.client.get_or_create_collection(
                name=COLLECTION_RELEASE_NOTES,
                metadata={"description": "Qlik Replicate release notes and fixes"}
            )

            where_filter = None
            if endpoint_filter:
                where_filter = {"endpoint_types": {"$contains": endpoint_filter.lower()}}

            results = rn_collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filter
            )

            formatted = []
            if results and results['documents'] and results['documents'][0]:
                for i, doc in enumerate(results['documents'][0]):
                    distance = results['distances'][0][i] if results.get('distances') else 0
                    similarity = max(0, 1 - distance)
                    meta = results['metadatas'][0][i] if results['metadatas'] else {}

                    fix_ids_str = meta.get("fix_ids", "") or meta.get("fix_id", "")
                    formatted.append({
                        "content": doc,
                        "metadata": meta,
                        "distance": distance,
                        "similarity": similarity,
                        "title": meta.get("title", "Unknown"),
                        "url": meta.get("url", ""),
                        "version": meta.get("version", ""),
                        "fix_id": fix_ids_str.split(",")[0] if fix_ids_str else "",
                    })

            return formatted

        except Exception:
            return []

    def get_release_notes_by_version(
        self,
        version_prefix: str,
    ) -> List[Dict[str, Any]]:
        """Get ALL release note chunks whose version metadata matches the prefix.

        Args:
            version_prefix: e.g. "May 2024" - matched with $contains

        Returns:
            List of all matching chunks with their documents and metadata.
        """
        try:
            rn_collection = self.client.get_or_create_collection(
                name=COLLECTION_RELEASE_NOTES,
                metadata={"description": "Qlik Replicate release notes and fixes"}
            )
            results = rn_collection.get(
                where={"version": version_prefix},
                include=["documents", "metadatas"],
            )
            formatted = []
            if results and results["documents"]:
                for i, doc in enumerate(results["documents"]):
                    meta = results["metadatas"][i] if results["metadatas"] else {}
                    formatted.append({
                        "content": doc,
                        "metadata": meta,
                        "version": meta.get("version", ""),
                        "url": meta.get("url", ""),
                        "title": meta.get("title", ""),
                    })
            return formatted
        except Exception:
            return []

    def get_all_release_note_versions(self) -> List[str]:
        """Return the distinct version strings in the release notes collection."""
        try:
            rn_collection = self.client.get_or_create_collection(
                name=COLLECTION_RELEASE_NOTES,
                metadata={"description": "Qlik Replicate release notes and fixes"}
            )
            results = rn_collection.get(include=["metadatas"], limit=500)
            versions = sorted(
                {m.get("version", "") for m in (results["metadatas"] or []) if m.get("version")},
                key=lambda v: _version_sort_key(v),
                reverse=True,
            )
            return versions
        except Exception:
            return []

    def get_all_release_note_chunks(self) -> List[Dict[str, Any]]:
        """Get ALL release note chunks in one call (fast, no embeddings needed)."""
        try:
            rn_collection = self.client.get_or_create_collection(
                name=COLLECTION_RELEASE_NOTES,
                metadata={"description": "Qlik Replicate release notes and fixes"}
            )
            results = rn_collection.get(include=["documents", "metadatas"], limit=1000)
            out = []
            if results and results["documents"]:
                for i, doc in enumerate(results["documents"]):
                    meta = results["metadatas"][i] if results["metadatas"] else {}
                    out.append({"content": doc, "metadata": meta})
            return out
        except Exception:
            return []

    def get_release_notes_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the release notes collection.
        
        Returns:
            Dictionary with release notes stats
        """
        try:
            rn_collection = self.client.get_or_create_collection(name=COLLECTION_RELEASE_NOTES)
            return {
                "release_notes_documents": rn_collection.count(),
                "collection_name": COLLECTION_RELEASE_NOTES
            }
        except Exception:
            return {"release_notes_documents": 0, "collection_name": COLLECTION_RELEASE_NOTES}


# Singleton instance for easy access
_vector_store: Optional[LogVectorStore] = None


def get_vector_store() -> LogVectorStore:
    """Get the singleton vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = LogVectorStore()
    return _vector_store

