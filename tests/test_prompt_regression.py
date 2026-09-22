"""Phase 0a — golden regression corpus contract tests."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.llm.report_grader import assert_no_analysis_request_in_prompt
from backend.llm.report_generator import ReportGenerator

CORPUS_PATH = Path(__file__).parent / "fixtures" / "prompt_regression" / "corpus.json"


def _load_corpus():
    with open(CORPUS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _resolve_fixture(request, name: str):
    if name == "indexed_file":
        return request.getfixturevalue("indexed_file")
    if name == "sparse_indexed_file":
        return request.getfixturevalue("sparse_indexed_file")
    pytest.skip(f"Unknown fixture: {name}")


def _run_case(request, case: dict):
    db, file_id, _ = _resolve_fixture(request, case["fixture"])
    gen = ReportGenerator(db)
    bundle = gen.build_report_messages(
        file_id,
        quick=case.get("quick", False),
        focus_mode=case.get("focus_mode"),
        include_chart=False,
        fetch_external=False,
        cancel_check=False,
        payload_format=case.get("payload_format", "markdown"),
        include_graph=case.get("include_graph", True),
    )
    return bundle


class TestPromptRegressionCorpus:
    @pytest.fixture(autouse=True)
    def _corpus(self):
        self.corpus = _load_corpus()

    def test_corpus_file_valid(self):
        assert self.corpus["version"] == 1
        assert len(self.corpus["cases"]) >= 8

    @pytest.mark.parametrize(
        "case_id",
        [c["id"] for c in _load_corpus()["cases"] if c.get("status") == "active"],
    )
    def test_active_corpus_preview_contract(self, request, case_id):
        case = next(c for c in _load_corpus()["cases"] if c["id"] == case_id)
        bundle = _run_case(request, case)
        prompt = bundle.prompt_text.lower()

        assert bundle.est_tokens > 0
        assert_no_analysis_request_in_prompt(bundle.prompt_text)

        checks = case.get("checks") or []
        if "evidence_preamble" in checks:
            assert "evidence package" in prompt
        if "task_config" in checks:
            assert "task configuration" in prompt
        if "no_representative_errors" in checks:
            assert "representative error evidence" not in prompt
        if "configuration_focus" in checks:
            assert "configuration review" in prompt
        if "json_facts_block" in checks:
            assert "scalar facts (json" in prompt
        if "log_aggregates" in checks:
            assert "log aggregates" in prompt

    def test_sparse_preflight_matches_corpus(self, sparse_indexed_file):
        db, file_id, _ = sparse_indexed_file
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from backend.llm.endpoints import router
        from backend.database import get_db

        app = FastAPI()
        app.include_router(router, prefix="/api")

        def _override():
            yield db

        app.dependency_overrides[get_db] = _override
        client = TestClient(app)
        resp = client.get(f"/api/llm/report/{file_id}/preflight")
        assert resp.status_code == 200
        assert resp.json()["needs_focus"] is True
