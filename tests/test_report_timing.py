"""Tests for report timing (llm_duration_seconds, generation_duration_seconds)
and the unified build_report_messages() prompt builder."""
import os
import sys
import sqlite3
from unittest.mock import MagicMock, patch
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# build_report_messages parity
# ---------------------------------------------------------------------------

class TestBuildReportMessages:
    """build_report_messages returns a consistent ReportPromptBundle."""

    def test_returns_bundle_with_expected_fields(self, indexed_file):
        db, file_id, _ = indexed_file
        from backend.llm.report_generator import ReportGenerator, ReportPromptBundle

        gen = ReportGenerator(db)
        bundle = gen.build_report_messages(
            file_id, quick=True, web_search=False, cancel_check=False,
        )
        assert isinstance(bundle, ReportPromptBundle)
        assert bundle.est_tokens > 0
        assert len(bundle.messages) >= 2
        assert "errors" in bundle.context_stats
        assert bundle.prompt_text  # non-empty

    def test_estimate_cost_uses_same_builder(self, indexed_file):
        db, file_id, _ = indexed_file
        from backend.llm.report_generator import ReportGenerator

        gen = ReportGenerator(db)
        bundle = gen.build_report_messages(
            file_id, quick=False, web_search=False, cancel_check=False,
        )
        est = gen.estimate_cost(file_id, quick=False, web_search=False)
        assert est["prompt_tokens"] == bundle.est_tokens


# ---------------------------------------------------------------------------
# Timing in generate_report
# ---------------------------------------------------------------------------

class TestReportTimingFields:
    """generate_report must return llm_duration_seconds and generation_duration_seconds."""

    @patch("backend.llm.report_generator.ReportGenerator.build_report_messages")
    def test_timing_fields_present(self, mock_build, indexed_file):
        db, file_id, _ = indexed_file
        from backend.llm.report_generator import ReportGenerator, ReportPromptBundle

        mock_bundle = ReportPromptBundle(
            messages=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "test prompt"},
            ],
            est_tokens=100,
            context_stats={"errors": 0, "anomalies": 0, "kb": 0, "release_notes": 0},
        )
        mock_build.return_value = mock_bundle

        mock_result = MagicMock()
        mock_result.model = "test-model"
        mock_result.content = "Report content here"
        mock_result.prompt_tokens = 100
        mock_result.completion_tokens = 50
        mock_result.total_tokens = 150
        mock_result.cost_usd = 0.0
        mock_result.finish_reason = "stop"

        gen = ReportGenerator(db)
        gen.provider = "lmstudio"
        with patch.object(gen.lmstudio_client, "complete", return_value=mock_result):
            result = gen.generate_report(file_id, quick=True)

        assert "llm_duration_seconds" in result
        assert "generation_duration_seconds" in result
        assert result["llm_duration_seconds"] >= 0
        assert result["generation_duration_seconds"] >= result["llm_duration_seconds"]
        assert result["focus_mode"] is None


# ---------------------------------------------------------------------------
# Database migration
# ---------------------------------------------------------------------------

class TestLLMReportMigration:
    """_migrate_schema adds new columns to llm_reports."""

    def test_migration_adds_columns(self, tmp_path):
        db_file = tmp_path / "migrate_test.db"
        conn = sqlite3.connect(str(db_file))
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE llm_reports (
                id INTEGER PRIMARY KEY,
                file_id INTEGER,
                model_used TEXT,
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                report_content TEXT,
                generated_at DATETIME
            )
        """)
        conn.commit()

        cols_before = {row[1] for row in cur.execute("PRAGMA table_info(llm_reports)").fetchall()}
        assert "llm_duration_seconds" not in cols_before

        from backend.database import _alter_if_missing, _get_columns
        cols = _get_columns(cur, "llm_reports")
        _alter_if_missing(cur, "llm_reports", cols, [
            ("llm_duration_seconds", "REAL"),
            ("generation_duration_seconds", "REAL"),
            ("focus_mode", "TEXT"),
            ("web_search", "INTEGER"),
            ("quick", "INTEGER"),
        ])
        conn.commit()

        cols_after = {row[1] for row in cur.execute("PRAGMA table_info(llm_reports)").fetchall()}
        assert "llm_duration_seconds" in cols_after
        assert "generation_duration_seconds" in cols_after
        assert "focus_mode" in cols_after
        conn.close()


# ---------------------------------------------------------------------------
# Cached report returns stored durations
# ---------------------------------------------------------------------------

class TestCachedReportDurations:
    """GET and POST (cached) paths must return stored duration fields."""

    def test_get_report_includes_durations(self, indexed_file):
        db, file_id, _ = indexed_file
        from backend.database import LLMReport

        report = LLMReport(
            file_id=file_id,
            model_used="test-model",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.0,
            report_content="# Test Report",
            generated_at=datetime.utcnow(),
            llm_duration_seconds=5.2,
            generation_duration_seconds=12.7,
            focus_mode="performance",
        )
        db.add(report)
        db.commit()

        from fastapi.testclient import TestClient
        from backend.llm.endpoints import router
        from backend.database import get_db
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router, prefix="/api")

        def _override():
            try:
                yield db
            finally:
                pass

        app.dependency_overrides[get_db] = _override
        client = TestClient(app)

        resp = client.get(f"/api/llm/report/{file_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is True
        assert data["llm_duration_seconds"] == 5.2
        assert data["generation_duration_seconds"] == 12.7
        assert data["focus_mode"] == "performance"

    def test_legacy_report_returns_null_durations(self, indexed_file):
        db, file_id, _ = indexed_file
        from backend.database import LLMReport

        report = LLMReport(
            file_id=file_id,
            model_used="legacy-model",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.0,
            report_content="# Legacy Report",
            generated_at=datetime.utcnow(),
        )
        db.add(report)
        db.commit()

        from fastapi.testclient import TestClient
        from backend.llm.endpoints import router
        from backend.database import get_db
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router, prefix="/api")

        def _override():
            try:
                yield db
            finally:
                pass

        app.dependency_overrides[get_db] = _override
        client = TestClient(app)

        resp = client.get(f"/api/llm/report/{file_id}")
        data = resp.json()
        assert data["exists"] is True
        assert data["llm_duration_seconds"] is None
        assert data["generation_duration_seconds"] is None
