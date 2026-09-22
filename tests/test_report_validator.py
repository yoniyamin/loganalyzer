"""Tests for post-LLM report validation."""
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.llm.report_validator import (
    ValidationContext,
    build_correction_user_message,
    build_validation_context,
    compute_passed,
    extract_authoritative_counts,
    extract_tuning_allowlist,
    validate_and_correct,
    validate_report,
)
from tests.test_report_grader import SAMPLE_REPORT


class TestReportValidator:
    def test_good_report_passes(self):
        ctx = ValidationContext(
            chart_attached=False,
            allowed_param_names={"executeTimeout"},
            authoritative_counts={"HYT00": 12},
            valid_line_numbers={4821},
        )
        result = validate_report(
            SAMPLE_REPORT,
            ctx,
            input_tokens=3000,
            output_tokens=800,
        )
        assert result.passed
        assert result.grade.metrics["normalized_score"] >= 0.85

    def test_missing_sections_fail(self):
        ctx = ValidationContext(quick=False)
        result = validate_report("## Executive Summary\n\nBrief note.\n", ctx)
        assert not result.passed
        assert any("Missing section" in issue for issue in result.issues)

    def test_quick_mode_passes_minimal(self):
        ctx = ValidationContext(quick=True)
        result = validate_report("Quick summary only.", ctx)
        assert result.passed

    def test_completion_budget_issue(self):
        ctx = ValidationContext(max_completion_tokens=500, quick=False)
        result = validate_report(
            SAMPLE_REPORT,
            ctx,
            output_tokens=900,
        )
        assert any("Completion used" in issue for issue in result.issues)
        assert not result.passed

    def test_extract_authoritative_counts(self):
        prompt = (
            "## Log Aggregates (computed — authoritative)\n"
            "**Distinct error codes:**\n"
            "- `[HYT00]` × 12\n"
        )
        counts = extract_authoritative_counts(prompt)
        assert counts == {"[HYT00]": 12}

    def test_extract_tuning_allowlist(self):
        prompt = (
            "## Tuning Reference\n"
            "| Param | Description |\n"
            "| `executeTimeout` | Query timeout |\n"
            "## Other\n"
        )
        allowed = extract_tuning_allowlist(prompt)
        assert "executeTimeout" in allowed

    def test_build_correction_message_lists_issues(self):
        msg = build_correction_user_message(["Missing health score", "Bad param"])
        assert "Missing health score" in msg
        assert "complete" in msg.lower()

    def test_validate_and_correct_retries_once(self):
        bad_report = "## Executive Summary\n\nNo health score.\n"
        fixed_report = SAMPLE_REPORT
        mock_llm = MagicMock(
            return_value=SimpleNamespace(
                content=fixed_report,
                prompt_tokens=100,
                completion_tokens=200,
                cost_usd=0.01,
            )
        )
        ctx = ValidationContext(
            quick=False,
            allowed_param_names={"executeTimeout"},
            valid_line_numbers={4821},
        )
        result = validate_and_correct(
            bad_report,
            ctx,
            messages=[{"role": "system", "content": "sys"}, {"role": "user", "content": "evidence"}],
            llm_call=mock_llm,
        )
        assert mock_llm.called
        assert result.correction_applied
        assert result.final_content == fixed_report

    def test_build_validation_context_from_bundle(self, indexed_file):
        from backend.llm.report_generator import ReportGenerator

        db, file_id, _log_path = indexed_file
        gen = ReportGenerator(db)
        bundle = gen.build_report_messages(file_id, quick=False, include_chart=False)
        ctx = build_validation_context(db, file_id, bundle)
        assert isinstance(ctx.chart_attached, bool)

    def test_compute_passed_requires_health_and_sections(self):
        from backend.llm.report_grader import grade_report

        grade = grade_report("## Executive Summary\n\nHealth Score: 2/5\n")
        assert not compute_passed(grade, quick=False, extra_issues=[])
