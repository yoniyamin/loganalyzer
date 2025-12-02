import re
from datetime import datetime

PERF_RE = re.compile(
    r'^\s*\d+:\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}).*'
    r'\[PERFORMANCE\s*\].*?Source latency ([0-9.]+) seconds,\s*'
    r'Target latency ([0-9.]+) seconds,\s*'
    r'Handling latency ([0-9.]+) seconds',
    re.MULTILINE
)

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

LINE_TS_RE = re.compile(
    r'^\s*\d+:\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})'
)

def build_log_lines(text: str):
    """Return list of {timestamp: datetime|None, text:str}."""
    lines = []
    for line in text.splitlines():
        m = LINE_TS_RE.match(line)
        ts = datetime.fromisoformat(m.group(1)) if m else None
        lines.append({"timestamp": ts, "text": line})
    return lines

filename = "reptask_P1JRNC_DATABRICKS_1_B (6).log"
print(f"Reading {filename}...")
with open(filename, "rb") as f:
    raw = f.read().decode("utf-8", errors="replace")

print(f"File length: {len(raw)}")
perf_points = parse_performance(raw)
print(f"Found {len(perf_points)} performance points.")

log_lines = build_log_lines(raw)
print(f"Built {len(log_lines)} log lines.")
valid_ts = sum(1 for l in log_lines if l["timestamp"] is not None)
print(f"Lines with valid timestamp: {valid_ts}")

if perf_points:
    print(f"First point: {perf_points[0]}")

