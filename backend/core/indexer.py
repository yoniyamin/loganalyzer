import os
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from backend.database import (
    LogFile, LogIndex, LogPerformance, LogOracleRedoRead, LogOracleRedoLogSession, LogStats, LogError,
)
from collections import defaultdict, Counter
from backend.core.patterns import (
    LINE_FULL_RE, LINE_START_RE, PERF_RE, ERR_RE, ASM_PREPARE_READ_RE,
    parse_oracle_archived_redo_read, parse_oracle_redo_log_open, parse_oracle_redo_log_close,
)
from backend.core.reader import clear_file_cache

logger = logging.getLogger(__name__)

BATCH_SIZE = 5000  # Commit to DB every N lines
INDEX_INTERVAL = 500  # Create sparse index every N lines (reduced for better seeking)

def process_log_file(db: Session, file_id: int):
    """
    Reads the log file, builds an index, and populates stats/performance tables.
    Updates the file status to 'ready' upon completion.
    """
    log_file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not log_file:
        logger.error(f"File ID {file_id} not found.")
        return

    # Clear any cached lines for this file when reindexing
    clear_file_cache(file_id)

    try:
        file_path = log_file.file_path
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at {file_path}")

        logger.info(f"Starting indexing for {log_file.filename}...")
        
        db.query(LogOracleRedoRead).filter(LogOracleRedoRead.file_id == file_id).delete(
            synchronize_session=False
        )
        db.query(LogOracleRedoLogSession).filter(LogOracleRedoLogSession.file_id == file_id).delete(
            synchronize_session=False
        )
        db.commit()
        
        # Temp storage for batch inserts
        perf_batch = []
        redo_batch = []
        session_batch = []
        error_batch = []
        index_batch = []
        pending_redo_log_opens = {}
        
        # Aggregation stats: (component, thread) -> {count, first_ts, last_ts}
        stats_map = {}

        # ASM worker thread tracking: thread_id -> Counter({stmt_num: count})
        asm_thread_stmts = defaultdict(Counter)

        # Tracking state
        line_count = 0
        byte_offset = 0
        last_thread = None
        last_component = None
        last_ts = None
        
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            while True:
                # Capture current offset before reading the line
                current_offset = f.tell()
                line = f.readline()
                if not line:
                    break
                
                line_len = len(line) # bytes? utf-8 read gives str len, tell() gives bytes. 
                # Be careful: f.tell() in text mode on Windows can be tricky, but usually works for seeking if opened in text mode. 
                # Ideally open in binary for exact offsets, but we need text matching.
                # Python 3 text mode tell() returns an opaque number that is valid for seek(), which is what we need.
                
                # Check empty
                if not line.strip():
                    line_count += 1
                    continue

                # Parse Line
                m = LINE_FULL_RE.match(line)
                timestamp = None
                thread_id = None
                component = None
                
                if m:
                    thread_id = m.group(1)
                    ts_str = m.group(2)
                    component = m.group(3).strip()
                    timestamp = datetime.fromisoformat(ts_str)
                    
                    last_thread = thread_id
                    last_component = component
                    last_ts = timestamp
                else:
                    # Check start RE
                    if LINE_START_RE.match(line):
                        # New line but unknown component
                        # Try to grab timestamp
                        import re
                        ts_m = re.match(r'^\s*\d+:\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', line)
                        if ts_m:
                             timestamp = datetime.fromisoformat(ts_m.group(1))
                             last_ts = timestamp
                        # Try to extract thread_id from the start of the line
                        thread_match = re.match(r'^\s*(\d+):', line)
                        if thread_match:
                            thread_id = thread_match.group(1)
                            last_thread = thread_id
                        component = "UNKNOWN"
                        last_component = component
                    else:
                        # Continuation
                        thread_id = last_thread
                        component = last_component
                        timestamp = last_ts

                # 1. Update Index
                if line_count % INDEX_INTERVAL == 0:
                    index_batch.append(LogIndex(
                        file_id=file_id,
                        line_number=line_count,
                        byte_offset=current_offset,
                        timestamp=timestamp
                    ))

                # 2. Check Performance
                # Perf logs can span multiple lines but our regex in app.py was multiline on the whole file.
                # Streaming perf regex is harder. 
                # Simple approach: Check if line contains [PERFORMANCE] and then try to parse it specifically?
                # The original PERF_RE is multiline. 
                # "^\s*\d+: ... [PERFORMANCE] ... Source latency ... "
                # It seems it's usually on one line in the log file or continuation lines?
                # The provided PERF_RE uses `re.MULTILINE`, implying it might match across newlines?
                # Actually, in `app.py`, `parse_performance` runs on the whole text.
                # Let's try to match PERF_RE on the single line first, or keep a small buffer if needed.
                # The regex starts with `^\s*\d+: ...`. It looks like it matches a full log entry.
                # If the log entry is split across lines, we might miss it if we only check `line`.
                # BUT, `LINE_FULL_RE` matches the start. 
                # If we see [PERFORMANCE] in component, we can try to parse the latencies from the text.
                
                if component == "PERFORMANCE" and timestamp:
                    # Try to extract latencies from this line
                    # Reuse the logic from app.py but adapted for single line
                    # Regex: Source latency ([0-9.]+) seconds,\s*Target latency ([0-9.]+) seconds,\s*Handling latency ([0-9.]+) seconds
                    import re
                    lat_m = re.search(r'Source latency ([0-9.]+) seconds,\s*Target latency ([0-9.]+) seconds,\s*Handling latency ([0-9.]+) seconds', line)
                    if lat_m:
                        perf_batch.append(LogPerformance(
                            file_id=file_id,
                            line_number=line_count,  # Store the line number!
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
                            tid = open_info.get("thread_id") or thread_id
                            if t0 and t1:
                                dur = (t1 - t0).total_seconds()
                                if dur >= 0:
                                    tid_s = str(tid) if tid not in (None, "") else None
                                    session_batch.append(LogOracleRedoLogSession(
                                        file_id=file_id,
                                        thread_id=tid_s,
                                        redo_path=cpath,
                                        line_open=open_info["line_number"],
                                        line_close=line_count,
                                        timestamp_open=t0,
                                        timestamp_close=t1,
                                        duration_seconds=dur,
                                    ))

                # 2b. Track ASM parallel read worker messages
                if component == "SOURCE_CAPTURE" and thread_id:
                    asm_m = ASM_PREPARE_READ_RE.search(line)
                    if asm_m:
                        asm_thread_stmts[thread_id][asm_m.group(1)] += 1

                # 3. Aggregates
                if thread_id and component:
                    key = (component, thread_id)
                    if key not in stats_map:
                        stats_map[key] = {
                            "count": 0,
                            "first_ts": timestamp,
                            "last_ts": timestamp
                        }
                    stats = stats_map[key]
                    stats["count"] += 1
                    if timestamp:
                        stats["last_ts"] = timestamp
                        if not stats["first_ts"]:
                            stats["first_ts"] = timestamp

                # 4. Errors
                if ERR_RE.search(line):
                    error_batch.append(LogError(
                        file_id=file_id,
                        line_number=line_count,
                        timestamp=timestamp,
                        component=component,
                        thread_id=thread_id,
                        text=line[:500] # Truncate if too long
                    ))

                line_count += 1

                # Batch Commit
                if line_count % BATCH_SIZE == 0:
                    db.bulk_save_objects(index_batch)
                    db.bulk_save_objects(perf_batch)
                    db.bulk_save_objects(redo_batch)
                    db.bulk_save_objects(session_batch)
                    db.bulk_save_objects(error_batch)
                    db.commit()
                    
                    index_batch = []
                    perf_batch = []
                    redo_batch = []
                    session_batch = []
                    error_batch = []

        # Final Commit
        if index_batch: db.bulk_save_objects(index_batch)
        if perf_batch: db.bulk_save_objects(perf_batch)
        if redo_batch: db.bulk_save_objects(redo_batch)
        if session_batch: db.bulk_save_objects(session_batch)
        if error_batch: db.bulk_save_objects(error_batch)
        
        # Post-process: merge ASM-only worker threads into virtual groups
        # A thread is "ASM-only" if every one of its SOURCE_CAPTURE messages
        # is a "Preparing read from ASM statement (N)" line.
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

        # Save Stats
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
        
        # Update File Status
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


