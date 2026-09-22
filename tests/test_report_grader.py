"""Tests for deterministic report graders."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.llm.report_grader import grade_report, assert_no_analysis_request_in_prompt


SAMPLE_REPORT = """
## Executive Summary & Health

Health Score: **2/5** (Warning). Primary issue: ODBC timeouts on source unload.

## Key Findings

- **12** occurrences of HYT00 timeout (lines 4821–4900)

## Performance & Full Load Analysis

Structured latency telemetry was not captured.

## Issues & Recommendations

### HYT00 timeout
- **Evidence**: LINE 4821 | SOURCE_UNLOAD | command timed out
- **Interpretation**: Source query exceeded executeTimeout.
- **Recommendations**: Increase `executeTimeout` iteratively.

## Error & Component Mapping

| Code | Component | LINE |
|------|-----------|------|
| HYT00 | SOURCE_UNLOAD | 4821 |

## Risk Assessment

If timeouts persist, full load will fail to complete.
"""


class TestReportGrader:
    def test_good_report_scores_high(self):
        result = grade_report(
            SAMPLE_REPORT,
            input_tokens=3000,
            output_tokens=800,
            allowed_param_names={"executeTimeout"},
            valid_line_numbers={4821},
            authoritative_counts={"HYT00": 12},
        )
        assert result.score >= result.max_score - 1
        assert result.metrics["normalized_score"] >= 0.85
        assert result.quality_per_input_token is not None

    def test_missing_sections_flagged(self):
        result = grade_report("## Executive Summary\n\nBrief.\n")
        assert not result.checks.get("section_key_findings", True)
        assert len(result.issues) > 0

    def test_chart_claim_without_attachment(self):
        bad = SAMPLE_REPORT + "\n\nAs shown in the Latency Over Time graph, latency spiked."
        result = grade_report(bad, chart_attached=False)
        assert not result.checks["no_unsupported_chart_claims"]

    def test_no_analysis_request_guard(self):
        assert_no_analysis_request_in_prompt("[USER]\nEvidence only.\n")
        try:
            assert_no_analysis_request_in_prompt("## Analysis Request\n1. Foo")
            assert False, "expected AssertionError"
        except AssertionError:
            pass
