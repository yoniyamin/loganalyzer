from flask import Flask, render_template, request, jsonify
from datetime import datetime
import re
import logging
import time

app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Cache busting version - changes on app restart
CACHE_VERSION = str(int(time.time()))

# ---- Simple in-memory "session" for a single user ----
CURRENT_LOG_LINES = []
CURRENT_LATENCY_DATA = {}
CURRENT_STATS = {}
RECENT_LOGS = []  # List of recently loaded log filenames
LOG_CACHE = {}  # Cache of log file contents by filename

@app.context_processor
def inject_cache_version():
    """Inject cache version into all templates for cache busting."""
    return dict(cache_version=CACHE_VERSION)

COMPONENT_DESCRIPTIONS = {
    "ADDONS": "Only relevant when working with a Replicate add-on. Currently, the only add-ons are user-defined transformations.",
    "ASSERTION": "When the log contains an ASSERTION WARNING, it usually means that Replicate detected an anomaly with the data, which might result in replication issues at some stage.",
    "COMMON": "Writes low level messages such as network activity. Not recommended to set to 'Trace' as it will write a huge amount of data to the log.",
    "COMMUNICATION": "Provides additional information about the communication between Replicate and the Source and Target components.",
    "DATA_RECORD": "Only available for some endpoints and may be implemented differently for each endpoint. It writes information about each change that occurs.",
    "DATA_STRUCTURE": "Used for internal Replicate data structures and is related to how the code deals with the data and stores it in memory.",
    "FILE_FACTORY": "Relevant to Hadoop Target, Amazon Redshift and Microsoft Azure SQL Synapse Analytics. Moves files from Replicate to the target.",
    "FILE_TRANSFER": "Writes to the log when the File Transfer component is used to push files to a specific location. (AKA CIFTA)",
    "INFRASTRUCTURE": "Records infrastructure information related to the infrastructure layers of Replicate code: ODBC, logger, PROTO_BUF, REPOSITORY, etc.",
    "IO": "Logs all IO operations (i.e. file operations), such as checking directory size, creating directories, deleting directories, and so on.",
    "METADATA_CHANGES": "Will show the actual DDL changes which are included in the scope (available for specific endpoints).",
    "METADATA_MANAGER": "Writes information whenever Replicate reads metadata from the source or target, or stores it.",
    "PERFORMANCE": "Currently used for latency only. Logs latency values for source and target endpoints every 30 seconds.",
    "REST_SERVER": "Handles all REST requests (API and UI). Also shows the interaction between Replicate and Qlik Enterprise Manager.",
    "SERVER": "The server thread in the task that communicates with the Replicate Server service on task start, stop, etc.",
    "SORTER": "The main component in CDC that routes the changes captured from the source to the target.",
    "SORTER_STORAGE": "The storage component of the Sorter which stores transactions in memory and offloads them to disk when too large.",
    "SOURCE_CAPTURE": "This is main CDC component on the source side. Should be used to troubleshoot any CDC source issue.",
    "SOURCE_LOG_DUMP": "When using Replicate Log Reader, this component creates additional files with dumps of the read changes.",
    "SOURCE_UNLOAD": "Records source activity related to Full load operations and includes the SELECT statement executed against the source tables.",
    "STREAM": "The Stream is the buffer in memory where data and control commands are kept.",
    "STREAM_COMPONENT": "Used by the Source, Sorter and Target to interact and communicate with the Stream component.",
    "TABLES_MANAGER": "Manage the table status including whether they were loaded into the target, the number of events, etc.",
    "TARGET_APPLY": "Determines which changes are applied to the target during CDC. Relevant to both Batch optimized apply and Transactional apply.",
    "TARGET_LOAD": "Provides information about Full Load operations on the target side. May also print the metadata of the target table.",
    "TASK_MANAGER": "This is the parent task component that manages the other components in the task.",
    "TRANSFORMATION": "Logs information related to transformations.",
    "UTILITIES": "In most cases, UTILITIES logs issues related to notifications."
}

PERF_RE = re.compile(
    r'^\s*\d+:\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}).*'
    r'\[PERFORMANCE\s*\].*?Source latency ([0-9.]+) seconds,\s*'
    r'Target latency ([0-9.]+) seconds,\s*'
    r'Handling latency ([0-9.]+) seconds',
    re.MULTILINE
)

# Matches: ThreadID: Timestamp [Component] ...
# Changed from \w+ to [^\]]+ to handle components with dashes or spaces if they occur (e.g. MD-CHANGE)
LINE_FULL_RE = re.compile(
    r'^\s*(\d+):\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\s*\[([^\]]+)\]'
)

# Regex to detect simple timestamp at start of line (to check if it is a new log line or continuation)
LINE_START_RE = re.compile(r'^\s*\d+:\s+\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')


def parse_performance(text: str):
    """Return list of dicts with timestamp + latencies."""
    matches = PERF_RE.findall(text)
    perf_points = [
        {
            "timestamp": m[0],
            "source": float(m[1]),
            "target": float(m[2]),
            "handling": float(m[3]),
        }
        for m in matches
    ]
    return perf_points


def build_log_lines(text: str):
    """Return list of {timestamp, text, thread, component}. Filters out empty lines."""
    lines = []
    
    last_thread = None
    last_component = None
    last_ts = None
    
    line_count = 0
    matched_count = 0
    continuation_count = 0
    empty_count = 0
    
    for line in text.splitlines():
        line_count += 1
        
        # Skip empty lines at parse time to maintain consistent indices
        if not line or not line.strip():
            empty_count += 1
            continue
        
        m = LINE_FULL_RE.match(line)
        if m:
            matched_count += 1
            thread_id = m.group(1)
            ts_str = m.group(2)
            component = m.group(3).strip() # strip spaces from regex capture
            ts = datetime.fromisoformat(ts_str)
            
            last_thread = thread_id
            last_component = component
            last_ts = ts
        else:
            # Check if this is a new log line but regex failed
            if LINE_START_RE.match(line):
                # It starts like a log line but didn't match FULL_RE.
                # Treat as UNKNOWN component but try to grab timestamp.
                thread_id = None
                component = "UNKNOWN"
                ts = None
                ts_m = re.match(r'^\s*\d+:\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', line)
                if ts_m:
                     ts = datetime.fromisoformat(ts_m.group(1))
                     last_ts = ts
                
                last_thread = None # Reset thread context if new line starts without thread info we recognize
                last_component = component
            else:
                # Continuation line
                continuation_count += 1
                thread_id = last_thread
                component = last_component
                ts = last_ts
        
        lines.append({
            "timestamp": ts,
            "text": line,
            "thread": thread_id,
            "component": component
        })
    
    logger.debug(f"Parsed {line_count} raw lines -> {len(lines)} log entries (matched: {matched_count}, continuation: {continuation_count}, empty: {empty_count})")
    return lines


def calc_stats(perf_points, filename, text):
    line_count = len(text.splitlines())
    size_kb = len(text.encode("utf-8")) / 1024.0

    if not perf_points:
        return {
            "has_perf": False,
            "filename": filename,
            "line_count": line_count,
            "size_kb": size_kb,
        }

    def summary(values):
        return {
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
        }

    sources = [p["source"] for p in perf_points]
    targets = [p["target"] for p in perf_points]
    handlings = [p["handling"] for p in perf_points]

    return {
        "has_perf": True,
        "filename": filename,
        "line_count": line_count,
        "size_kb": size_kb,
        "count": len(perf_points),
        "start_time": perf_points[0]["timestamp"],
        "end_time": perf_points[-1]["timestamp"],
        "source_latency": summary(sources),
        "target_latency": summary(targets),
        "handling_latency": summary(handlings),
    }


def build_latency_series(perf_points):
    """Transform to arrays for Plotly."""
    if not perf_points:
        return {
            "timestamps": [],
            "source": [],
            "target": [],
            "handling": [],
        }
    return {
        "timestamps": [p["timestamp"] for p in perf_points],
        "source": [p["source"] for p in perf_points],
        "target": [p["target"] for p in perf_points],
        "handling": [p["handling"] for p in perf_points],
    }


def get_log_snippet_around_ts(log_lines, ts_str, before=15, after=25):
    """Return list of raw lines around nearest timestamp."""
    if not log_lines or not ts_str:
        return []

    try:
        target_ts = datetime.fromisoformat(str(ts_str))
    except ValueError:
        return []

    best_idx = None
    best_diff = None

    for i, entry in enumerate(log_lines):
        ts = entry["timestamp"]
        if ts is None:
            continue
        diff = abs((ts - target_ts).total_seconds())
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_idx = i

    if best_idx is None:
        return []

    start = max(0, best_idx - before)
    end = min(len(log_lines), best_idx + after)
    return [e["text"] for e in log_lines[start:end]]


def get_snippet_start_idx(log_lines, ts_str):
    """Return start index of the snippet."""
    if not log_lines or not ts_str:
        return 0
    try:
        target_ts = datetime.fromisoformat(str(ts_str))
    except ValueError:
        return 0

    best_idx = 0
    best_diff = None
    for i, entry in enumerate(log_lines):
        ts = entry["timestamp"]
        if ts is None: continue
        diff = abs((ts - target_ts).total_seconds())
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_idx = i
            
    return max(0, best_idx - 15) # matches 'before=15' logic


@app.route("/", methods=["GET", "POST"])
def index():
    global CURRENT_LOG_LINES, CURRENT_LATENCY_DATA, CURRENT_STATS, RECENT_LOGS, LOG_CACHE

    # Clear globals on GET request (app startup) - only if no query params to preserve on refresh
    if request.method == "GET" and not request.args.get("keep_session"):
        logger.info("GET request - clearing session data")
        CURRENT_LOG_LINES = []
        CURRENT_LATENCY_DATA = {}
        CURRENT_STATS = {}
        # Don't clear RECENT_LOGS and LOG_CACHE - keep for user convenience

    latency_data = CURRENT_LATENCY_DATA
    stats = CURRENT_STATS
    initial_snippet = []
    initial_start_idx = 0

    if request.method == "POST":
        if "log_file" not in request.files:
            return render_template("index.html",
                                   latency_data={},
                                   stats={"has_perf": False},
                                   initial_snippet=[],
                                   initial_start_idx=0,
                                   recent_logs=RECENT_LOGS,
                                   message="No file uploaded.")

        files = request.files.getlist("log_file")
        if not files or (len(files) == 1 and files[0].filename == ""):
            return render_template("index.html",
                                   latency_data={},
                                   stats={"has_perf": False},
                                   initial_snippet=[],
                                   initial_start_idx=0,
                                   recent_logs=RECENT_LOGS,
                                   message="No file selected.")

        all_raw_parts = []
        filenames = []
        for f in files:
            if f.filename:
                filenames.append(f.filename)
                content = f.read().decode("utf-8", errors="replace")
                all_raw_parts.append(content)
                
                # Cache the file content
                LOG_CACHE[f.filename] = content
                
                # Add to recent logs (avoid duplicates)
                if f.filename not in RECENT_LOGS:
                    RECENT_LOGS.insert(0, f.filename)
                    # Keep only last 10
                    if len(RECENT_LOGS) > 10:
                        removed = RECENT_LOGS.pop()
                        # Clean up cache for removed item
                        if removed in LOG_CACHE:
                            del LOG_CACHE[removed]

        if not all_raw_parts:
             return render_template("index.html",
                                   latency_data={},
                                   stats={"has_perf": False},
                                   initial_snippet=[],
                                   initial_start_idx=0,
                                   recent_logs=RECENT_LOGS,
                                   message="No valid files uploaded.")

        # Only load the first file for display
        raw = all_raw_parts[0]
        display_filename = filenames[0]

        logger.info(f"Processing file: {display_filename}, size: {len(raw)} bytes")
        
        perf_points = parse_performance(raw)
        logger.info(f"Found {len(perf_points)} performance data points")
        
        CURRENT_LOG_LINES = build_log_lines(raw)
        logger.info(f"Built {len(CURRENT_LOG_LINES)} log lines (empty lines already filtered)")
        
        latency_data = CURRENT_LATENCY_DATA = build_latency_series(perf_points)
        stats = CURRENT_STATS = calc_stats(perf_points, display_filename, raw)

        # Show snippet - always start with first 150 lines (no filtering needed - already done at parse)
        initial_snippet = [l["text"] for l in CURRENT_LOG_LINES[:150]]
        initial_start_idx = 0
        
        logger.info(f"Initial snippet has {len(initial_snippet)} lines")
        
        # Override with perf-based snippet if available
        if perf_points:
            last_ts = perf_points[-1]["timestamp"]
            perf_snippet = get_log_snippet_around_ts(CURRENT_LOG_LINES, last_ts)
            perf_start_idx = get_snippet_start_idx(CURRENT_LOG_LINES, last_ts)
            if perf_snippet and len(perf_snippet) > 20:  # Only use if we got a good chunk
                initial_snippet = perf_snippet
                initial_start_idx = perf_start_idx
                logger.info(f"Using performance-based snippet at index {perf_start_idx}")
        
        logger.info(f"Final initial snippet: {len(initial_snippet)} lines starting at index {initial_start_idx}")

    return render_template(
        "index.html",
        latency_data=latency_data,
        stats=stats,
        initial_snippet=initial_snippet,
        initial_start_idx=initial_start_idx,
        recent_logs=RECENT_LOGS,
        message=None,
    )


@app.route("/log_snippet")
def log_snippet():
    ts = request.args.get("ts")
    lines = get_log_snippet_around_ts(CURRENT_LOG_LINES, ts)
    return jsonify({"lines": lines})


@app.route("/log_chunk")
def log_chunk():
    """Return a chunk of log lines by index range."""
    start_idx = int(request.args.get("start", 0))
    count = int(request.args.get("count", 100))
    
    total_lines = len(CURRENT_LOG_LINES)
    end_idx = min(start_idx + count, total_lines)
    start_idx = max(0, start_idx)
    
    # Don't filter here - already filtered at parse time
    chunk = [l["text"] for l in CURRENT_LOG_LINES[start_idx:end_idx]]
    
    logger.debug(f"log_chunk: requested {start_idx}:{end_idx}, returning {len(chunk)} lines (total: {total_lines})")
    
    return jsonify({
        "lines": chunk,
        "start": start_idx,
        "end": end_idx,
        "total": total_lines
    })


@app.route("/log_chunk_ts")
def log_chunk_ts():
    """Return a chunk of log lines centered around a timestamp."""
    ts_str = request.args.get("ts")
    count = int(request.args.get("count", 100))
    
    if not ts_str:
        return jsonify({"lines": [], "start": 0, "total": len(CURRENT_LOG_LINES)})

    try:
        target_ts = datetime.fromisoformat(str(ts_str))
    except ValueError:
        return jsonify({"lines": [], "start": 0, "total": len(CURRENT_LOG_LINES)})

    # Find best index
    best_idx = 0
    best_diff = None
    
    for i, entry in enumerate(CURRENT_LOG_LINES):
        ts = entry["timestamp"]
        if ts is None:
            continue
        diff = abs((ts - target_ts).total_seconds())
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_idx = i
            
    half = count // 2
    start_idx = max(0, best_idx - half)
    end_idx = min(len(CURRENT_LOG_LINES), start_idx + count)
    
    chunk = [l["text"] for l in CURRENT_LOG_LINES[start_idx:end_idx]]
    
    return jsonify({
        "lines": chunk,
        "start": start_idx,
        "end": end_idx,
        "total": len(CURRENT_LOG_LINES)
    })


@app.route("/analysis_data")
def analysis_data():
    """Return list of threads grouped by component."""
    components_map = {}
    all_errors = []
    
    # Regex for Errors/Warnings
    ERR_RE = re.compile(r'(\][EW]:|SQL_ERROR|SqlState:|NativeError:)', re.IGNORECASE)

    for i, line in enumerate(CURRENT_LOG_LINES):
        tid = line["thread"]
        comp = line["component"]
        text = line["text"]
        
        # Check for error
        if ERR_RE.search(text):
            all_errors.append({
                "line_idx": i,
                "text": text,
                "thread": tid,
                "component": comp,
                "timestamp": line["timestamp"].isoformat() if line["timestamp"] else None
            })

        if tid:
            comp_key = comp if comp else "UNKNOWN"
            
            if comp_key not in components_map:
                components_map[comp_key] = {}
            
            if tid not in components_map[comp_key]:
                components_map[comp_key][tid] = {
                    "id": tid,
                    "count": 0,
                    "first_ts": line["timestamp"],
                    "last_ts": line["timestamp"]
                }
            
            components_map[comp_key][tid]["count"] += 1
            if line["timestamp"]:
                components_map[comp_key][tid]["last_ts"] = line["timestamp"]
                if not components_map[comp_key][tid]["first_ts"]:
                    components_map[comp_key][tid]["first_ts"] = line["timestamp"]

    # Convert to list structure
    comp_list = []
    for comp_name, threads_dict in components_map.items():
        t_list = list(threads_dict.values())
        t_list.sort(key=lambda x: x["count"], reverse=True)
        comp_list.append({
            "name": comp_name,
            "threads": t_list,
            "total_lines": sum(t["count"] for t in t_list)
        })
    
    comp_list.sort(key=lambda x: x["total_lines"], reverse=True)
    
    return jsonify({
        "components": comp_list,
        "errors": all_errors
    })


@app.route("/thread_log")
def thread_log():
    """Return log lines for a specific thread with gap calculation."""
    tid = request.args.get("thread_id")
    if not tid:
        return jsonify({"lines": []})
        
    filtered_lines = []
    last_ts = None
    
    # Regex for marking errors in trace
    ERR_RE = re.compile(r'(\][EW]:|SQL_ERROR|SqlState:|NativeError:)', re.IGNORECASE)

    for line in CURRENT_LOG_LINES:
        if line["thread"] == tid:
            gap = None
            current_ts = line["timestamp"]
            if current_ts and last_ts:
                gap = (current_ts - last_ts).total_seconds()
            
            if current_ts:
                last_ts = current_ts
            
            is_error = bool(ERR_RE.search(line["text"]))

            filtered_lines.append({
                "text": line["text"],
                "gap": gap,
                "timestamp": current_ts.isoformat() if current_ts else None,
                "is_error": is_error
            })
            
    return jsonify({"lines": filtered_lines})


@app.route("/component_info")
def component_info():
    comp = request.args.get("component")
    desc = COMPONENT_DESCRIPTIONS.get(comp, "No description available.")
    return jsonify({"component": comp, "description": desc})


@app.route("/analysis_report")
def analysis_report():
    """Generate a summary report based on apply patterns (Bulk vs One-by-One)."""
    # Regex for applying patterns
    OBO_RE = re.compile(r'Applying\s+\S+\s+one-by-one for table\s+(\S+)', re.IGNORECASE)
    BULK_BACK_RE = re.compile(r'Switch back to bulk apply mode', re.IGNORECASE)
    BULK_FINISH_RE = re.compile(r'Finish Bulk|Bulk finished', re.IGNORECASE)
    BULK_MAP_RE = re.compile(r'bulk_map:\s+seq\s+(\d+):(\d+)\s+(\w+)', re.IGNORECASE)
    
    events = []
    
    # State tracking
    obo_active = False
    obo_start_ts = None
    obo_table = None
    
    for line in CURRENT_LOG_LINES:
        text = line["text"]
        ts = line["timestamp"]
        if not ts: 
            continue
            
        # One-by-One start
        m_obo = OBO_RE.search(text)
        if m_obo:
            obo_active = True
            obo_table = m_obo.group(1)
            obo_start_ts = ts
            events.append({
                "type": "OBO_START",
                "ts": ts,
                "table": obo_table,
                "text": text
            })
            continue
            
        # Switch back to Bulk
        if obo_active and BULK_BACK_RE.search(text):
            duration = (ts - obo_start_ts).total_seconds() if obo_start_ts else 0
            events.append({
                "type": "OBO_END",
                "ts": ts,
                "duration": duration,
                "table": obo_table,
                "text": text
            })
            obo_active = False
            obo_table = None
            continue
        
        # Bulk Map (High importance)
        m_bmap = BULK_MAP_RE.search(text)
        if m_bmap:
             events.append({
                "type": "BULK_MAP",
                "ts": ts,
                "seq_start": m_bmap.group(1),
                "seq_end": m_bmap.group(2),
                "op": m_bmap.group(3),
                "text": text
            })

        # Finish Bulk
        if BULK_FINISH_RE.search(text):
             events.append({
                "type": "BULK_FINISH",
                "ts": ts,
                "text": text
            })

    summary = {
        "obo_events": [e for e in events if e["type"] == "OBO_END"],
        "bulk_maps": [e for e in events if e["type"] == "BULK_MAP"],
        "bulk_finishes": [e for e in events if e["type"] == "BULK_FINISH"]
    }
    
    return jsonify(summary)


@app.route("/search_log")
def search_log():
    """Search current log with regex pattern."""
    pattern = request.args.get("pattern", "")
    case_sensitive = request.args.get("case_sensitive", "false") == "true"
    
    logger.info(f"Search requested: pattern='{pattern}', case_sensitive={case_sensitive}")
    
    if not pattern:
        return jsonify({"matches": [], "count": 0})
    
    try:
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)
    except re.error as e:
        logger.error(f"Invalid regex pattern '{pattern}': {e}")
        return jsonify({"error": f"Invalid regex: {str(e)}", "matches": [], "count": 0})
    
    matches = []
    for idx, line in enumerate(CURRENT_LOG_LINES):
        text = line["text"]
        if text and regex.search(text):
            matches.append({
                "line_idx": idx,
                "text": text,
                "timestamp": line["timestamp"].isoformat() if line["timestamp"] else None
            })
    
    logger.info(f"Search complete: found {len(matches)} matches out of {len(CURRENT_LOG_LINES)} lines")
    return jsonify({"matches": matches, "count": len(matches)})


@app.route("/clear_recent")
def clear_recent():
    """Clear recent logs list."""
    global RECENT_LOGS, LOG_CACHE
    RECENT_LOGS = []
    LOG_CACHE = {}
    return jsonify({"status": "ok"})


@app.route("/load_cached_log")
def load_cached_log():
    """Load a previously uploaded log from cache."""
    global CURRENT_LOG_LINES, CURRENT_LATENCY_DATA, CURRENT_STATS, LOG_CACHE
    
    filename = request.args.get("filename")
    logger.info(f"Loading cached log: {filename}")
    
    if not filename or filename not in LOG_CACHE:
        logger.error(f"Log file not found in cache: {filename}")
        return jsonify({"error": "Log file not found in cache"}), 404
    
    raw = LOG_CACHE[filename]
    
    perf_points = parse_performance(raw)
    logger.info(f"Cached log: Found {len(perf_points)} performance data points")
    
    CURRENT_LOG_LINES = build_log_lines(raw)
    logger.info(f"Cached log: Built {len(CURRENT_LOG_LINES)} log lines (empty lines already filtered)")
    
    latency_data = CURRENT_LATENCY_DATA = build_latency_series(perf_points)
    stats = CURRENT_STATS = calc_stats(perf_points, filename, raw)
    
    # Get initial snippet - always start with first 150 lines (no filtering needed)
    initial_snippet = [l["text"] for l in CURRENT_LOG_LINES[:150]]
    initial_start_idx = 0
    
    logger.info(f"Cached log: Initial snippet has {len(initial_snippet)} lines")
    
    return jsonify({
        "success": True,
        "latency_data": latency_data,
        "stats": stats,
        "initial_snippet": initial_snippet,
        "initial_start_idx": initial_start_idx,
        "total_lines": len(CURRENT_LOG_LINES)
    })


if __name__ == "__main__":
    app.run(debug=True)
