import re

text = "00012052: 2025-11-20T13:15:13 [PERFORMANCE     ]T:  Source latency 0.00 seconds, Target latency 0.00 seconds, Handling latency 0.00 seconds  (replicationtask.c:3927)"

PERF_RE = re.compile(
    r'^\s*\d+:\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}).*'
    r'\[PERFORMANCE\s*\].*?Source latency ([0-9.]+) seconds,\s*'
    r'Target latency ([0-9.]+) seconds,\s*'
    r'Handling latency ([0-9.]+) seconds',
    re.MULTILINE
)

matches = PERF_RE.findall(text)
print(f"Matches: {matches}")

