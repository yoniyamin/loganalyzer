"""Tests for report markdown normalization."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.llm.report_formatter import (
    display_report_content,
    normalize_report_markdown,
    uses_numbered_section_headers,
)
from backend.llm.report_grader import grade_report


NUMBERED_REPORT = """
1. **Executive Summary & Health**

Health Score: **2/5** (Critical). ODBC timeouts dominate.

2. **Key Findings**

- **60** errors indexed

3. **Performance & Full Load Analysis**

Task ran 61,126 seconds///

4. **Issues & Recommendations**

### HYT00
- **Evidence**: LINE 4821

5. **Error & Component Mapping**

| Code | Component | LINE |
| HYT00 | SOURCE_UNLOAD | 4821 |

6. **Risk Assessment**

Full load will fail if timeouts persist.
"""


class TestReportFormatter:
    def test_promotes_numbered_sections_to_h2(self):
        normalized, fixes = normalize_report_markdown(NUMBERED_REPORT)
        assert "## Executive Summary & Health" in normalized
        assert "## Key Findings" in normalized
        assert "1. **Executive Summary" not in normalized
        assert len(fixes) >= 1

    def test_strips_trailing_slashes(self):
        normalized, fixes = normalize_report_markdown(NUMBERED_REPORT)
        assert "seconds///" not in normalized
        assert "seconds" in normalized
        assert any("slash" in f.lower() for f in fixes)

    def test_normalized_report_grades_h2_sections(self):
        normalized, _ = normalize_report_markdown(NUMBERED_REPORT)
        grade = grade_report(normalized)
        assert grade.checks.get("markdown_h2_sections") is True
        assert grade.checks.get("no_truncation_artifacts") is True

    def test_detects_numbered_sections(self):
        assert uses_numbered_section_headers(NUMBERED_REPORT)
        normalized, _ = normalize_report_markdown(NUMBERED_REPORT)
        assert not uses_numbered_section_headers(normalized)

    def test_display_report_content_applies_normalization(self):
        displayed = display_report_content(NUMBERED_REPORT)
        assert "## Executive Summary & Health" in displayed
        assert "seconds///" not in displayed
