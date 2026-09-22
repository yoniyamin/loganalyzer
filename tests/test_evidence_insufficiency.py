"""Tests for Phase 7 evidence insufficiency gating."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.llm.evidence_insufficiency import (
    assess_evidence_insufficiency,
    build_semantic_retrieval_query,
)
from backend.llm.report_generator import ReportGenerator


class TestAssessEvidenceInsufficiency:
    def test_quick_mode_never_insufficient(self):
        result = assess_evidence_insufficiency(
            quick=True,
            focus_mode=None,
            db_error_count=500,
            sqlite_excerpt_count=40,
            warning_count=0,
        )
        assert not result.insufficient

    def test_sufficient_small_error_set(self):
        result = assess_evidence_insufficiency(
            quick=False,
            focus_mode=None,
            db_error_count=5,
            sqlite_excerpt_count=5,
            warning_count=1,
        )
        assert not result.insufficient

    def test_errors_focus_sparse_log(self):
        result = assess_evidence_insufficiency(
            quick=False,
            focus_mode="errors",
            db_error_count=0,
            sqlite_excerpt_count=0,
            warning_count=0,
        )
        assert result.insufficient
        assert any("errors focus" in r for r in result.reasons)

    def test_merge_cap_exceeded(self):
        result = assess_evidence_insufficiency(
            quick=False,
            focus_mode=None,
            db_error_count=45,
            sqlite_excerpt_count=40,
            warning_count=0,
        )
        assert result.insufficient
        assert len(result.reasons) == 1
        assert "exceed deterministic excerpt budget" in result.reasons[0]

    def test_build_semantic_query_uses_codes_and_focus(self):
        q = build_semantic_retrieval_query(
            error_snippets=["ORA-00054 resource busy"],
            error_codes=["[1205]"],
            focus_mode="errors",
        )
        assert "1205" in q
        assert "ORA-00054" in q or "resource busy" in q
        assert "warning" in q.lower()


class TestEmbeddingFallbackWiring:
    def test_skips_embedding_when_sufficient(self, indexed_file, monkeypatch):
        db, file_id, _ = indexed_file
        gen = ReportGenerator(db)
        embed_calls = []
        rag_calls = []

        monkeypatch.setattr(
            gen,
            "embed_file_content",
            lambda fid: embed_calls.append(fid) or {"summaries": 0, "errors": 0, "anomalies": 0},
        )
        monkeypatch.setattr(
            gen,
            "get_rag_context",
            lambda fid, query=None, query_driven=False: rag_calls.append((fid, query_driven)) or {"errors": [], "anomalies": []},
        )

        bundle = gen.build_report_messages(file_id, quick=False, include_chart=False)
        assert embed_calls == []
        assert rag_calls == []
        assert bundle.context_stats.get("embedding_fallback") is False

    def test_triggers_fallback_on_sparse_errors_focus(self, sparse_indexed_file, monkeypatch):
        db, file_id, _ = sparse_indexed_file
        gen = ReportGenerator(db)
        embed_calls = []
        rag_calls = []

        monkeypatch.setattr(
            gen,
            "embed_file_content",
            lambda fid: embed_calls.append(fid) or {"summaries": 0, "errors": 0, "anomalies": 0},
        )
        monkeypatch.setattr(
            gen.vector_store,
            "get_stats",
            lambda _fid: {"total": 0},
        )

        def _fake_rag(fid, query=None, query_driven=False):
            rag_calls.append((query_driven, query))
            return {"errors": ["LINE 99 | semantic hit\nfallback error text"], "anomalies": []}

        monkeypatch.setattr(gen, "get_rag_context", _fake_rag)

        bundle = gen.build_report_messages(
            file_id,
            quick=False,
            focus_mode="errors",
            include_chart=False,
        )
        assert bundle.context_stats.get("embedding_fallback") is True
        assert embed_calls == [file_id]
        assert rag_calls and rag_calls[0][0] is True
        assert rag_calls[0][1]
