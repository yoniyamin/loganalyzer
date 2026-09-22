import os
import re
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from backend.database import (
    LogFile, LogIndex, LogPerformance, LogOracleRedoRead, LogOracleRedoLogSession,
    LogStats, LogError, LogBatch, LogTableStats, LogTaskConfig, FileVersion, LogLineMeta,
    SCHEMA_VERSION,
)
from collections import defaultdict, Counter
from backend.core.patterns import (
    LINE_FULL_RE, LINE_START_RE, ERR_RE, ASM_PREPARE_READ_RE,
    parse_oracle_archived_redo_read, parse_oracle_redo_log_open, parse_oracle_redo_log_close,
)
from backend.core.reader import clear_file_cache
from backend.core.error_codes import extract_error_code
from backend.core.extractors import BatchExtractor, TableStatsExtractor, TaskConfigExtractor

logger = logging.getLogger(__name__)

BATCH_SIZE = 5000
INDEX_INTERVAL = 500
FTS_BATCH_SIZE = 2000

# Severity letter from the bracket pattern ']X:'
_SEVERITY_RE = re.compile(r'\]([EWITD]):')


def _detect_severity(line: str, component: str = None) -> str | None:
    """Return single-char severity (E/W/I/T/D) or None."""
    m = _SEVERITY_RE.search(line)
    if m:
        return m.group(1)
    return None


def _is_new_log_line(line: str) -> bool:
    """True if the line starts a new log entry (has thread:timestamp prefix)."""
    return bool(LINE_FULL_RE.match(line) or LINE_START_RE.match(line))


def process_log_file(db: Session, file_id: int):
    """
    Reads the log file, builds index + FTS + line_meta, extracts errors/batches/stats/config,
    and updates the file status to 'ready' upon completion.
    """
    log_file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not log_file:
        logger.error(f"File ID {file_id} not found.")
        return

    clear_file_cache(file_id)

    try:
        file_path = log_file.file_path
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at {file_path}")

        logger.info(f"Starting indexing for {log_file.filename}...")

        # Delete existing derived data for this file (oracle tables cleared here too)
        db.query(LogOracleRedoRead).filter(LogOracleRedoRead.file_id == file_id).delete(synchronize_session=False)
        db.query(LogOracleRedoLogSession).filter(LogOracleRedoLogSession.file_id == file_id).delete(synchronize_session=False)
        db.query(LogBatch).filter(LogBatch.file_id == file_id).delete(synchronize_session=False)
        db.query(LogTableStats).filter(LogTableStats.file_id == file_id).delete(synchronize_session=False)
        db.query(LogTaskConfig).filter(LogTaskConfig.file_id == file_id).delete(synchronize_session=False)
        db.query(LogLineMeta).filter(LogLineMeta.file_id == file_id).delete(synchronize_session=False)
        db.commit()

        # FTS: use SQLAlchemy's execute for virtual table ops (shares transaction)
        from sqlalchemy import text as sa_text
        db.execute(sa_text("DELETE FROM log_lines_fts WHERE file_id = :fid"), {"fid": file_id})
        db.commit()

        # Extractors
        batch_extractor = BatchExtractor()
        table_stats_extractor = TableStatsExtractor()
        config_extractor = TaskConfigExtractor()

        # Batch inserts
        perf_batch = []
        redo_batch = []
        session_batch = []
        error_batch = []
        index_batch = []
        meta_batch = []
        fts_batch = []
        pending_redo_log_opens = {}

        # Aggregation
        stats_map = {}
        asm_thread_stmts = defaultdict(Counter)

        # Tracking state
        line_count = 0
        last_thread = None
        last_component = None
        last_ts = None
        last_error_line = -10  # For continuation dedup

        # Open in binary mode to get accurate byte offsets, decode manually
        with open(file_path, "rb") as f:
            while True:
                current_offset = f.tell()
                raw_line = f.readline()
                if not raw_line:
                    break

                line = raw_line.decode("utf-8", errors="replace")

                if not line.strip():
                    line_count += 1
                    continue

                # Parse Line
                m = LINE_FULL_RE.match(line)
                timestamp = None
                thread_id = None
                component = None
                is_continuation = False

                if m:
                    thread_id = m.group(1)
                    ts_str = m.group(2)
                    component = m.group(3).strip()
                    timestamp = datetime.fromisoformat(ts_str)
                    last_thread = thread_id
                    last_component = component
                    last_ts = timestamp
                else:
                    if LINE_START_RE.match(line):
                        ts_m = re.match(r'^\s*\d+:\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', line)
                        if ts_m:
                            timestamp = datetime.fromisoformat(ts_m.group(1))
                            last_ts = timestamp
                        thread_match = re.match(r'^\s*(\d+):', line)
                        if thread_match:
                            thread_id = thread_match.group(1)
                            last_thread = thread_id
                        component = "UNKNOWN"
                        last_component = component
                    else:
                        # Continuation line
                        is_continuation = True
                        thread_id = last_thread
                        component = last_component
                        timestamp = last_ts

                severity = _detect_severity(line, component)

                # 1. Sparse index
                if line_count % INDEX_INTERVAL == 0:
                    index_batch.append(LogIndex(
                        file_id=file_id,
                        line_number=line_count,
                        byte_offset=current_offset,
                        timestamp=timestamp
                    ))

                # 2. Dense line_meta
                meta_batch.append(LogLineMeta(
                    file_id=file_id,
                    line_number=line_count,
                    byte_offset=current_offset,
                    timestamp=timestamp,
                    component=component,
                    thread_id=thread_id,
                    severity=severity,
                ))

                # 3. FTS (contentless) — index all lines for keyword search
                fts_batch.append((line.rstrip('\n\r'), file_id, line_count))

                # 4. Performance
                if component == "PERFORMANCE" and timestamp:
                    lat_m = re.search(
                        r'Source latency ([0-9.]+) seconds,\s*Target latency ([0-9.]+) seconds,\s*Handling latency ([0-9.]+) seconds',
                        line
                    )
                    if lat_m:
                        perf_batch.append(LogPerformance(
                            file_id=file_id,
                            line_number=line_count,
                            timestamp=timestamp,
                            source_latency=float(lat_m.group(1)),
                            target_latency=float(lat_m.group(2)),
                            handling_latency=float(lat_m.group(3))
                        ))
                    else:
                        parsed = parse_oracle_archived_redo_read(line)
                        if parsed and parsed["read_ms"] > 200.0:
                            redo_batch.append(LogOracleRedoRead(
                                file_id=file_id,
                                line_number=line_count,
                                timestamp=timestamp,
                                thread_id=thread_id,
                                bytes_read=parsed["bytes_read"],
                                read_ms=parsed["read_ms"],
                                source_location=parsed.get("source_location"),
                            ))

                if component == "SOURCE_CAPTURE" and timestamp:
                    o = parse_oracle_redo_log_open(line)
                    if o:
                        tid = o.get("thread_id_in_message") or thread_id or None
                        pending_redo_log_opens[o["redo_path"]] = {
                            "line_number": line_count,
                            "timestamp": timestamp,
                            "thread_id": tid,
                        }
                    cpath = parse_oracle_redo_log_close(line)
                    if cpath and timestamp:
                        if cpath in pending_redo_log_opens:
                            open_info = pending_redo_log_opens.pop(cpath)
                            t0 = open_info["timestamp"]
                            t1 = timestamp
                            tid_s = open_info.get("thread_id") or thread_id
                            if t0 and t1:
                                dur = (t1 - t0).total_seconds()
                                if dur >= 0:
                                    session_batch.append(LogOracleRedoLogSession(
                                        file_id=file_id,
                                        thread_id=str(tid_s) if tid_s not in (None, "") else None,
                                        redo_path=cpath,
                                        line_open=open_info["line_number"],
                                        line_close=line_count,
                                        timestamp_open=t0,
                                        timestamp_close=t1,
                                        duration_seconds=dur,
                                    ))

                # ASM worker tracking
                if component == "SOURCE_CAPTURE" and thread_id:
                    asm_m = ASM_PREPARE_READ_RE.search(line)
                    if asm_m:
                        asm_thread_stmts[thread_id][asm_m.group(1)] += 1

                # 5. Stats aggregation
                if thread_id and component:
                    key = (component, thread_id)
                    if key not in stats_map:
                        stats_map[key] = {"count": 0, "first_ts": timestamp, "last_ts": timestamp}
                    stats = stats_map[key]
                    stats["count"] += 1
                    if timestamp:
                        stats["last_ts"] = timestamp
                        if not stats["first_ts"]:
                            stats["first_ts"] = timestamp

                # 6. Errors — only match on full log lines, skip continuations to dedup
                if not is_continuation and ERR_RE.search(line):
                    error_code = extract_error_code(line)
                    error_batch.append(LogError(
                        file_id=file_id,
                        line_number=line_count,
                        timestamp=timestamp,
                        component=component,
                        thread_id=thread_id,
                        text=line.rstrip('\n\r'),
                        error_code=error_code,
                    ))
                    last_error_line = line_count

                # 7. Batch/table/config extractors
                batch_extractor.feed(line, line_count, timestamp, component)
                table_stats_extractor.feed(line, line_count, timestamp, component)
                config_extractor.feed(line)

                line_count += 1

                # Periodic commit
                if line_count % BATCH_SIZE == 0:
                    db.bulk_save_objects(index_batch)
                    db.bulk_save_objects(perf_batch)
                    db.bulk_save_objects(redo_batch)
                    db.bulk_save_objects(session_batch)
                    db.bulk_save_objects(error_batch)
                    db.bulk_save_objects(meta_batch)
                    db.commit()

                    index_batch = []
                    perf_batch = []
                    redo_batch = []
                    session_batch = []
                    error_batch = []
                    meta_batch = []

                # FTS periodic flush
                if len(fts_batch) >= FTS_BATCH_SIZE:
                    db.execute(
                        sa_text("INSERT INTO log_lines_fts(body, file_id, line_number) VALUES (:b, :f, :l)"),
                        [{"b": b, "f": f, "l": l} for b, f, l in fts_batch]
                    )
                    fts_batch = []

        # Final flush
        if index_batch:
            db.bulk_save_objects(index_batch)
        if perf_batch:
            db.bulk_save_objects(perf_batch)
        if redo_batch:
            db.bulk_save_objects(redo_batch)
        if session_batch:
            db.bulk_save_objects(session_batch)
        if error_batch:
            db.bulk_save_objects(error_batch)
        if meta_batch:
            db.bulk_save_objects(meta_batch)

        if fts_batch:
            db.execute(
                sa_text("INSERT INTO log_lines_fts(body, file_id, line_number) VALUES (:b, :f, :l)"),
                [{"b": b, "f": f, "l": l} for b, f, l in fts_batch]
            )

        # ASM merge
        asm_only_threads = set()
        for tid, stmt_counts in asm_thread_stmts.items():
            total_asm = sum(stmt_counts.values())
            sc_key = ("SOURCE_CAPTURE", tid)
            if sc_key in stats_map and stats_map[sc_key]["count"] == total_asm:
                asm_only_threads.add(tid)

        if asm_only_threads:
            asm_groups = defaultdict(lambda: {
                "count": 0, "first_ts": None, "last_ts": None, "pool_tids": set()
            })
            for tid in asm_only_threads:
                sc_key = ("SOURCE_CAPTURE", tid)
                removed = stats_map.pop(sc_key)
                for stmt_num, count in asm_thread_stmts[tid].items():
                    g = asm_groups[stmt_num]
                    g["count"] += count
                    g["pool_tids"].add(tid)
                    if removed["first_ts"]:
                        if not g["first_ts"] or removed["first_ts"] < g["first_ts"]:
                            g["first_ts"] = removed["first_ts"]
                    if removed["last_ts"]:
                        if not g["last_ts"] or removed["last_ts"] > g["last_ts"]:
                            g["last_ts"] = removed["last_ts"]

            for stmt_num, g in sorted(asm_groups.items(), key=lambda x: int(x[0])):
                pool_count = len(g["pool_tids"])
                virtual_tid = f"__asm:{stmt_num}:{pool_count}"
                stats_map[("SOURCE_CAPTURE", virtual_tid)] = {
                    "count": g["count"],
                    "first_ts": g["first_ts"],
                    "last_ts": g["last_ts"],
                }
            logger.info(
                f"Merged {len(asm_only_threads)} ASM worker threads into "
                f"{len(asm_groups)} virtual groups"
            )

        # Save stats
        stats_objects = []
        for (comp, tid), data in stats_map.items():
            stats_objects.append(LogStats(
                file_id=file_id,
                component=comp,
                thread_id=tid,
                message_count=data["count"],
                first_ts=data["first_ts"],
                last_ts=data["last_ts"]
            ))
        db.bulk_save_objects(stats_objects)

        # Save batches
        for b in batch_extractor.batches:
            db.add(LogBatch(
                file_id=file_id,
                line_number=b["line_number"],
                start_timestamp=b["start_timestamp"],
                end_timestamp=b["end_timestamp"],
                duration_seconds=b["duration_seconds"],
                closure_reason=b["closure_reason"],
                changes_count=b["changes_count"],
                applies_count=b["applies_count"],
                tables=b["tables"],
            ))

        # Save table stats
        for ts in table_stats_extractor.results:
            db.add(LogTableStats(
                file_id=file_id,
                table_name=ts["table_name"],
                total_inserts=ts["total_inserts"],
                total_updates=ts["total_updates"],
                total_deletes=ts["total_deletes"],
                total_merges=ts["total_merges"],
                total_apply_time_seconds=ts["total_apply_time_seconds"],
                avg_apply_time_seconds=ts["avg_apply_time_seconds"],
                max_apply_time_seconds=ts["max_apply_time_seconds"],
                one_by_one_count=ts["one_by_one_count"],
                has_pk=ts["has_pk"],
                error_count=ts["error_count"],
            ))

        # Save task config
        cfg = config_extractor.config
        if cfg:
            db.add(LogTaskConfig(
                file_id=file_id,
                bulk_timeout_ms=cfg.get('bulk_timeout_ms'),
                bulk_timeout_min_ms=cfg.get('bulk_timeout_min_ms'),
                bulk_max_file_size_kb=cfg.get('bulk_max_file_size_kb'),
                parallel_apply_threads=cfg.get('parallel_apply_threads'),
                source_type=cfg.get('source_type'),
                target_type=cfg.get('target_type'),
                apply_mode=cfg.get('apply_mode'),
                merge_enabled=cfg.get('merge_enabled'),
            ))

        # FileVersion sidecar
        fv = db.query(FileVersion).filter(FileVersion.file_id == file_id).first()
        if fv:
            fv.schema_version = SCHEMA_VERSION
            fv.extractor_version = 1
            fv.fts_version = 1
            fv.indexed_at = datetime.utcnow()
        else:
            db.add(FileVersion(
                file_id=file_id,
                schema_version=SCHEMA_VERSION,
                extractor_version=1,
                fts_version=1,
                findings_epoch=0,
                indexed_at=datetime.utcnow(),
            ))

        # Update file status
        log_file.status = "ready"
        log_file.line_count = line_count
        log_file.size_bytes = os.path.getsize(file_path)
        db.commit()

        logger.info(f"Finished indexing {log_file.filename}. Lines: {line_count}")

    except Exception as e:
        logger.error(f"Error indexing file {file_id}: {e}")
        log_file.status = "error"
        log_file.error_message = str(e)
        db.commit()
