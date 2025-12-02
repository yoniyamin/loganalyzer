import re

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


