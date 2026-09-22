"""Tests for deterministic evidence compiler."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.llm.evidence_compiler import (
    EvidenceBudgets,
    BudgetedSection,
    build_authoritative_facts,
    build_error_aggregates,
    build_focus_payload_plan,
    detect_tuning_modes,
    enforce_budgets,
    format_task_config,
    format_warning_tail,
    select_representative_excerpts,
)


SAMPLE_ERRORS = [
    "LINE 100 | 2024-01-01 10:00:00 | SOURCE_UNLOAD | [30149] HYT00 timeout on SELECT\nDetails A",
    "LINE 200 | 2024-01-01 10:01:00 | SOURCE_UNLOAD | [30149] HYT00 timeout on SELECT\nDetails B",
    "LINE 300 | 2024-01-01 10:02:00 | TARGET_APPLY | [12345] PK violation\nDetails C",
]


class TestEvidenceCompiler:
    def test_build_error_aggregates_counts(self):
        block = build_error_aggregates(SAMPLE_ERRORS)
        assert "Occurrences" in block
        assert "| 2 |" in block or "| 2|" in block.replace(" ", "")

    def test_select_representative_top_n(self):
        quotes = select_representative_excerpts(SAMPLE_ERRORS, top_n=2)
        assert len(quotes) == 2
        assert all("LINE" in q for q in quotes)

    def test_format_task_config(self):
        text = format_task_config({
            "source_type": "Oracle",
            "target_type": "Databricks on AWS",
            "parallel_apply_threads": 4,
            "bulk_timeout_ms": 30000,
        })
        assert "Task Configuration" in text
        assert "Oracle" in text
        assert "parallel_apply_threads" in text.lower() or "Parallel apply" in text

    def test_authoritative_facts_latency_delta(self):
        summary = {
            "latency_profile": {
                "data_points": 100,
                "source": {"avg": 1.0},
                "target": {"avg": 2.0},
                "handling": {"avg": 0.5},
            },
            "bottleneck": {"primary": "target"},
        }
        facts = build_authoritative_facts(summary)
        assert "Target − Source" in facts
        assert "+100%" in facts or "+1.00s" in facts

    def test_detect_tuning_modes_timeout(self):
        modes = detect_tuning_modes({}, SAMPLE_ERRORS)
        assert "timeout" in modes

    def test_detect_tuning_modes_batch_for_databricks(self):
        summary = {
            "config": {"target_type": "Databricks on AWS"},
            "batch_profile": {"total_batches": 10},
        }
        modes = detect_tuning_modes(summary, [])
        assert "batch" in modes

    def test_enforce_budgets_never_drops_priority_one(self):
        sections = [
            BudgetedSection("error_aggregates", "X" * 4000, priority=1),
            BudgetedSection("kb_release_notes", "Y" * 4000, priority=5),
        ]
        trimmed, report = enforce_budgets(sections, EvidenceBudgets(total_input_target=500))
        assert len(trimmed) == 2
        assert report["total_tokens_after"] <= report["total_tokens_before"]

    def test_focus_plan_configuration_skips_perf(self):
        plan = build_focus_payload_plan("configuration", {"latency_profile": {"data_points": 50}})
        assert plan.include_full_tuning_reference
        assert not plan.include_performance_telemetry
        assert not plan.include_representative_quotes

    def test_focus_plan_errors_includes_warning_tail(self):
        plan = build_focus_payload_plan("errors", {})
        assert plan.include_warning_tail

    def test_format_warning_tail(self):
        text = format_warning_tail(["LINE 10 | x | SORTER\nMemory threshold reached"])
        assert "Recent warnings" in text
        assert "LINE 10" in text
