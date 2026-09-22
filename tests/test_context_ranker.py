"""Unit tests for backend.core.context_ranker."""
import pytest
from backend.core.context_ranker import (
    rank_neighbors,
    merge_overlapping_windows,
    build_structural_facts_xml,
    deduplicate_facts,
    _approx_tokens,
)


class TestRankNeighbors:
    def test_basic_scoring(self):
        neighbors = [
            {"line_number": 105, "hop": 1, "score": 1.0, "provenance": "EXTRACTED"},
            {"line_number": 500, "hop": 2, "score": 0.5, "provenance": "INFERRED"},
        ]
        ranked = rank_neighbors(neighbors, anchor_line=100, total_lines=1000)

        assert len(ranked) == 2
        assert ranked[0]["line_number"] == 105
        assert ranked[0]["_rank_score"] > ranked[1]["_rank_score"]

    def test_closer_lines_score_higher(self):
        neighbors = [
            {"line_number": 900, "hop": 1, "score": 1.0, "provenance": "EXTRACTED"},
            {"line_number": 102, "hop": 1, "score": 1.0, "provenance": "EXTRACTED"},
        ]
        ranked = rank_neighbors(neighbors, anchor_line=100, total_lines=1000)
        assert ranked[0]["line_number"] == 102

    def test_hop_decay(self):
        neighbors = [
            {"line_number": 110, "hop": 1, "score": 1.0, "provenance": "EXTRACTED"},
            {"line_number": 110, "hop": 3, "score": 1.0, "provenance": "EXTRACTED"},
        ]
        ranked = rank_neighbors(neighbors, anchor_line=100, total_lines=1000)
        assert ranked[0]["hop"] == 1
        assert ranked[0]["_rank_score"] > ranked[1]["_rank_score"]

    def test_extracted_confidence_bonus(self):
        neighbors = [
            {"line_number": 110, "hop": 1, "score": 1.0, "provenance": "INFERRED"},
            {"line_number": 110, "hop": 1, "score": 1.0, "provenance": "EXTRACTED"},
        ]
        ranked = rank_neighbors(neighbors, anchor_line=100, total_lines=1000)
        assert ranked[0]["provenance"] == "EXTRACTED"

    def test_empty_input(self):
        assert rank_neighbors([], 100, 1000) == []

    def test_missing_line_number(self):
        neighbors = [{"hop": 1, "score": 0.5, "provenance": "EXTRACTED"}]
        ranked = rank_neighbors(neighbors, 100, 1000)
        assert len(ranked) == 1


class TestMergeOverlappingWindows:
    def test_no_overlap(self):
        snippets = [
            {"line_number": 10},
            {"line_number": 50},
        ]
        groups = merge_overlapping_windows(snippets, window_before=3, window_after=3)
        assert len(groups) == 2

    def test_overlapping_merge(self):
        snippets = [
            {"line_number": 10},
            {"line_number": 12},
        ]
        groups = merge_overlapping_windows(snippets, window_before=3, window_after=3)
        assert len(groups) == 1
        assert len(groups[0]["items"]) == 2

    def test_max_window_cap(self):
        snippets = [{"line_number": i} for i in range(0, 50, 2)]
        groups = merge_overlapping_windows(snippets, window_before=3, window_after=3, max_window=20)
        for g in groups:
            assert g["end"] - g["start"] <= 20

    def test_empty_input(self):
        assert merge_overlapping_windows([]) == []

    def test_none_line_numbers_skipped(self):
        snippets = [
            {"line_number": None},
            {"line_number": 10},
        ]
        groups = merge_overlapping_windows(snippets, window_before=3, window_after=3)
        assert len(groups) == 1


class TestBuildStructuralFactsXml:
    def test_basic_output(self):
        neighbors = [
            {"edge_type": "co_occurs_within", "line_number": 42, "label": "ORA-00054",
             "context_lines": ["error line 1", "error line 2"]},
        ]
        xml = build_structural_facts_xml(neighbors, anchor_line=40)
        assert '<structural_facts anchor="line:40">' in xml
        assert "c1" in xml
        assert "co_occurs_within" in xml
        assert "</structural_facts>" in xml

    def test_token_budget_enforcement(self):
        neighbors = [
            {"edge_type": "test", "line_number": i, "label": f"item_{i}",
             "context_lines": ["x" * 200]}
            for i in range(100)
        ]
        xml = build_structural_facts_xml(neighbors, anchor_line=50, max_tokens=200)
        assert xml.count("<c") < 100

    def test_empty_neighbors(self):
        xml = build_structural_facts_xml([], anchor_line=10)
        assert '<structural_facts anchor="line:10">' in xml
        assert "</structural_facts>" in xml

    def test_xml_escaping(self):
        neighbors = [
            {"edge_type": "test", "line_number": 5, "label": 'foo<bar>&"baz"'},
        ]
        xml = build_structural_facts_xml(neighbors, anchor_line=3)
        assert "&lt;" in xml
        assert "&amp;" in xml
        assert "&quot;" in xml


class TestDeduplicateFacts:
    def test_dedup_by_line(self):
        facts = [
            {"line_number": 10, "label": "a"},
            {"line_number": 10, "label": "b"},
            {"line_number": 20, "label": "c"},
        ]
        result = deduplicate_facts(facts)
        assert len(result) == 2
        assert result[0]["label"] == "a"

    def test_dedup_by_label_when_no_line(self):
        facts = [
            {"label": "ORA-00054"},
            {"label": "ORA-00054"},
            {"label": "ORA-01555"},
        ]
        result = deduplicate_facts(facts)
        assert len(result) == 2

    def test_empty_input(self):
        assert deduplicate_facts([]) == []

    def test_mixed_dedup(self):
        facts = [
            {"line_number": 10, "label": "a"},
            {"line_number": 20, "label": "b"},
            {"label": "c"},
            {"label": "c"},
        ]
        result = deduplicate_facts(facts)
        assert len(result) == 3


class TestApproxTokens:
    def test_short_text(self):
        assert _approx_tokens("hello") >= 1

    def test_empty(self):
        assert _approx_tokens("") == 1

    def test_longer_text(self):
        text = "word " * 100
        tokens = _approx_tokens(text)
        assert 80 < tokens < 200
