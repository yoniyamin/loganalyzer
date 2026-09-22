"""Tests for evidence payload format variants (Phase 4)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.llm.evidence_compiler import BudgetedSection
from backend.llm.payload_formats import (
    build_scalar_facts_dict,
    normalize_payload_format,
    render_json_markdown,
    render_payload,
    render_xml,
)


def _sample_sections():
    return [
        BudgetedSection(
            category="facts_inventory",
            text="Here is the deterministic evidence package for this log.",
            priority=1,
        ),
        BudgetedSection(
            category="facts_inventory",
            text="## Data Available for This Analysis\n- Errors: 3\n",
            priority=1,
        ),
        BudgetedSection(
            category="error_aggregates",
            text="## Log Aggregates\n| # | Occurrences |\n|---|---|\n| 1 | 3 |",
            priority=1,
        ),
        BudgetedSection(
            category="line_evidence",
            text="**Pattern 1:**\n```\nLINE 100 | SOURCE_UNLOAD | timeout\n```\n",
            priority=3,
        ),
    ]


class TestPayloadFormats:
    def test_normalize_aliases(self):
        assert normalize_payload_format("a") == "markdown"
        assert normalize_payload_format("b") == "json_markdown"
        assert normalize_payload_format("hybrid") == "json_markdown"
        assert normalize_payload_format("c") == "xml"
        assert normalize_payload_format("unknown") == "markdown"

    def test_scalar_facts_dict(self):
        facts = build_scalar_facts_dict(
            {
                "error_summary": {"total": 5, "by_component": {"SORTER": 2}},
                "config": {"source_type": "Oracle", "parallel_apply_threads": 4},
            },
            file_info={"filename": "test.log", "line_count": 1000, "size_bytes": 5000},
        )
        assert facts["errors"]["total"] == 5
        assert facts["task_config"]["source_type"] == "Oracle"
        assert facts["file"]["line_count"] == 1000

    def test_render_markdown_unchanged(self):
        text = render_payload(_sample_sections(), "markdown")
        assert "Log Aggregates" in text
        assert "```" in text

    def test_render_json_markdown(self):
        text = render_json_markdown(
            _sample_sections(),
            summary_data={"error_summary": {"total": 3}},
        )
        assert "### Scalar facts (JSON" in text
        assert '"errors"' in text
        assert "<evidence anchor=" in text
        assert "Log Aggregates" in text
        assert "```json" in text
        payload = text.split("```json")[1].split("```")[0]
        parsed = json.loads(payload)
        assert parsed["errors"]["total"] == 3

    def test_render_xml_wrapper(self):
        text = render_xml(_sample_sections())
        assert text.startswith("<report_context>")
        assert '</report_context>' in text
        assert 'category="error_aggregates"' in text
