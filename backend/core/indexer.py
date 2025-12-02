import os
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from backend.database import LogFile, LogIndex, LogPerformance, LogStats, LogError
from backend.core.patterns import LINE_FULL_RE, LINE_START_RE, PERF_RE, ERR_RE

logger = logging.getLogger(__name__)

BATCH_SIZE = 5000  # Commit to DB every N lines
INDEX_INTERVAL = 1000  # Create sparse index every N lines

def process_log_file(db: Session, file_id: int):
    """
    Reads the log file, builds an index, and populates stats/performance tables.
    Updates the file status to 'ready' upon completion.
    """
    log_file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not log_file:
        logger.error(f"File ID {file_id} not found.")
        return

    try:
        file_path = log_file.file_path
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at {file_path}")

        logger.info(f"Starting indexing for {log_file.filename}...")
        
        # Temp storage for batch inserts
        perf_batch = []
        error_batch = []
        index_batch = []
        
        # Aggregation stats: (component, thread) -> {count, first_ts, last_ts}
        stats_map = {}

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
                    db.bulk_save_objects(error_batch)
                    db.commit()
                    
                    index_batch = []
                    perf_batch = []
                    error_batch = []

        # Final Commit
        if index_batch: db.bulk_save_objects(index_batch)
        if perf_batch: db.bulk_save_objects(perf_batch)
        if error_batch: db.bulk_save_objects(error_batch)
        
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


