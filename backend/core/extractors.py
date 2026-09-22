"""Shared extraction logic for batch, table stats, and task config.

Used by the indexer at ingest time so the cockpit can read from SQLite
rather than re-parsing the raw log.
"""
import json
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.core.patterns import (
    BATCH_START_RE, BATCH_END_RE, APPLY_SEQ_RANGE_RE,
    FINISHED_APPLYING_RE, START_APPLYING_RE,
    MERGE_STATEMENT_RE, NO_PK_RE,
    BULK_TIMEOUT_RE, BULK_TIMEOUT_MIN_RE, BULK_MAX_FILE_SIZE_RE,
    PARALLEL_APPLY_RE, SOURCE_ENDPOINT_RE, TARGET_ENDPOINT_RE,
    FL_INIT_SEGMENTED_RE, FL_INIT_TABLE_RE, FL_START_SEGMENT_RE, FL_START_TABLE_RE,
    FL_UNLOAD_SEGMENT_DONE_RE, FL_UNLOAD_TABLE_DONE_RE,
    FL_LOAD_SEGMENT_DONE_RE, FL_LOAD_TABLE_DONE_RE,
    FL_TM_SEGMENT_DONE_RE, FL_TM_TABLE_DONE_RE,
    FL_RELOAD_RE, FL_SEGMENT_WHERE_RE, FL_UNLOAD_CMD_RE,
    FL_COMPLETED_RE, FL_RUNNING_MODE_RE, FL_TARGET_PREP_RE,
    classify_batch_closure_reason, extract_table_name, extract_timestamp,
)


class BatchExtractor:
    """Tracks batch events and produces LogBatch-ready dicts."""

    def __init__(self):
        self._start_time: Optional[datetime] = None
        self._changes: int = 0
        self._applies: int = 0
        self._tables: Set[str] = set()
        self._closure_reason: Optional[str] = None
        self.batches: List[Dict[str, Any]] = []

    def feed(self, line: str, line_num: int, timestamp: Optional[datetime], component: Optional[str]):
        if component != "TARGET_APPLY":
            return

        if BATCH_START_RE.search(line):
            self._start_time = timestamp
            self._changes = 0
            self._applies = 0
            self._tables = set()
            self._closure_reason = None

        if 'Finish Bulk' in line or 'Finish bulk' in line:
            self._closure_reason = classify_batch_closure_reason(line)

        if 'same bulk' in line and ('same PK' in line or 'changes PK' in line):
            self._closure_reason = classify_batch_closure_reason(line)

        seq_match = APPLY_SEQ_RANGE_RE.search(line)
        if seq_match:
            from_seq = int(seq_match.group(2))
            to_seq = int(seq_match.group(3))
            self._changes += to_seq - from_seq + 1
            self._applies += 1

        start_match = START_APPLYING_RE.search(line)
        if start_match:
            table_name = f"{start_match.group(3)}.{start_match.group(4)}"
            self._tables.add(table_name)

        if 'Bulk finished.' in line:
            if self._start_time and timestamp:
                duration = (timestamp - self._start_time).total_seconds()
                self.batches.append({
                    "line_number": line_num,
                    "start_timestamp": self._start_time,
                    "end_timestamp": timestamp,
                    "duration_seconds": duration,
                    "closure_reason": self._closure_reason or "Normal",
                    "changes_count": self._changes,
                    "applies_count": self._applies,
                    "tables": json.dumps(list(self._tables)) if self._tables else None,
                })
            self._start_time = None


class TableStatsExtractor:
    """Aggregates per-table apply statistics."""

    def __init__(self):
        self._stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "total_inserts": 0, "total_updates": 0, "total_deletes": 0,
            "total_merges": 0, "total_apply_time_seconds": 0.0,
            "apply_count": 0, "max_apply_time_seconds": 0.0,
            "one_by_one_count": 0, "has_pk": None, "error_count": 0,
        })
        self._apply_start_times: Dict[str, datetime] = {}

    def feed(self, line: str, line_num: int, timestamp: Optional[datetime], component: Optional[str]):
        if component != "TARGET_APPLY":
            return

        start_match = START_APPLYING_RE.search(line)
        if start_match and timestamp:
            table_name = f"{start_match.group(3)}.{start_match.group(4)}"
            self._apply_start_times[table_name] = timestamp
            op_type = start_match.group(1)
            count = int(start_match.group(2))
            if op_type == 'UNKNOWN':
                self._stats[table_name]["total_merges"] += count
            elif op_type == 'INSERT':
                self._stats[table_name]["total_inserts"] += count
            elif op_type == 'UPDATE':
                self._stats[table_name]["total_updates"] += count
            elif op_type == 'DELETE':
                self._stats[table_name]["total_deletes"] += count

        finish_match = FINISHED_APPLYING_RE.search(line)
        if finish_match and timestamp:
            table_name = f"{finish_match.group(3)}.{finish_match.group(4)}"
            if table_name in self._apply_start_times:
                duration = (timestamp - self._apply_start_times[table_name]).total_seconds()
                s = self._stats[table_name]
                s["total_apply_time_seconds"] += duration
                s["apply_count"] += 1
                if duration > s["max_apply_time_seconds"]:
                    s["max_apply_time_seconds"] = duration
                del self._apply_start_times[table_name]

        if 'one-by-one' in line.lower() and 'Applying' in line:
            table_name = extract_table_name(line)
            if table_name:
                self._stats[table_name]["one_by_one_count"] += 1

        if NO_PK_RE.search(line):
            table_name = extract_table_name(line)
            if table_name:
                self._stats[table_name]["has_pk"] = False

    @property
    def results(self) -> List[Dict[str, Any]]:
        out = []
        for name, s in self._stats.items():
            avg = s["total_apply_time_seconds"] / s["apply_count"] if s["apply_count"] else None
            out.append({
                "table_name": name,
                "total_inserts": s["total_inserts"],
                "total_updates": s["total_updates"],
                "total_deletes": s["total_deletes"],
                "total_merges": s["total_merges"],
                "total_apply_time_seconds": s["total_apply_time_seconds"],
                "avg_apply_time_seconds": avg,
                "max_apply_time_seconds": s["max_apply_time_seconds"],
                "one_by_one_count": s["one_by_one_count"],
                "has_pk": s["has_pk"],
                "error_count": s["error_count"],
            })
        return out


class TaskConfigExtractor:
    """Extracts task configuration values from log lines."""

    def __init__(self):
        self.config: Dict[str, Any] = {}

    def feed(self, line: str):
        if 'Set Bulk Timeout' in line and 'Min' not in line:
            m = BULK_TIMEOUT_RE.search(line)
            if m:
                self.config['bulk_timeout_ms'] = int(m.group(1))

        if 'Set Bulk Timeout Min' in line:
            m = BULK_TIMEOUT_MIN_RE.search(line)
            if m:
                self.config['bulk_timeout_min_ms'] = int(m.group(1))

        if 'Bulk max file size' in line:
            m = BULK_MAX_FILE_SIZE_RE.search(line)
            if m:
                self.config['bulk_max_file_size_kb'] = int(m.group(2))

        if 'Parallel bulk apply' in line:
            m = PARALLEL_APPLY_RE.search(line)
            if m:
                self.config['parallel_apply_threads'] = int(m.group(1))

        if 'Source endpoint' in line and 'provider' in line:
            m = SOURCE_ENDPOINT_RE.search(line)
            if m:
                self.config['source_type'] = m.group(1)

        if 'Target endpoint' in line and 'provider' in line:
            m = TARGET_ENDPOINT_RE.search(line)
            if m:
                self.config['target_type'] = m.group(1)

        if 'Going to execute MERGE' in line or 'Merge table statement MERGE' in line:
            self.config['merge_enabled'] = True
            self.config['apply_mode'] = 'merge'


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _duration_seconds(start: Optional[str], end: Optional[str]) -> Optional[float]:
    start_dt = _parse_ts(start)
    end_dt = _parse_ts(end)
    if start_dt and end_dt:
        return (end_dt - start_dt).total_seconds()
    return None


def _ts_str(timestamp: Optional[datetime]) -> Optional[str]:
    return timestamp.isoformat(timespec='seconds') if timestamp else None


class FullLoadExtractor:
    """Tracks full-load unload/load activity per table and segment.

    Consumes TASK_MANAGER / SOURCE_UNLOAD / TARGET_LOAD lines and produces
    a report-ready dict (summary + tables + segments + insights).
    """

    def __init__(self):
        # table_id -> table state
        self._tables: Dict[int, Dict[str, Any]] = {}
        # (table_id, attempt, segment_num) -> segment state
        self._segments: Dict[Tuple[int, int, int], Dict[str, Any]] = {}
        # thread_id -> subtask for pending WHERE assignment
        self._thread_subtask: Dict[str, int] = {}
        # table_id -> current attempt number (1-based)
        self._attempts: Dict[int, int] = {}
        self.full_load_completed: bool = False
        self.task_name: Optional[str] = None
        self.running_mode: Optional[str] = None
        self._first_ts: Optional[str] = None
        self._last_ts: Optional[str] = None
        self.reloads: List[Dict[str, Any]] = []

    def _ensure_table(
        self,
        table_id: int,
        schema: str,
        table: str,
        segmented: bool,
        timestamp: Optional[str],
        line_num: int,
        subtask: Optional[int] = None,
    ) -> Dict[str, Any]:
        if table_id not in self._tables:
            self._attempts[table_id] = 1
            self._tables[table_id] = {
                "table_id": table_id,
                "schema": schema,
                "table": table,
                "table_name": f"{schema}.{table}",
                "segmented": segmented,
                "status": "initializing",
                "attempt": 1,
                "attempts_total": 1,
                "segment_count": 0,
                "init_start": timestamp,
                "init_end": None,
                "load_start": None,
                "load_end": None,
                "rows_sent": 0,
                "rows_received": 0,
                "rows_skipped": 0,
                "volume_transferred": 0,
                "reload_count": 0,
                "errors": [],
                "init_line": line_num,
                "subtask": subtask,
            }
        else:
            t = self._tables[table_id]
            t["schema"] = schema or t["schema"]
            t["table"] = table or t["table"]
            t["table_name"] = f"{t['schema']}.{t['table']}"
            if segmented:
                t["segmented"] = True
            if t.get("init_start") is None and timestamp:
                t["init_start"] = timestamp
                t["init_line"] = line_num
        return self._tables[table_id]

    def _current_attempt(self, table_id: int) -> int:
        return self._attempts.get(table_id, 1)

    def _seg_key(self, table_id: int, segment_num: int) -> Tuple[int, int, int]:
        return (table_id, self._current_attempt(table_id), segment_num)

    def _ensure_segment(
        self,
        table_id: int,
        segment_num: int,
        segment_total: int,
        subtask: int,
        timestamp: Optional[str],
        line_num: int,
        schema: str = "",
        table: str = "",
    ) -> Dict[str, Any]:
        key = self._seg_key(table_id, segment_num)
        if key not in self._segments:
            self._segments[key] = {
                "table_id": table_id,
                "attempt": self._current_attempt(table_id),
                "segment_num": segment_num,
                "segment_total": segment_total,
                "subtask": subtask,
                "status": "loading",
                "start_time": timestamp,
                "unload_end": None,
                "load_end": None,
                "rows_sent": None,
                "rows_received": None,
                "rows_skipped": None,
                "volume_transferred": None,
                "records_transferred": None,
                "split_predicate": None,
                "unload_duration_seconds": None,
                "load_duration_seconds": None,
                "gap_unload_to_load_seconds": None,
                "total_duration_seconds": None,
                "start_line": line_num,
                "error": None,
            }
            t = self._tables.get(table_id)
            if t:
                t["segment_count"] = max(t.get("segment_count") or 0, segment_total)
                t["segmented"] = segment_total > 1 or t.get("segmented", False)
                if t.get("load_start") is None:
                    t["load_start"] = timestamp
                if t.get("status") in ("initializing", "reloading"):
                    t["status"] = "loading"
                if schema:
                    t["schema"] = schema
                    t["table"] = table
                    t["table_name"] = f"{schema}.{table}"
        else:
            seg = self._segments[key]
            if seg.get("start_time") is None and timestamp:
                seg["start_time"] = timestamp
                seg["start_line"] = line_num
            if segment_total:
                seg["segment_total"] = segment_total
        return self._segments[key]

    def _begin_reload(self, table_id: int, subtask: int, segment_num: int,
                      timestamp: Optional[str], line_num: int, message: str):
        t = self._tables.get(table_id)
        if not t:
            return
        attempt = self._current_attempt(table_id)
        # Mark unfinished segments of this attempt as error
        for key, seg in self._segments.items():
            if key[0] == table_id and key[1] == attempt and seg.get("status") == "loading":
                if seg["segment_num"] == segment_num:
                    seg["status"] = "error"
                    seg["error"] = message
                else:
                    # Other in-flight segments may still complete; leave as-is unless same failure
                    pass
        t["reload_count"] = t.get("reload_count", 0) + 1
        t["status"] = "reloading"
        t["errors"].append({
            "line": line_num,
            "timestamp": timestamp,
            "subtask": subtask,
            "segment": segment_num,
            "message": message,
        })
        self._attempts[table_id] = attempt + 1
        t["attempt"] = self._attempts[table_id]
        t["attempts_total"] = self._attempts[table_id]
        # Reset aggregate counters for new attempt (keep historical via segments)
        t["rows_sent"] = 0
        t["rows_received"] = 0
        t["rows_skipped"] = 0
        t["volume_transferred"] = 0
        t["load_start"] = None
        t["load_end"] = None
        self.reloads.append({
            "table_id": table_id,
            "table_name": t["table_name"],
            "subtask": subtask,
            "segment": segment_num,
            "timestamp": timestamp,
            "line": line_num,
            "message": message,
        })

    def _thread_id(self, line: str) -> Optional[str]:
        m = re.match(r'^(\d+):', line)
        return m.group(1) if m else None

    def feed(self, line: str, line_num: int, timestamp: Optional[datetime] = None,
             component: Optional[str] = None):
        ts = _ts_str(timestamp) if timestamp else None
        if ts is None:
            # Fall back to line parse when caller didn't supply a datetime
            extracted = extract_timestamp(line)
            ts = _ts_str(extracted)

        if ts:
            if self._first_ts is None:
                self._first_ts = ts
            self._last_ts = ts

        if component is None:
            cm = re.search(r'\[([A-Z_ ]+?)\]', line)
            component = cm.group(1).strip() if cm else None

        if FL_RUNNING_MODE_RE.search(line):
            m = FL_RUNNING_MODE_RE.search(line)
            self.task_name = m.group(1)
            self.running_mode = m.group(2).strip()

        if FL_COMPLETED_RE.search(line):
            self.full_load_completed = True

        # Track UNLOAD_TABLE_SEGMENT thread -> subtask for WHERE assignment
        cmd = FL_UNLOAD_CMD_RE.search(line)
        if cmd:
            tid = self._thread_id(line)
            if tid:
                self._thread_subtask[tid] = int(cmd.group(1))

        where = FL_SEGMENT_WHERE_RE.search(line)
        if where and component == "SOURCE_UNLOAD":
            tid = self._thread_id(line)
            subtask = self._thread_subtask.get(tid) if tid else None
            predicate = where.group(1).strip()
            if subtask is not None:
                # Attach to newest open segment with this subtask that lacks a predicate
                candidates = [
                    seg for seg in self._segments.values()
                    if seg.get("subtask") == subtask and not seg.get("split_predicate")
                ]
                if candidates:
                    # Prefer most recent start
                    candidates.sort(key=lambda s: (s.get("start_line") or 0), reverse=True)
                    candidates[0]["split_predicate"] = predicate

        init = FL_INIT_SEGMENTED_RE.search(line) or FL_INIT_TABLE_RE.search(line)
        if init:
            schema, table, table_id, subtask = init.group(1), init.group(2), int(init.group(3)), int(init.group(4))
            segmented = "segmented table" in line.lower()
            self._ensure_table(table_id, schema, table, segmented, ts, line_num, subtask)
            return

        prep = FL_TARGET_PREP_RE.search(line)
        if prep:
            schema, table, table_id = prep.group(1), prep.group(2), int(prep.group(3))
            t = self._ensure_table(table_id, schema, table, "segmented" in line.lower(), ts, line_num)
            t["init_end"] = ts
            return

        start_seg = FL_START_SEGMENT_RE.search(line)
        if start_seg:
            seg_num = int(start_seg.group(1))
            seg_total = int(start_seg.group(2))
            schema, table = start_seg.group(3), start_seg.group(4)
            table_id = int(start_seg.group(5))
            subtask = int(start_seg.group(6))
            self._ensure_table(table_id, schema, table, True, ts, line_num, subtask)
            self._ensure_segment(table_id, seg_num, seg_total, subtask, ts, line_num, schema, table)
            return

        start_tbl = FL_START_TABLE_RE.search(line)
        if start_tbl:
            schema, table = start_tbl.group(1), start_tbl.group(2)
            table_id = int(start_tbl.group(3))
            subtask = int(start_tbl.group(4))
            self._ensure_table(table_id, schema, table, False, ts, line_num, subtask)
            self._ensure_segment(table_id, 1, 1, subtask, ts, line_num, schema, table)
            return

        unload_seg = FL_UNLOAD_SEGMENT_DONE_RE.search(line)
        if unload_seg:
            seg_num = int(unload_seg.group(1))
            schema, table = unload_seg.group(2), unload_seg.group(3)
            table_id = int(unload_seg.group(4))
            rows = int(unload_seg.group(5))
            self._ensure_table(table_id, schema, table, True, ts, line_num)
            # Find segment in current or latest attempt
            seg = self._find_segment(table_id, seg_num)
            if seg is None:
                seg = self._ensure_segment(table_id, seg_num, 0, 0, None, line_num, schema, table)
            seg["unload_end"] = ts
            seg["rows_sent"] = rows
            seg["unload_duration_seconds"] = _duration_seconds(seg.get("start_time"), ts)
            t = self._tables[table_id]
            if seg.get("attempt") == self._current_attempt(table_id):
                t["rows_sent"] = (t.get("rows_sent") or 0) + rows
            return

        unload_tbl = FL_UNLOAD_TABLE_DONE_RE.search(line)
        if unload_tbl:
            schema, table = unload_tbl.group(1), unload_tbl.group(2)
            table_id = int(unload_tbl.group(3))
            rows = int(unload_tbl.group(4))
            self._ensure_table(table_id, schema, table, False, ts, line_num)
            seg = self._find_segment(table_id, 1)
            if seg is None:
                seg = self._ensure_segment(table_id, 1, 1, 0, None, line_num, schema, table)
            seg["unload_end"] = ts
            seg["rows_sent"] = rows
            seg["unload_duration_seconds"] = _duration_seconds(seg.get("start_time"), ts)
            t = self._tables[table_id]
            if seg.get("attempt") == self._current_attempt(table_id):
                t["rows_sent"] = (t.get("rows_sent") or 0) + rows
            return

        load_seg = FL_LOAD_SEGMENT_DONE_RE.search(line)
        if load_seg:
            seg_num = int(load_seg.group(1))
            schema, table = load_seg.group(2), load_seg.group(3)
            table_id = int(load_seg.group(4))
            rows_recv = int(load_seg.group(5))
            rows_skip = int(load_seg.group(6))
            volume = int(load_seg.group(7))
            self._ensure_table(table_id, schema, table, True, ts, line_num)
            seg = self._find_segment(table_id, seg_num)
            if seg is None:
                seg = self._ensure_segment(table_id, seg_num, 0, 0, None, line_num, schema, table)
            seg["load_end"] = ts
            seg["rows_received"] = rows_recv
            seg["rows_skipped"] = rows_skip
            seg["volume_transferred"] = volume
            if seg.get("unload_end"):
                seg["gap_unload_to_load_seconds"] = _duration_seconds(seg["unload_end"], ts)
                # Load duration approximated as gap when we lack a separate load-start
                seg["load_duration_seconds"] = seg["gap_unload_to_load_seconds"]
            seg["total_duration_seconds"] = _duration_seconds(seg.get("start_time"), ts)
            if seg.get("status") != "error":
                seg["status"] = "complete"
            t = self._tables[table_id]
            if seg.get("attempt") == self._current_attempt(table_id):
                t["rows_received"] = (t.get("rows_received") or 0) + rows_recv
                t["rows_skipped"] = (t.get("rows_skipped") or 0) + rows_skip
                t["volume_transferred"] = (t.get("volume_transferred") or 0) + volume
            return

        load_tbl = FL_LOAD_TABLE_DONE_RE.search(line)
        if load_tbl:
            schema, table = load_tbl.group(1), load_tbl.group(2)
            table_id = int(load_tbl.group(3))
            rows_recv = int(load_tbl.group(4))
            rows_skip = int(load_tbl.group(5))
            volume = int(load_tbl.group(6))
            self._ensure_table(table_id, schema, table, False, ts, line_num)
            seg = self._find_segment(table_id, 1)
            if seg is None:
                seg = self._ensure_segment(table_id, 1, 1, 0, None, line_num, schema, table)
            seg["load_end"] = ts
            seg["rows_received"] = rows_recv
            seg["rows_skipped"] = rows_skip
            seg["volume_transferred"] = volume
            if seg.get("unload_end"):
                seg["gap_unload_to_load_seconds"] = _duration_seconds(seg["unload_end"], ts)
                seg["load_duration_seconds"] = seg["gap_unload_to_load_seconds"]
            seg["total_duration_seconds"] = _duration_seconds(seg.get("start_time"), ts)
            if seg.get("status") != "error":
                seg["status"] = "complete"
            t = self._tables[table_id]
            if seg.get("attempt") == self._current_attempt(table_id):
                t["rows_received"] = (t.get("rows_received") or 0) + rows_recv
                t["rows_skipped"] = (t.get("rows_skipped") or 0) + rows_skip
                t["volume_transferred"] = (t.get("volume_transferred") or 0) + volume
            return

        tm_seg = FL_TM_SEGMENT_DONE_RE.search(line)
        if tm_seg:
            seg_num = int(tm_seg.group(1))
            schema, table = tm_seg.group(2), tm_seg.group(3)
            table_id = int(tm_seg.group(4))
            subtask = int(tm_seg.group(5))
            records = int(tm_seg.group(6))
            self._ensure_table(table_id, schema, table, True, ts, line_num)
            seg = self._find_segment(table_id, seg_num)
            if seg is None:
                seg = self._ensure_segment(table_id, seg_num, 0, subtask, None, line_num, schema, table)
            seg["records_transferred"] = records
            seg["subtask"] = subtask or seg.get("subtask")
            if seg.get("load_end") is None:
                seg["load_end"] = ts
            if seg.get("status") != "error":
                seg["status"] = "complete"
            if seg.get("total_duration_seconds") is None:
                seg["total_duration_seconds"] = _duration_seconds(seg.get("start_time"), ts)
            self._refresh_table_status(table_id)
            return

        tm_tbl = FL_TM_TABLE_DONE_RE.search(line)
        if tm_tbl:
            schema, table = tm_tbl.group(1), tm_tbl.group(2)
            table_id = int(tm_tbl.group(3))
            subtask = int(tm_tbl.group(4))
            records = int(tm_tbl.group(5))
            self._ensure_table(table_id, schema, table, False, ts, line_num)
            seg = self._find_segment(table_id, 1)
            if seg is None:
                seg = self._ensure_segment(table_id, 1, 1, subtask, None, line_num, schema, table)
            seg["records_transferred"] = records
            if seg.get("load_end") is None:
                seg["load_end"] = ts
            if seg.get("status") != "error":
                seg["status"] = "complete"
            t = self._tables[table_id]
            t["status"] = "complete"
            t["load_end"] = ts
            return

        reload_m = FL_RELOAD_RE.search(line)
        if reload_m:
            table_id = int(reload_m.group(1))
            subtask = int(reload_m.group(2))
            segment_num = int(reload_m.group(3))
            msg = line.split(']I:', 1)[-1].split(']E:', 1)[-1].strip() if ']' in line else line.strip()
            msg = re.sub(r'\s+\([^)]+\)\s*$', '', msg)
            self._begin_reload(table_id, subtask, segment_num, ts, line_num, msg)
            return

    def _find_segment(self, table_id: int, segment_num: int) -> Optional[Dict[str, Any]]:
        """Prefer current attempt, else most recent prior attempt for this segment."""
        attempt = self._current_attempt(table_id)
        key = (table_id, attempt, segment_num)
        if key in self._segments:
            return self._segments[key]
        # Fall back: highest attempt <= current that has this segment
        candidates = [
            (k, v) for k, v in self._segments.items()
            if k[0] == table_id and k[2] == segment_num
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0][1], reverse=True)
        return candidates[0][1]

    def _refresh_table_status(self, table_id: int):
        t = self._tables.get(table_id)
        if not t:
            return
        attempt = self._current_attempt(table_id)
        segs = [s for k, s in self._segments.items() if k[0] == table_id and k[1] == attempt]
        if not segs:
            return
        expected = t.get("segment_count") or len(segs)
        complete = [s for s in segs if s.get("status") == "complete"]
        errors = [s for s in segs if s.get("status") == "error"]
        loading = [s for s in segs if s.get("status") == "loading"]
        if errors and not loading:
            t["status"] = "error"
        elif len(complete) >= expected and expected > 0 and not loading:
            t["status"] = "complete"
            ends = [s.get("load_end") for s in complete if s.get("load_end")]
            if ends:
                t["load_end"] = max(ends)
        elif loading or complete:
            t["status"] = "loading"

    def build_report(self) -> Dict[str, Any]:
        for table_id in list(self._tables.keys()):
            self._refresh_table_status(table_id)

        tables_out = []
        for table_id, t in sorted(self._tables.items(), key=lambda x: x[0]):
            attempt = self._current_attempt(table_id)
            segs = [
                s for k, s in self._segments.items()
                if k[0] == table_id and k[1] == attempt
            ]
            segs_sorted = sorted(segs, key=lambda s: s.get("segment_num") or 0)
            # Also include prior-attempt segments for history
            prior = [
                s for k, s in self._segments.items()
                if k[0] == table_id and k[1] != attempt
            ]
            prior_sorted = sorted(prior, key=lambda s: (s.get("attempt") or 0, s.get("segment_num") or 0))

            unload_durs = [s.get("unload_duration_seconds") for s in segs_sorted if s.get("unload_duration_seconds") is not None]
            gaps = [s.get("gap_unload_to_load_seconds") for s in segs_sorted if s.get("gap_unload_to_load_seconds") is not None]
            total_durs = [s.get("total_duration_seconds") for s in segs_sorted if s.get("total_duration_seconds") is not None]

            tables_out.append({
                **t,
                "unload_duration_seconds": sum(unload_durs) if unload_durs else None,
                "max_segment_duration_seconds": max(total_durs) if total_durs else None,
                "max_unload_to_load_gap_seconds": max(gaps) if gaps else None,
                "segments_complete": sum(1 for s in segs_sorted if s.get("status") == "complete"),
                "segments_loading": sum(1 for s in segs_sorted if s.get("status") == "loading"),
                "segments_error": sum(1 for s in segs_sorted if s.get("status") == "error"),
                "segments": segs_sorted,
                "prior_attempt_segments": prior_sorted,
                "duration_seconds": _duration_seconds(t.get("init_start") or t.get("load_start"), t.get("load_end") or self._last_ts),
            })

        loaded = sum(1 for t in tables_out if t["status"] == "complete")
        loading = sum(1 for t in tables_out if t["status"] in ("loading", "initializing", "reloading"))
        failed = sum(1 for t in tables_out if t["status"] == "error")
        total_rows = sum(t.get("rows_received") or 0 for t in tables_out)
        total_volume = sum(t.get("volume_transferred") or 0 for t in tables_out)
        max_parallel = 0
        for t in tables_out:
            max_parallel = max(max_parallel, t.get("segment_count") or 0)

        summary = {
            "full_load_completed": self.full_load_completed,
            "task_name": self.task_name,
            "running_mode": self.running_mode,
            "tables_total": len(tables_out),
            "tables_loaded": loaded,
            "tables_loading": loading,
            "tables_failed": failed,
            "tables_reloaded": sum(1 for t in tables_out if (t.get("reload_count") or 0) > 0),
            "total_rows_received": total_rows,
            "total_rows_sent": sum(t.get("rows_sent") or 0 for t in tables_out),
            "total_volume_transferred": total_volume,
            "max_parallel_segments": max_parallel,
            "reload_events": len(self.reloads),
            "start_time": self._first_ts,
            "end_time": self._last_ts,
            "duration_seconds": _duration_seconds(self._first_ts, self._last_ts),
        }

        insights = self._build_insights(tables_out, summary)

        return {
            "summary": summary,
            "tables": tables_out,
            "reloads": self.reloads,
            "insights": insights,
        }

    def _build_insights(self, tables: List[Dict[str, Any]], summary: Dict[str, Any]) -> List[Dict[str, Any]]:
        insights: List[Dict[str, Any]] = []

        if summary.get("reload_events", 0) > 0:
            insights.append({
                "type": "reload_loop",
                "severity": "error",
                "title": "Full load reload loops",
                "message": (
                    f"{summary['reload_events']} reload event(s) across "
                    f"{summary.get('tables_reloaded', 0)} table(s). "
                    "A segment failed after partial target load, forcing a full table reload."
                ),
                "recommendation": "Check SOURCE_UNLOAD errors on the failing subtask/segment; reduce segment size or fix source connectivity/timeouts.",
            })

        slow_segs = []
        for t in tables:
            for s in t.get("segments") or []:
                dur = s.get("total_duration_seconds")
                if dur is not None and dur >= 3600:
                    slow_segs.append((dur, t["table_name"], s))
        slow_segs.sort(reverse=True)
        for dur, tname, s in slow_segs[:5]:
            hours = dur / 3600.0
            insights.append({
                "type": "slow_segment",
                "severity": "warning",
                "title": f"Slow segment on {tname}",
                "message": (
                    f"Segment #{s.get('segment_num')} took {hours:.1f}h "
                    f"({(s.get('rows_received') or 0):,} rows)."
                ),
                "recommendation": "Review segment split balance and source unload parallelism; skewed ranges cause long-tail segments.",
            })

        big_gaps = []
        for t in tables:
            for s in t.get("segments") or []:
                gap = s.get("gap_unload_to_load_seconds")
                if gap is not None and gap >= 30:
                    big_gaps.append((gap, t["table_name"], s))
        big_gaps.sort(reverse=True)
        for gap, tname, s in big_gaps[:3]:
            insights.append({
                "type": "unload_load_gap",
                "severity": "warning",
                "title": f"Unload→load gap on {tname}",
                "message": f"Segment #{s.get('segment_num')} waited {gap:.0f}s between unload finish and load finish.",
                "recommendation": "Check TARGET_LOAD throughput, BCP/bulk insert performance, and target contention.",
            })

        mismatches = []
        for t in tables:
            for s in t.get("segments") or []:
                sent, recv = s.get("rows_sent"), s.get("rows_received")
                if sent is not None and recv is not None and sent != recv:
                    mismatches.append((t["table_name"], s, sent, recv))
        for tname, s, sent, recv in mismatches[:5]:
            insights.append({
                "type": "row_mismatch",
                "severity": "error",
                "title": f"Row count mismatch on {tname}",
                "message": f"Segment #{s.get('segment_num')}: {sent:,} unloaded vs {recv:,} loaded.",
                "recommendation": "Investigate TARGET_LOAD errors/skips for this segment.",
            })

        if summary.get("tables_loading", 0) > 0 and not summary.get("full_load_completed"):
            insights.append({
                "type": "in_progress",
                "severity": "info",
                "title": "Full load still in progress",
                "message": f"{summary['tables_loading']} table(s) still loading; full load completion message not seen.",
                "recommendation": None,
            })

        return insights


_FL_COMPONENT_HINTS = (
    "TASK_MANAGER", "SOURCE_UNLOAD", "TARGET_LOAD", "TABLES_MANAGER", "SORTER",
)
_FL_KEYWORD_HINTS = (
    "initializing", "Start loading", "Unload finished", "Load finished",
    "Reloading table", "Transformation Where", "UNLOAD_TABLE_SEGMENT",
    "Full load", "Full Load", "running full load", "target preparation",
    "Initialization finished",
)


def analyze_full_load_file(file_path: str, max_lines: int = 500000) -> Dict[str, Any]:
    """Scan a reptask log and return the FullLoadExtractor report dict.

    Adds ``available`` so callers can decide whether FL context is present.
    """
    from backend.core.patterns import LINE_FULL_RE

    extractor = FullLoadExtractor()
    with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
        for line_num, line in enumerate(fh, start=1):
            if line_num > max_lines:
                break
            if not any(c in line for c in _FL_COMPONENT_HINTS):
                continue
            if not any(k in line for k in _FL_KEYWORD_HINTS):
                continue
            timestamp = extract_timestamp(line)
            component = None
            m = LINE_FULL_RE.match(line)
            if m:
                component = (m.group(3) or "").strip()
            else:
                cm = re.search(r'\[([A-Z_ ]+?)\]', line)
                component = cm.group(1).strip() if cm else None
            extractor.feed(line, line_num, timestamp, component)

    report = extractor.build_report()
    available = bool(
        report["summary"].get("tables_total", 0) > 0
        or report["summary"].get("full_load_completed")
    )
    report["available"] = available
    if not available:
        report["message"] = "No full load table/segment activity detected in this log"
    return report


def condense_full_load_for_llm(report: Dict[str, Any], max_tables: int = 15) -> Optional[Dict[str, Any]]:
    """Shrink a full-load report for AI Insights prompt / embedding context."""
    if not report or not report.get("available"):
        return None

    summary = report.get("summary") or {}
    tables_out: List[Dict[str, Any]] = []
    for t in (report.get("tables") or [])[:max_tables]:
        segs = []
        for s in (t.get("segments") or []):
            segs.append({
                "segment_num": s.get("segment_num"),
                "segment_total": s.get("segment_total"),
                "subtask": s.get("subtask"),
                "status": s.get("status"),
                "rows_sent": s.get("rows_sent"),
                "rows_received": s.get("rows_received"),
                "rows_skipped": s.get("rows_skipped"),
                "volume_transferred": s.get("volume_transferred"),
                "unload_duration_seconds": s.get("unload_duration_seconds"),
                "gap_unload_to_load_seconds": s.get("gap_unload_to_load_seconds"),
                "total_duration_seconds": s.get("total_duration_seconds"),
                "split_predicate": s.get("split_predicate"),
                "error": s.get("error"),
            })
        tables_out.append({
            "table_name": t.get("table_name"),
            "table_id": t.get("table_id"),
            "status": t.get("status"),
            "segmented": t.get("segmented"),
            "segment_count": t.get("segment_count"),
            "segments_complete": t.get("segments_complete"),
            "segments_loading": t.get("segments_loading"),
            "segments_error": t.get("segments_error"),
            "rows_sent": t.get("rows_sent"),
            "rows_received": t.get("rows_received"),
            "rows_skipped": t.get("rows_skipped"),
            "volume_transferred": t.get("volume_transferred"),
            "unload_duration_seconds": t.get("unload_duration_seconds"),
            "max_segment_duration_seconds": t.get("max_segment_duration_seconds"),
            "max_unload_to_load_gap_seconds": t.get("max_unload_to_load_gap_seconds"),
            "duration_seconds": t.get("duration_seconds"),
            "reload_count": t.get("reload_count"),
            "attempts_total": t.get("attempts_total"),
            "segments": segs,
        })

    insights = []
    for ins in (report.get("insights") or [])[:8]:
        insights.append({
            "type": ins.get("type"),
            "severity": ins.get("severity"),
            "title": ins.get("title"),
            "message": ins.get("message"),
            "recommendation": ins.get("recommendation"),
        })

    reloads = []
    for r in (report.get("reloads") or [])[:10]:
        reloads.append({
            "table_name": r.get("table_name"),
            "table_id": r.get("table_id"),
            "segment": r.get("segment"),
            "subtask": r.get("subtask"),
            "timestamp": r.get("timestamp"),
            "message": r.get("message"),
        })

    return {
        "available": True,
        "summary": {
            "full_load_completed": summary.get("full_load_completed"),
            "task_name": summary.get("task_name"),
            "running_mode": summary.get("running_mode"),
            "tables_total": summary.get("tables_total"),
            "tables_loaded": summary.get("tables_loaded"),
            "tables_loading": summary.get("tables_loading"),
            "tables_failed": summary.get("tables_failed"),
            "tables_reloaded": summary.get("tables_reloaded"),
            "total_rows_sent": summary.get("total_rows_sent"),
            "total_rows_received": summary.get("total_rows_received"),
            "total_volume_transferred": summary.get("total_volume_transferred"),
            "max_parallel_segments": summary.get("max_parallel_segments"),
            "reload_events": summary.get("reload_events"),
            "start_time": summary.get("start_time"),
            "end_time": summary.get("end_time"),
            "duration_seconds": summary.get("duration_seconds"),
        },
        "tables": tables_out,
        "reloads": reloads,
        "insights": insights,
    }
