"""Unit tests for backend.core.graph."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from backend.core.graph import (
    AdjacencyGraph,
    build_adjacency,
    get_related_context,
    _node_id,
    _code_node_id,
    _component_node_id,
    EDGE_CO_OCCURS,
    EDGE_HAS_CODE,
    EDGE_IN_COMPONENT,
    EDGE_ON_THREAD,
    CO_OCCURS_WINDOW,
)


class TestAdjacencyGraph:
    def test_add_edge_bidirectional(self):
        g = AdjacencyGraph()
        g.add_edge("a", "b", "test_edge")
        assert any(dst == "b" for dst, *_ in g.adj["a"])
        assert any(dst == "a" for dst, *_ in g.adj["b"])

    def test_neighbors_bfs(self):
        g = AdjacencyGraph()
        g.add_edge("center", "n1", "type_a", weight=1.0)
        g.add_edge("center", "n2", "type_b", weight=0.5)
        g.add_edge("n1", "n3", "type_a", weight=1.0)

        result = g.neighbors("center", max_hops=2, max_results=10)
        node_ids = [r["node_id"] for r in result]
        assert "n1" in node_ids
        assert "n2" in node_ids
        assert "n3" in node_ids

    def test_neighbors_respects_max_hops(self):
        g = AdjacencyGraph()
        g.add_edge("a", "b", "t")
        g.add_edge("b", "c", "t")
        g.add_edge("c", "d", "t")

        result = g.neighbors("a", max_hops=1, max_results=10)
        node_ids = [r["node_id"] for r in result]
        assert "b" in node_ids
        assert "c" not in node_ids

    def test_neighbors_respects_max_results(self):
        g = AdjacencyGraph()
        for i in range(50):
            g.add_edge("center", f"node_{i}", "t")

        result = g.neighbors("center", max_hops=1, max_results=5)
        assert len(result) == 5

    def test_neighbors_unknown_node(self):
        g = AdjacencyGraph()
        assert g.neighbors("nonexistent") == []

    def test_weight_affects_score(self):
        g = AdjacencyGraph()
        g.add_edge("center", "low", "t", weight=0.1)
        g.add_edge("center", "high", "t", weight=2.0)

        result = g.neighbors("center", max_hops=1, max_results=10)
        assert result[0]["node_id"] == "high"
        assert result[0]["score"] > result[1]["score"]

    def test_to_dict_from_dict_roundtrip(self):
        g = AdjacencyGraph()
        g.add_edge("a", "b", "co_occurs", weight=0.8, provenance="INFERRED")
        g.add_edge("a", "c", "has_code", weight=1.5, provenance="EXTRACTED")

        data = g.to_dict()
        g2 = AdjacencyGraph.from_dict(data)

        assert set(g2.adj.keys()) == set(g.adj.keys())
        assert len(g2.adj["a"]) == len(g.adj["a"])


class TestBuildAdjacency:
    def test_builds_from_errors(self, tmp_db):
        from backend.database import LogFile, LogError

        db = tmp_db
        lf = LogFile(filename="test.log", file_path="/tmp/test.log", status="ready")
        db.add(lf)
        db.commit()
        db.refresh(lf)

        db.add(LogError(file_id=lf.id, line_number=10, component="TARGET_APPLY",
                        thread_id="001", error_code="ORA-00054", text="error 1"))
        db.add(LogError(file_id=lf.id, line_number=15, component="TARGET_APPLY",
                        thread_id="001", error_code="ORA-00054", text="error 2"))
        db.add(LogError(file_id=lf.id, line_number=200, component="SOURCE_CAPTURE",
                        thread_id="002", error_code=None, text="error 3"))
        db.commit()

        graph = build_adjacency(db, lf.id)

        n10 = _node_id(lf.id, 10)
        n15 = _node_id(lf.id, 15)
        n200 = _node_id(lf.id, 200)

        assert n10 in graph.adj
        assert n15 in graph.adj

        # Errors 10 and 15 share component+thread+code → co-occurrence edge
        neighbors_of_10 = graph.neighbors(n10, max_hops=1, max_results=50)
        neighbor_ids = [n["node_id"] for n in neighbors_of_10]
        assert n15 in neighbor_ids

        # Error 200 is far away and different component → no direct co-occurrence
        assert n200 not in neighbor_ids

    def test_code_nodes_created(self, tmp_db):
        from backend.database import LogFile, LogError

        db = tmp_db
        lf = LogFile(filename="test.log", file_path="/tmp/test.log", status="ready")
        db.add(lf)
        db.commit()
        db.refresh(lf)

        db.add(LogError(file_id=lf.id, line_number=10, component="TARGET_APPLY",
                        error_code="ORA-00054", text="err"))
        db.commit()

        graph = build_adjacency(db, lf.id)
        code_nid = _code_node_id("ORA-00054")
        assert code_nid in graph.adj

    def test_empty_file(self, tmp_db):
        from backend.database import LogFile

        db = tmp_db
        lf = LogFile(filename="empty.log", file_path="/tmp/empty.log", status="ready")
        db.add(lf)
        db.commit()
        db.refresh(lf)

        graph = build_adjacency(db, lf.id)
        assert len(graph.adj) == 0


class TestGetRelatedContext:
    def test_weak_for_missing_anchor(self, tmp_db):
        from backend.database import LogFile

        db = tmp_db
        lf = LogFile(filename="test.log", file_path="/tmp/test.log", status="ready")
        db.add(lf)
        db.commit()
        db.refresh(lf)

        graph = AdjacencyGraph()
        result = get_related_context(db, lf.id, line_number=999, graph=graph)
        assert result["weak"] is True

    def test_returns_enriched_neighbors(self, indexed_file):
        db, file_id, log_path = indexed_file
        from backend.core.graph import build_adjacency

        graph = build_adjacency(db, file_id)

        from backend.database import LogError
        first_err = db.query(LogError).filter(LogError.file_id == file_id).first()
        if not first_err:
            pytest.skip("No errors in sample log")

        result = get_related_context(db, file_id, first_err.line_number, graph=graph)
        assert "neighbors" in result
        assert "anchor_line" in result
