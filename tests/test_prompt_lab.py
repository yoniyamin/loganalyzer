"""Tests for prompt-lab endpoints (prompt-preview and compare)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_llm_client(app, db):
    from backend.llm.endpoints import router
    from backend.database import get_db
    from fastapi.testclient import TestClient

    app.include_router(router, prefix="/api")

    def _override():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


# ---------------------------------------------------------------------------
# Prompt preview
# ---------------------------------------------------------------------------

class TestPromptLabStatus:
    def test_status_endpoint(self, indexed_file):
        db, _, _ = indexed_file
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        client = _make_llm_client(FastAPI(), db)
        resp = client.get("/api/llm/prompt-lab/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "compare_enabled" in data
        assert isinstance(data["compare_enabled"], bool)


class TestReportPromptPreview:
    def test_preview_returns_prompt(self, indexed_file):
        db, file_id, _ = indexed_file
        from fastapi import FastAPI

        client = _make_llm_client(FastAPI(), db)
        resp = client.post(
            f"/api/llm/report/{file_id}/prompt-preview",
            json={"quick": True, "web_search": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["est_tokens"] > 0
        assert data["message_count"] >= 2
        assert "[SYSTEM]" in data["prompt_text"]
        assert data["provider"]  # non-empty
        assert "## Analysis Request" not in data["prompt_text"]

    def test_preview_full_mode_no_analysis_request(self, indexed_file):
        db, file_id, _ = indexed_file
        from fastapi import FastAPI

        client = _make_llm_client(FastAPI(), db)
        resp = client.post(
            f"/api/llm/report/{file_id}/prompt-preview",
            json={"quick": False, "web_search": False},
        )
        assert resp.status_code == 200
        assert "## Analysis Request" not in resp.json()["prompt_text"]
        assert "evidence package" in resp.json()["prompt_text"].lower()
        assert "Task Configuration" in resp.json()["prompt_text"]

    def test_preview_404_for_missing_file(self, indexed_file):
        db, _, _ = indexed_file
        from fastapi import FastAPI

        client = _make_llm_client(FastAPI(), db)
        resp = client.post(
            "/api/llm/report/99999/prompt-preview",
            json={"quick": True},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

class TestReportPreflight:
    def test_preflight_rich_log(self, indexed_file):
        db, file_id, _ = indexed_file
        from fastapi import FastAPI

        client = _make_llm_client(FastAPI(), db)
        resp = client.get(f"/api/llm/report/{file_id}/preflight")
        assert resp.status_code == 200
        data = resp.json()
        assert data["needs_focus"] is False
        assert data["has_task_config"] is True
        assert data["has_errors"] is True
        assert data["warning_count"] >= 1

    def test_preflight_sparse_log(self, sparse_indexed_file):
        db, file_id, _ = sparse_indexed_file
        from fastapi import FastAPI

        client = _make_llm_client(FastAPI(), db)
        resp = client.get(f"/api/llm/report/{file_id}/preflight")
        assert resp.status_code == 200
        data = resp.json()
        assert data["needs_focus"] is True
        assert data["has_task_config"] is False
        assert data["has_errors"] is False
        assert data["has_performance"] is False

    def test_preview_json_markdown_format(self, indexed_file):
        db, file_id, _ = indexed_file
        from fastapi import FastAPI

        client = _make_llm_client(FastAPI(), db)
        resp = client.post(
            f"/api/llm/report/{file_id}/prompt-preview",
            json={"quick": False, "payload_format": "json_markdown"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["payload_format"] == "json_markdown"
        assert "### Scalar facts (JSON" in data["prompt_text"]
        assert "Log Aggregates" in data["prompt_text"]

    def test_preview_xml_format(self, indexed_file):
        db, file_id, _ = indexed_file
        from fastapi import FastAPI

        client = _make_llm_client(FastAPI(), db)
        resp = client.post(
            f"/api/llm/report/{file_id}/prompt-preview",
            json={"quick": False, "payload_format": "xml"},
        )
        assert resp.status_code == 200
        assert resp.json()["payload_format"] == "xml"
        assert "<report_context>" in resp.json()["prompt_text"]

    def test_preview_graph_toggle(self, indexed_file):
        db, file_id, _ = indexed_file
        from fastapi import FastAPI

        client = _make_llm_client(FastAPI(), db)
        on = client.post(
            f"/api/llm/report/{file_id}/prompt-preview",
            json={"quick": False, "include_graph": True},
        )
        off = client.post(
            f"/api/llm/report/{file_id}/prompt-preview",
            json={"quick": False, "include_graph": False},
        )
        assert on.status_code == 200
        assert off.status_code == 200
        on_stats = on.json()["context_stats"]
        off_stats = off.json()["context_stats"]
        assert on_stats.get("graph_injected") in (True, False)
        assert off_stats.get("graph_injected") is False

    def test_preview_configuration_focus(self, indexed_file):
        db, file_id, _ = indexed_file
        from fastapi import FastAPI

        client = _make_llm_client(FastAPI(), db)
        resp = client.post(
            f"/api/llm/report/{file_id}/prompt-preview",
            json={"quick": False, "focus_mode": "configuration"},
        )
        assert resp.status_code == 200
        prompt = resp.json()["prompt_text"]
        assert "Task Configuration" in prompt
        assert "Representative error evidence" not in prompt


# ---------------------------------------------------------------------------
# Compare endpoint
# ---------------------------------------------------------------------------

class TestReportCompare:
    def test_compare_rejected_without_env(self, indexed_file, monkeypatch):
        monkeypatch.delenv("LOG_ANALYZER_PROMPT_LAB", raising=False)
        db, file_id, _ = indexed_file
        from fastapi import FastAPI

        client = _make_llm_client(FastAPI(), db)
        resp = client.post(
            f"/api/llm/report/{file_id}/compare",
            json={
                "baseline": {"provider": "gemini", "temperature": 0.3},
                "variants": [],
                "quick": True,
            },
        )
        assert resp.status_code == 403
        assert "PROMPT_LAB" in resp.json()["detail"]

    def test_compare_max_variants(self, indexed_file, monkeypatch):
        monkeypatch.setenv("LOG_ANALYZER_PROMPT_LAB", "1")
        db, file_id, _ = indexed_file
        from fastapi import FastAPI

        client = _make_llm_client(FastAPI(), db)
        too_many = [{"provider": "gemini", "temperature": 0.1 * i} for i in range(6)]
        resp = client.post(
            f"/api/llm/report/{file_id}/compare",
            json={
                "baseline": {"provider": "gemini"},
                "variants": too_many,
                "quick": True,
            },
        )
        assert resp.status_code == 400
        assert "5" in resp.json()["detail"]

    def test_compare_404_for_missing_file(self, indexed_file, monkeypatch):
        monkeypatch.setenv("LOG_ANALYZER_PROMPT_LAB", "1")
        db, _, _ = indexed_file
        from fastapi import FastAPI

        client = _make_llm_client(FastAPI(), db)
        resp = client.post(
            "/api/llm/report/99999/compare",
            json={"baseline": {"provider": "gemini"}, "variants": [], "quick": True},
        )
        assert resp.status_code == 404

    def test_compare_includes_grader_output(self, indexed_file, monkeypatch):
        from tests.test_report_grader import SAMPLE_REPORT

        monkeypatch.setenv("LOG_ANALYZER_PROMPT_LAB", "1")
        db, file_id, _ = indexed_file
        from fastapi import FastAPI
        from backend.llm import endpoints as llm_endpoints
        from backend.llm.endpoints import CompareRunResult

        def _fake_compare(*_args, **_kwargs):
            return CompareRunResult(
                provider="gemini",
                model="test-model",
                temperature=0.3,
                llm_duration_seconds=1.0,
                prompt_tokens=3000,
                completion_tokens=800,
                cost_usd=0.01,
                content=SAMPLE_REPORT,
                content_excerpt=SAMPLE_REPORT[:500],
            )

        monkeypatch.setattr(llm_endpoints, "_run_single_compare", _fake_compare)

        client = _make_llm_client(FastAPI(), db)
        resp = client.post(
            f"/api/llm/report/{file_id}/compare",
            json={
                "baseline": {"provider": "gemini", "temperature": 0.3},
                "variants": [],
                "quick": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["baseline"]["grade"] is not None
        assert "normalized_score" in data["baseline"]["grade"]
        assert data["baseline"]["grade"].get("quality_per_input_token") is not None
