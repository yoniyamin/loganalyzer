import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime

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
    r'^\s*\d+:\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?::\d+)?.*'
    r'\[PERFORMANCE\s*\].*?Source latency ([0-9.]+) seconds,\s*'
    r'Target latency ([0-9.]+) seconds,\s*'
    r'Handling latency ([0-9.]+) seconds',
    re.MULTILINE
)

# Matches: ThreadID: Timestamp [Component] ...
# Changed from \w+ to [^\]]+ to handle components with dashes or spaces if they occur (e.g. MD-CHANGE)
# Updated to handle timestamps with microseconds like 2025-12-02T11:38:56:118446
LINE_FULL_RE = re.compile(
    r'^\s*(\d+):\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?::\d+)?\s*\[([^\]]+)\]'
)

# Regex to detect simple timestamp at start of line (to check if it is a new log line or continuation)
# Updated to handle timestamps with microseconds
LINE_START_RE = re.compile(r'^\s*\d+:\s+\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?::\d+)?')

# Regex for Errors/Warnings
ERR_RE = re.compile(r'(\][EW]:|SQL_ERROR|SqlState:|NativeError:)', re.IGNORECASE)

# Regex for applying patterns
OBO_RE = re.compile(r'Applying\s+\S+\s+one-by-one for table\s+(\S+)', re.IGNORECASE)
BULK_BACK_RE = re.compile(r'Switch back to bulk apply mode', re.IGNORECASE)
BULK_FINISH_RE = re.compile(r'Finish Bulk|Bulk finished', re.IGNORECASE)
BULK_MAP_RE = re.compile(r'bulk_map:\s+seq\s+(\d+):(\d+)\s+(\w+)', re.IGNORECASE)

# ============================================================
# ENHANCED PATTERNS FOR PERFORMANCE COCKPIT
# ============================================================

# --- Batch Analysis Patterns ---
# Batch closure reasons
BATCH_FINISH_REASON_RE = re.compile(
    r'Finish [Bb]ulk because(?: of)?\s*(.+?)(?:\s*\(|$)',
    re.IGNORECASE
)

# PK conflict patterns
PK_CONFLICT_INSERT_RE = re.compile(
    r'same bulk.*INSERT.*same PK|INSERT.*changes PK.*same bulk',
    re.IGNORECASE
)
PK_CONFLICT_UPDATE_RE = re.compile(
    r'same bulk.*Update.*updated.*same PK|Update.*changes PK.*same bulk',
    re.IGNORECASE
)
PK_CONFLICT_DELETE_RE = re.compile(
    r'same bulk.*deleted.*same PK|DELETE.*changes PK.*same bulk',
    re.IGNORECASE
)

# Batch start/end
BATCH_START_RE = re.compile(
    r'Going to start applying bulk changes',
    re.IGNORECASE
)
BATCH_END_RE = re.compile(
    r'Finished applying bulk changes|Bulk finished\.',
    re.IGNORECASE
)

# Going to run statement with seq range
APPLY_SEQ_RANGE_RE = re.compile(
    r'Going to run (\w+) statement.*from seq (\d+) to seq (\d+)',
    re.IGNORECASE
)

# Finished applying N events for table
FINISHED_APPLYING_RE = re.compile(
    r"Finished applying of (\d+) '([A-Z]+) \(\d+\)' events for table '([^']+)'\.?'([^']+)'",
    re.IGNORECASE
)

# Start applying for table
START_APPLYING_RE = re.compile(
    r"Start applying '([A-Z]+) \((\d+)\)'.*for table '([^']+)'\.?'([^']+)'",
    re.IGNORECASE
)

# --- MERGE Patterns ---
MERGE_STATEMENT_RE = re.compile(
    r'Merge table statement\s+MERGE INTO\s+[`"]?([^`"\s.]+)[`"]?\.[`"]?([^`"\s]+)[`"]?',
    re.IGNORECASE
)

MERGE_START_RE = re.compile(
    r'Going to execute MERGE|Merge table statement MERGE',
    re.IGNORECASE
)

# --- File Operations Patterns ---
FILE_COMPRESS_START_RE = re.compile(
    r"going to compress file '([^']+)' to '([^']+)'",
    re.IGNORECASE
)

FILE_COMPRESSED_RE = re.compile(
    r'file compressed',
    re.IGNORECASE
)

FILE_UPLOAD_SUCCESS_RE = re.compile(
    r"File ([^\s]+) of size (\d+) was uploaded successfully",
    re.IGNORECASE
)

CSV_FILE_NAME_RE = re.compile(
    r'(CDC[0-9A-Fa-f]+\.csv)',
    re.IGNORECASE
)

# --- Sorter Patterns ---
SORTER_MEMORY_RE = re.compile(
    r'Stop reading when memory limit reached.*is set to (true|false)',
    re.IGNORECASE
)

SORTER_RELOAD_RE = re.compile(
    r'Reload for table Id (\d+) is requested',
    re.IGNORECASE
)

SORTER_COLLECTING_RE = re.compile(
    r'Start collecting changes for table id = (\d+)',
    re.IGNORECASE
)

SORTER_TRANSACTION_RE = re.compile(
    r'Transaction consistency.*confirmed_record_id = (\d+)',
    re.IGNORECASE
)

SORTER_BACKLOG_RE = re.compile(
    r'sorter.*backlog|pending.*transactions?|waiting.*commit',
    re.IGNORECASE
)

# --- Config Extraction Patterns ---
BULK_TIMEOUT_RE = re.compile(
    r'Set Bulk Timeout\s*=\s*(\d+)\s*milliseconds',
    re.IGNORECASE
)

BULK_TIMEOUT_MIN_RE = re.compile(
    r'Set Bulk Timeout Min\s*=\s*(\d+)\s*milliseconds',
    re.IGNORECASE
)

BULK_MAX_FILE_SIZE_RE = re.compile(
    r'Bulk max file size:\s*(\d+)\s*MB,\s*(\d+)\s*KB',
    re.IGNORECASE
)

PARALLEL_APPLY_RE = re.compile(
    r'Parallel bulk apply enabled.*maximum.*?(\d+)',
    re.IGNORECASE
)

STREAM_BUFFER_SIZE_RE = re.compile(
    r'stream_buffer_size["\s:=]+(\d+)',
    re.IGNORECASE
)

STREAM_BUFFERS_NUMBER_RE = re.compile(
    r'stream_buffers_number["\s:=]+(\d+)',
    re.IGNORECASE
)

# --- Source/Target Type Detection ---
SOURCE_ENDPOINT_RE = re.compile(
    r"Source endpoint '([^']+)' is using provider",
    re.IGNORECASE
)

TARGET_ENDPOINT_RE = re.compile(
    r"Target endpoint '([^']+)' is using provider",
    re.IGNORECASE
)

TARGET_CONNECTED_RE = re.compile(
    r'Connected to server.*database.*successfully',
    re.IGNORECASE
)

TARGET_DISCONNECT_RE = re.compile(
    r'disconnected|connection lost|connection failed|ODBC error|SQL_ERROR',
    re.IGNORECASE
)

# --- Error Correlation Patterns ---
RECONNECT_RE = re.compile(
    r'reconnect|retry|connection attempt|re-establishing',
    re.IGNORECASE
)

NETWORK_ERROR_RE = re.compile(
    r'network error|socket error|timeout|connection refused|connection reset',
    re.IGNORECASE
)

RESOURCE_LIMIT_RE = re.compile(
    r'memory limit|out of memory|resource limit|thread limit|max connections',
    re.IGNORECASE
)

# --- No PK / Apply Issues ---
NO_PK_RE = re.compile(
    r'no PK for table|Apply no Bulk|without.*primary key',
    re.IGNORECASE
)

TABLE_ERROR_RE = re.compile(
    r"(?:error|failed).*table '([^']+)'\.?'([^']+)'",
    re.IGNORECASE
)

# --- Throughput Patterns ---
THROUGHPUT_RE = re.compile(
    r'(\d+)\s*(?:events?|changes?|records?)\s*(?:per|/)\s*(?:second|sec|s)',
    re.IGNORECASE
)

EVENTS_CAPTURED_RE = re.compile(
    r'captured (\d+) (?:events?|changes?)',
    re.IGNORECASE
)

# --- CDC Pipeline / Sorter Throughput Patterns ---
# Sorter received events
SORTER_RECEIVED_RE = re.compile(
    r'\[SORTER\s*\].*received\s+(\d+)\s+(?:events?|changes?|records?)',
    re.IGNORECASE
)

# Sorter sent events to apply
SORTER_SENT_RE = re.compile(
    r'\[SORTER\s*\].*sent\s+(\d+)\s+(?:events?|changes?|records?).*apply',
    re.IGNORECASE
)

# Source capture rate
SOURCE_CAPTURE_RATE_RE = re.compile(
    r'\[SOURCE_CAPTURE\s*\].*(\d+)\s+(?:events?|changes?|records?)\s*(?:per|/)\s*(?:second|sec)',
    re.IGNORECASE
)

# Apply throughput
APPLY_THROUGHPUT_RE = re.compile(
    r'\[TARGET_APPLY\s*\].*(\d+)\s+(?:events?|changes?|records?)\s*(?:per|/)\s*(?:second|sec)',
    re.IGNORECASE
)

# Sorter memory warning
SORTER_MEMORY_WARNING_RE = re.compile(
    r'\[SORTER(?:_STORAGE)?\s*\].*(?:memory|overflow|buffer full|storage limit)',
    re.IGNORECASE
)

# Sorter queue depth / backlog
SORTER_QUEUE_DEPTH_RE = re.compile(
    r'\[SORTER\s*\].*queue.*(\d+)|pending\s+(\d+)',
    re.IGNORECASE
)

# Target disconnection patterns
TARGET_DISCONNECT_EVENT_RE = re.compile(
    r'\[TARGET_APPLY\s*\].*(?:disconnect|lost connection|connection closed|connection failed)',
    re.IGNORECASE
)

# Reconnection patterns
SOURCE_RECONNECT_RE = re.compile(
    r'\[SOURCE_CAPTURE\s*\].*(?:reconnect|retry|re-establish|connection restored)',
    re.IGNORECASE
)

# Source log read position (for tracking)
SOURCE_LOG_POSITION_RE = re.compile(
    r'(?:LSN|SCN|position|log seq(?:uence)?)[\s:=]+([0-9A-Fa-f:]+)',
    re.IGNORECASE
)

# Latency spike source correlations
SOURCE_SLOW_READ_RE = re.compile(
    r'\[SOURCE_CAPTURE\s*\].*(?:slow|delay|wait|blocked)',
    re.IGNORECASE
)

# Source database contention
SOURCE_CONTENTION_RE = re.compile(
    r'\[SOURCE_CAPTURE\s*\].*(?:lock|contention|wait|blocked by)',
    re.IGNORECASE
)


# ============================================================
# HELPER FUNCTIONS FOR PATTERN CLASSIFICATION
# ============================================================

def classify_batch_closure_reason(line: str) -> str:
    """
    Classify the batch closure reason from a log line.
    Returns a short code: PKi, PKu, PKd, MEM, TIM, TMO, SNG, RES, LOAD, Normal
    """
    line_lower = line.lower()
    
    # PK conflicts
    if PK_CONFLICT_INSERT_RE.search(line):
        return "PKi"
    if PK_CONFLICT_UPDATE_RE.search(line):
        return "PKu"
    if PK_CONFLICT_DELETE_RE.search(line):
        return "PKd"
    
    # Memory
    if 'memory' in line_lower:
        return "MEM"
    
    # Timeouts
    if 'stream timeout' in line_lower:
        return "TIM"
    if 'bulk timeout' in line_lower:
        return "TMO"
    
    # Single table / reload
    if 'tables with pk' in line_lower or 'single' in line_lower:
        return "SNG"
    
    # Resume
    if 'resume' in line_lower:
        return "RES"
    
    # Load table event
    if 'start_load_table' in line_lower:
        return "LOAD"
    
    return "Normal"


def extract_table_name(line: str) -> Optional[str]:
    """Extract table name from common patterns like 'SCHEMA'.'TABLE'"""
    match = re.search(r"'([^']+)'\.+'([^']+)'", line)
    if match:
        return f"{match.group(1)}.{match.group(2)}"
    return None


def extract_timestamp(line: str) -> Optional[datetime]:
    """Extract timestamp from a log line."""
    match = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', line)
    if match:
        try:
            return datetime.fromisoformat(match.group(1))
        except ValueError:
            pass
    return None


# Closure reason descriptions for UI
CLOSURE_REASON_DESCRIPTIONS = {
    "PKi": "PK Insert Conflict - Two INSERT operations on the same primary key in the same batch",
    "PKu": "PK Update Conflict - An UPDATE changes a PK that was already modified in this batch",
    "PKd": "PK Delete Conflict - A DELETE on a PK that was modified in this batch",
    "MEM": "Memory Limit - Batch closed because memory threshold was exceeded",
    "TIM": "Stream Timeout - No data received from source within timeout period",
    "TMO": "Bulk Timeout - Maximum batch duration was reached",
    "SNG": "Single Table - Batch finished for tables with PK",
    "RES": "Resume - Batch closed for resume operation",
    "LOAD": "Load Table - Batch closed for full load table event",
    "Normal": "Normal - Batch completed normally"
}


