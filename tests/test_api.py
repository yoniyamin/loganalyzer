"""Integration tests for new API endpoints (FTS search, related context)."""
import pytest


class TestFTSEndpoint:
    def test_fts_basic_search(self, test_client):
        resp = test_client.get(
            f"/files/{test_client.file_id}/search/fts",
            params={"q": '"ORA-00054"'}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert len(data["results"]) >= 1
        assert data["results"][0]["line_number"] > 0

    def test_fts_no_results(self, test_client):
        resp = test_client.get(
            f"/files/{test_client.file_id}/search/fts",
            params={"q": "xyznonexistent999"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["results"] == []

    def test_fts_component_filter(self, test_client):
        resp = test_client.get(
            f"/files/{test_client.file_id}/search/fts",
            params={"q": '"ORA-00054"', "component": "TARGET_APPLY"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) >= 1

    def test_fts_line_range_filter(self, test_client):
        resp = test_client.get(
            f"/files/{test_client.file_id}/search/fts",
            params={"q": "Transaction", "from": 5, "to": 25}
        )
        assert resp.status_code == 200
        data = resp.json()
        for r in data["results"]:
            assert 5 <= r["line_number"] <= 25

    def test_fts_missing_file_404(self, test_client):
        resp = test_client.get("/files/9999/search/fts", params={"q": "test"})
        assert resp.status_code == 404

    def test_fts_empty_query_422(self, test_client):
        resp = test_client.get(
            f"/files/{test_client.file_id}/search/fts",
            params={"q": ""}
        )
        assert resp.status_code == 422


class TestRelatedContextEndpoint:
    def test_related_basic(self, test_client):
        resp = test_client.get(
            f"/files/{test_client.file_id}/issues/related",
            params={"line_number": 22}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "data" in data

    def test_related_missing_file_404(self, test_client):
        resp = test_client.get(
            "/files/9999/issues/related",
            params={"line_number": 10}
        )
        assert resp.status_code == 404

    def test_related_missing_param_422(self, test_client):
        resp = test_client.get(f"/files/{test_client.file_id}/issues/related")
        assert resp.status_code == 422


class TestGraphCacheInvalidation:
    def test_cache_roundtrip(self, indexed_file):
        db, file_id, _ = indexed_file
        from backend.core.graph import build_adjacency
        from backend.core.graph_cache import load_cached_graph, save_graph_cache, invalidate_cache

        graph = build_adjacency(db, file_id)
        assert save_graph_cache(db, file_id, graph) is True

        loaded, hit = load_cached_graph(db, file_id)
        assert hit is True
        assert loaded is not None
        assert len(loaded.adj) == len(graph.adj)

        invalidate_cache(file_id)
        _, hit2 = load_cached_graph(db, file_id)
        assert hit2 is False
