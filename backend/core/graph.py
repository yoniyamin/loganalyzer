"""Per-file structural neighborhood graph (adjacency + weighted BFS).

No NetworkX — uses a plain adjacency list with typed/weighted edges.
Builds from SQLite at request time (with JSON cache for repeated queries).
"""
import json
import os
import tempfile
import logging
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from backend.database import (
    LogError, LogBatch, LogTableStats, LogStats, FileVersion, SavedFinding, LogLineMeta,
)

logger = logging.getLogger(__name__)

# Edge types
EDGE_HAS_CODE = "has_code"
EDGE_IN_COMPONENT = "in_component"
EDGE_ON_THREAD = "on_thread"
EDGE_SAME_TABLE = "same_table"
EDGE_SAME_BATCH = "same_batch"
EDGE_CO_OCCURS = "co_occurs_within"
EDGE_COMPONENT_PIPELINE = "component_pipeline"

# Provenance
PROV_EXTRACTED = "EXTRACTED"
PROV_INFERRED = "INFERRED"
PROV_USER = "USER"

# Co-occurrence window (lines)
CO_OCCURS_WINDOW = 50


def _node_id(file_id: int, line_number: int) -> str:
    return f"file:{file_id}:line:{line_number}"


def _code_node_id(code: str) -> str:
    return f"code:{code}"


def _component_node_id(file_id: int, component: str) -> str:
    return f"file:{file_id}:comp:{component}"


def _thread_node_id(file_id: int, thread_id: str) -> str:
    return f"file:{file_id}:thread:{thread_id}"


def _batch_node_id(file_id: int, batch_line: int) -> str:
    return f"file:{file_id}:batch:{batch_line}"


class AdjacencyGraph:
    """Lightweight adjacency list with typed, weighted edges."""

    def __init__(self):
        self.adj: Dict[str, List[Tuple[str, str, float, str]]] = defaultdict(list)
        # (target, edge_type, weight, provenance)

    def add_edge(self, src: str, dst: str, edge_type: str, weight: float = 1.0, provenance: str = PROV_EXTRACTED):
        self.adj[src].append((dst, edge_type, weight, provenance))
        self.adj[dst].append((src, edge_type, weight, provenance))

    def neighbors(self, node: str, max_hops: int = 2, max_results: int = 30) -> List[Dict[str, Any]]:
        """Weighted BFS from node, returns ranked neighbor list."""
        if node not in self.adj:
            return []

        visited: Dict[str, float] = {node: 1.0}
        queue: deque = deque()
        results: List[Dict[str, Any]] = []

        # Seed with immediate neighbors
        for (dst, etype, weight, prov) in self.adj[node]:
            score = weight
            if dst not in visited or score > visited[dst]:
                visited[dst] = score
                queue.append((dst, 1, score, etype, prov))

        while queue and len(results) < max_results:
            current, hop, score, via_type, via_prov = queue.popleft()
            if hop > max_hops:
                continue

            results.append({
                "node_id": current,
                "hop": hop,
                "score": score,
                "via_edge_type": via_type,
                "provenance": via_prov,
            })

            if hop < max_hops:
                decay = 0.5
                for (dst, etype, weight, prov) in self.adj[current]:
                    next_score = score * decay * weight
                    if dst not in visited or next_score > visited[dst]:
                        visited[dst] = next_score
                        queue.append((dst, hop + 1, next_score, etype, prov))

        results.sort(key=lambda x: -x["score"])
        return results[:max_results]

    def to_dict(self) -> Dict[str, Any]:
        return {"adjacency": {k: v for k, v in self.adj.items()}}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AdjacencyGraph":
        g = cls()
        for src, edges in data.get("adjacency", {}).items():
            g.adj[src] = [(e[0], e[1], e[2], e[3]) for e in edges]
        return g


def build_adjacency(db: Session, file_id: int) -> AdjacencyGraph:
    """Build the structural adjacency graph for a log file from SQLite data."""
    graph = AdjacencyGraph()

    # Load errors
    errors = db.query(LogError).filter(LogError.file_id == file_id).order_by(LogError.line_number).all()

    # Index errors by various dimensions for edge building
    errors_by_component: Dict[str, List[LogError]] = defaultdict(list)
    errors_by_thread: Dict[str, List[LogError]] = defaultdict(list)
    errors_by_code: Dict[str, List[LogError]] = defaultdict(list)

    for err in errors:
        nid = _node_id(file_id, err.line_number)
        if err.component:
            errors_by_component[err.component].append(err)
            graph.add_edge(nid, _component_node_id(file_id, err.component), EDGE_IN_COMPONENT)
        if err.thread_id:
            errors_by_thread[err.thread_id].append(err)
            graph.add_edge(nid, _thread_node_id(file_id, err.thread_id), EDGE_ON_THREAD, weight=0.5)
        if err.error_code:
            errors_by_code[err.error_code].append(err)
            graph.add_edge(nid, _code_node_id(err.error_code), EDGE_HAS_CODE, weight=1.5)

    # Load batches — link errors that occur during a batch
    batches = db.query(LogBatch).filter(LogBatch.file_id == file_id).order_by(LogBatch.line_number).all()
    for batch in batches:
        batch_nid = _batch_node_id(file_id, batch.line_number)
        if batch.tables:
            try:
                tables = json.loads(batch.tables)
                for t in tables:
                    for err in errors:
                        if err.text and t.split('.')[-1] in err.text:
                            graph.add_edge(
                                _node_id(file_id, err.line_number),
                                batch_nid,
                                EDGE_SAME_BATCH,
                                weight=0.8,
                            )
            except (json.JSONDecodeError, TypeError):
                pass

    # Co-occurrence edges: errors within CO_OCCURS_WINDOW lines of each other
    # ONLY if they share a secondary dimension (component, code, or thread)
    for i, err_a in enumerate(errors):
        for j in range(i + 1, len(errors)):
            err_b = errors[j]
            if err_b.line_number - err_a.line_number > CO_OCCURS_WINDOW:
                break

            # Require secondary overlap
            has_overlap = False
            if err_a.component and err_a.component == err_b.component:
                has_overlap = True
            elif err_a.error_code and err_a.error_code == err_b.error_code:
                has_overlap = True
            elif err_a.thread_id and err_a.thread_id == err_b.thread_id:
                has_overlap = True

            if has_overlap:
                distance = err_b.line_number - err_a.line_number
                weight = max(0.2, 1.0 - distance / CO_OCCURS_WINDOW)
                graph.add_edge(
                    _node_id(file_id, err_a.line_number),
                    _node_id(file_id, err_b.line_number),
                    EDGE_CO_OCCURS,
                    weight=weight,
                    provenance=PROV_INFERRED,
                )

    return graph


def get_related_context(
    db: Session,
    file_id: int,
    line_number: int,
    max_hops: int = 2,
    max_results: int = 20,
    graph: Optional[AdjacencyGraph] = None,
) -> Dict[str, Any]:
    """Get structurally related context for a specific error line.

    Returns neighbor nodes + metadata for UI display and LLM context.
    """
    if graph is None:
        graph = build_adjacency(db, file_id)

    anchor = _node_id(file_id, line_number)
    neighbors = graph.neighbors(anchor, max_hops=max_hops, max_results=max_results)

    if not neighbors:
        return {"anchor": anchor, "neighbors": [], "weak": True}

    # Enrich neighbors with line content
    enriched = []
    from backend.core.reader import LogReader
    try:
        reader = LogReader(db, file_id)
    except ValueError:
        return {"anchor": anchor, "neighbors": [], "weak": True}

    for n in neighbors:
        nid = n["node_id"]
        info = {"node_id": nid, "hop": n["hop"], "score": n["score"], "edge_type": n["via_edge_type"]}

        # If it's an error node, fetch the line
        if nid.startswith("file:") and ":line:" in nid:
            try:
                ln = int(nid.split(":line:")[1])
                ctx = reader.read_lines_centered(ln, before=2, after=2)
                info["line_number"] = ln
                info["context_lines"] = ctx.get("lines", [])
                # Fetch error metadata
                err = db.query(LogError).filter(
                    LogError.file_id == file_id,
                    LogError.line_number == ln
                ).first()
                if err:
                    info["error_code"] = err.error_code
                    info["component"] = err.component
                    info["timestamp"] = err.timestamp.isoformat() if err.timestamp else None
            except (ValueError, IndexError):
                pass
        elif nid.startswith("code:"):
            info["label"] = nid.replace("code:", "")
            info["type"] = "error_code"
        elif ":comp:" in nid:
            info["label"] = nid.split(":comp:")[1]
            info["type"] = "component"
        elif ":thread:" in nid:
            info["label"] = nid.split(":thread:")[1]
            info["type"] = "thread"
        elif ":batch:" in nid:
            info["label"] = f"Batch @line {nid.split(':batch:')[1]}"
            info["type"] = "batch"

        enriched.append(info)

    # Overlay findings at query time
    findings = db.query(SavedFinding).filter(SavedFinding.file_id == file_id).all()
    finding_nodes = []
    for f in findings:
        if f.line_number and abs(f.line_number - line_number) < CO_OCCURS_WINDOW:
            finding_nodes.append({
                "node_id": f"finding:{f.id}",
                "type": "finding",
                "label": f.title or f.content[:80],
                "line_number": f.line_number,
                "hop": 1,
                "score": 0.9,
                "edge_type": "related_finding",
            })

    return {
        "anchor": anchor,
        "anchor_line": line_number,
        "neighbors": enriched,
        "findings": finding_nodes,
        "weak": len(enriched) < 2,
    }
