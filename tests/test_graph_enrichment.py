"""Tests for Phase 5 gated graph enrichment."""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.llm.graph_enrichment import (
    build_gated_graph_context,
    extract_anchor_lines,
    should_attempt_graph_injection,
)


SAMPLE_ERRORS = [
    "LINE 100 | 2024-01-01 10:00:00 | SOURCE_UNLOAD\nHYT00 timeout on SELECT",
    "LINE 200 | 2024-01-01 10:01:00 | TARGET_APPLY\nORA-00054 resource busy",
]


class TestGraphEnrichment:
    def test_extract_anchor_lines(self):
        lines = extract_anchor_lines(SAMPLE_ERRORS, top_n=2)
        assert lines == [100, 200]

    def test_should_skip_configuration_focus(self):
        assert not should_attempt_graph_injection(SAMPLE_ERRORS, focus_mode="configuration")

    def test_gated_injection_on_indexed_file(self, indexed_file):
        db, file_id, _ = indexed_file
        result = build_gated_graph_context(db, file_id, SAMPLE_ERRORS)
        # Sample log has real errors — graph may inject if neighborhood is strong
        assert result.anchor_lines == [100, 200]
        if result.injected:
            assert "Structural context" in (result.xml_block or "")
            assert "structural_facts" in (result.xml_block or "").lower() or "<" in (result.xml_block or "")

    def test_respects_include_graph_false(self, indexed_file):
        db, file_id, _ = indexed_file
        result = build_gated_graph_context(
            db, file_id, SAMPLE_ERRORS, include_graph=False,
        )
        assert not result.injected
        assert result.xml_block is None

    def test_skips_when_structural_facts_returns_none(self, indexed_file):
        db, file_id, _ = indexed_file
        with patch(
            "backend.llm.error_resolution._build_structural_facts",
            return_value=None,
        ):
            result = build_gated_graph_context(db, file_id, SAMPLE_ERRORS)
        assert not result.injected
        assert result.skipped_weak
