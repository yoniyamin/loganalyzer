"""Tests for FullLoadExtractor and full-load log patterns."""
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from backend.core.extractors import FullLoadExtractor
from backend.core.patterns import (
    FL_INIT_SEGMENTED_RE,
    FL_START_SEGMENT_RE,
    FL_UNLOAD_SEGMENT_DONE_RE,
    FL_LOAD_SEGMENT_DONE_RE,
    FL_TM_SEGMENT_DONE_RE,
    FL_RELOAD_RE,
    FL_SEGMENT_WHERE_RE,
)


FL_TEST_DIR = Path(r"c:\Users\YAM\OneDrive - QlikTech Inc\Documents\POC Docs\Broadridge\FL_TEST")
JULY_LOG = FL_TEST_DIR / "reptask_GLOSS_trading_ALL-24July2026.log"
AUG_LOG = FL_TEST_DIR / "reptask_GLOSS_trading_ALL-05AUG2026.txt"


def _line(thread, offset, component, severity, message, base=None):
    base = base or datetime(2026, 8, 4, 9, 16, 36)
    ts = (base + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{thread}: {ts} [{component:<16}]{severity}:  {message}\n", base + timedelta(seconds=offset)


class TestFullLoadPatterns:
    def test_init_segmented(self):
        m = FL_INIT_SEGMENTED_RE.search(
            "Start initializing segmented table 'dbo'.'event_wil' (Id = 1) by subtask 1. Start load timestamp ABC"
        )
        assert m
        assert m.group(1) == "dbo"
        assert m.group(2) == "event_wil"
        assert m.group(3) == "1"

    def test_start_segment(self):
        m = FL_START_SEGMENT_RE.search(
            "Start loading segment #3 of 6 of table 'dbo'.'event_wil' (Id = 1) by subtask 3. Start load timestamp ABC"
        )
        assert m
        assert m.group(1) == "3"
        assert m.group(2) == "6"
        assert m.group(6) == "3"

    def test_unload_load_finish(self):
        u = FL_UNLOAD_SEGMENT_DONE_RE.search(
            "Unload finished for segment #1 of segmented table 'dbo'.'event_wil' (Id = 1). 179514 rows sent."
        )
        assert u and u.group(5) == "179514"
        l = FL_LOAD_SEGMENT_DONE_RE.search(
            "Load finished for segment #1 of segmented table 'dbo'.'event_wil' (Id = 1). "
            "179514 rows received. 0 rows skipped. Volume transferred 117761184."
        )
        assert l and l.group(5) == "179514" and l.group(7) == "117761184"

    def test_reload(self):
        m = FL_RELOAD_RE.search(
            "Reloading table 1 because subtask #5 that was loading segment 5 finished with error, "
            "and some data from the segment was already loaded to the target"
        )
        assert m
        assert m.group(1) == "1"
        assert m.group(2) == "5"
        assert m.group(3) == "5"

    def test_where_predicate(self):
        m = FL_SEGMENT_WHERE_RE.search(
            "Order by '', Resume Where '', Transformation Where ' ( ([event_id_wil] <= 3729277448.20) ) '"
        )
        assert m
        assert "event_id_wil" in m.group(1)


class TestFullLoadExtractor:
    def test_segment_cycle_and_gap(self):
        ext = FullLoadExtractor()
        base = datetime(2026, 8, 4, 9, 16, 36)

        events = [
            (0, "0001", "TASK_MANAGER", "I",
             "Task 'GLOSS_trading_ALL' running full load and CDC in fresh start mode"),
            (1, "0001", "TASK_MANAGER", "I",
             "Start initializing segmented table 'dbo'.'event_wil' (Id = 1) by subtask 1. Start load timestamp ABC"),
            (2, "0001", "TASK_MANAGER", "I",
             "Completed target preparation for segmented table 'dbo'.'event_wil' (Id = 1) by subtask 1"),
            (3, "0001", "TASK_MANAGER", "I",
             "Start loading segment #1 of 6 of table 'dbo'.'event_wil' (Id = 1) by subtask 1. Start load timestamp ABC"),
            (3, "0002", "SOURCE_UNLOAD", "T",
             "Command 'UNLOAD_TABLE_SEGMENT' received in component 'st_1_Sybase_t'"),
            (4, "0002", "SOURCE_UNLOAD", "T",
             "Order by '', Resume Where '', Transformation Where ' ( ([event_id_wil] <= 100) ) '"),
            (10, "0002", "SOURCE_UNLOAD", "I",
             "Unload finished for segment #1 of segmented table 'dbo'.'event_wil' (Id = 1). 1000 rows sent."),
            (12, "0003", "TARGET_LOAD", "I",
             "Load finished for segment #1 of segmented table 'dbo'.'event_wil' (Id = 1). "
             "1000 rows received. 0 rows skipped. Volume transferred 50000."),
            (12, "0001", "TASK_MANAGER", "I",
             "Load finished for segment #1 of table 'dbo'.'event_wil' (Id = 1) by subtask 1. 1000 records transferred."),
        ]

        for offset, thread, comp, sev, msg in events:
            line, ts = _line(thread, offset, comp, sev, msg, base)
            ext.feed(line, offset + 1, ts, comp)

        report = ext.build_report()
        assert report["summary"]["tables_total"] == 1
        assert report["summary"]["task_name"] == "GLOSS_trading_ALL"
        assert report["summary"]["running_mode"] == "fresh start"
        t = report["tables"][0]
        assert t["table_name"] == "dbo.event_wil"
        assert t["segment_count"] == 6
        assert len(t["segments"]) == 1
        seg = t["segments"][0]
        assert seg["rows_sent"] == 1000
        assert seg["rows_received"] == 1000
        assert seg["gap_unload_to_load_seconds"] == pytest.approx(2.0)
        assert seg["unload_duration_seconds"] == pytest.approx(7.0)
        assert "event_id_wil" in (seg.get("split_predicate") or "")

    def test_reload_increments_attempt(self):
        ext = FullLoadExtractor()
        base = datetime(2026, 7, 23, 12, 57, 42)
        seq = [
            (0, "Start initializing segmented table 'dbo'.'event_stream_wil' (Id = 1) by subtask 1. Start load timestamp A"),
            (1, "Start loading segment #5 of 6 of table 'dbo'.'event_stream_wil' (Id = 1) by subtask 5. Start load timestamp A"),
            (100, "Reloading table 1 because subtask #5 that was loading segment 5 finished with error, "
                  "and some data from the segment was already loaded to the target"),
            (101, "Start initializing segmented table 'dbo'.'event_stream_wil' (Id = 1) by subtask 3. Start load timestamp B"),
            (102, "Start loading segment #1 of 6 of table 'dbo'.'event_stream_wil' (Id = 1) by subtask 3. Start load timestamp B"),
        ]
        for offset, msg in seq:
            line, ts = _line("0001", offset, "TASK_MANAGER", "I", msg, base)
            ext.feed(line, offset + 1, ts, "TASK_MANAGER")

        report = ext.build_report()
        t = report["tables"][0]
        assert t["reload_count"] == 1
        assert t["attempts_total"] == 2
        assert report["summary"]["reload_events"] == 1
        assert any(i["type"] == "reload_loop" for i in report["insights"])


@pytest.mark.skipif(not JULY_LOG.exists(), reason="July FL_TEST log not present")
class TestFullLoadAgainstJulySample:
    def test_july_reload_loop(self):
        ext = FullLoadExtractor()
        with open(JULY_LOG, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh, 1):
                if not any(c in line for c in ("TASK_MANAGER", "SOURCE_UNLOAD", "TARGET_LOAD")):
                    continue
                from backend.core.patterns import extract_timestamp, LINE_FULL_RE
                ts = extract_timestamp(line)
                m = LINE_FULL_RE.match(line)
                comp = m.group(3).strip() if m else None
                ext.feed(line, i, ts, comp)

        report = ext.build_report()
        assert report["summary"]["tables_total"] >= 2
        assert report["summary"]["reload_events"] >= 1
        names = {t["table_name"] for t in report["tables"]}
        assert "dbo.event_stream_wil" in names
        assert "dbo.event_wil" in names
        stream = next(t for t in report["tables"] if t["table_name"] == "dbo.event_stream_wil")
        assert stream["reload_count"] >= 1


@pytest.mark.skipif(not AUG_LOG.exists(), reason="Aug FL_TEST log not present")
class TestFullLoadAgainstAugSample:
    def test_aug_segments_and_splits(self):
        ext = FullLoadExtractor()
        with open(AUG_LOG, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh, 1):
                if not any(c in line for c in ("TASK_MANAGER", "SOURCE_UNLOAD", "TARGET_LOAD")):
                    continue
                from backend.core.patterns import extract_timestamp, LINE_FULL_RE
                ts = extract_timestamp(line)
                m = LINE_FULL_RE.match(line)
                comp = m.group(3).strip() if m else None
                ext.feed(line, i, ts, comp)

        report = ext.build_report()
        assert report["summary"]["tables_total"] >= 1
        t = report["tables"][0]
        assert t["table_name"] == "dbo.event_wil"
        assert t["segment_count"] == 6
        complete = [s for s in t["segments"] if s["status"] == "complete"]
        assert len(complete) >= 4
        with_split = [s for s in t["segments"] if s.get("split_predicate")]
        assert len(with_split) >= 1
        # Segment 1 should have ~1s unload->load gap
        seg1 = next(s for s in t["segments"] if s["segment_num"] == 1)
        assert seg1["rows_received"] == 179514
        assert seg1["gap_unload_to_load_seconds"] is not None
        assert seg1["gap_unload_to_load_seconds"] <= 5


class TestFullLoadLlmContext:
    def test_condense_and_prompt_include_fl(self):
        from backend.core.extractors import analyze_full_load_file, condense_full_load_for_llm
        from backend.llm.prompts import build_analysis_prompt, build_quick_summary_prompt, _build_context_inventory

        if not AUG_LOG.exists():
            pytest.skip("Aug FL_TEST log not present")

        report = analyze_full_load_file(str(AUG_LOG))
        condensed = condense_full_load_for_llm(report)
        assert condensed is not None
        assert condensed["available"] is True
        assert condensed["summary"]["tables_total"] >= 1

        summary = {
            "latency_profile": {"data_points": 0},
            "bottleneck": {"primary": "unknown"},
            "error_summary": {"total": 0},
            "full_load_activity": condensed,
        }
        inventory = _build_context_inventory(summary, [], [], None, None, None)
        assert "Full Load Activity" in inventory

        prompt = build_analysis_prompt(summary, [], [], sanitize_log_payload=False)
        assert "### Full Load Activity" in prompt
        assert "dbo.event_wil" in prompt
        assert "Full-load insights" in prompt or "slow_segment" in prompt.lower() or "in progress" in prompt.lower()

        quick = build_quick_summary_prompt(summary, sanitize_log_payload=False)
        assert "full_load_tables_total" in quick
        assert "full_load_rows_received" in quick

    def test_july_reload_flagged_critical(self):
        from backend.core.extractors import analyze_full_load_file, condense_full_load_for_llm
        from backend.llm.prompts import build_analysis_prompt

        if not JULY_LOG.exists():
            pytest.skip("July FL_TEST log not present")

        condensed = condense_full_load_for_llm(analyze_full_load_file(str(JULY_LOG)))
        assert condensed and condensed["summary"]["reload_events"] >= 1
        prompt = build_analysis_prompt(
            {"full_load_activity": condensed, "error_summary": {"total": 0}},
            [],
            [],
            sanitize_log_payload=False,
        )
        assert "Full load reload loops" in prompt or "reload" in prompt.lower()
