"""Extract canonical error codes from log lines.

Handles SqlState/NativeError, ORA-*, ODBC codes, and common Replicate error forms.
Returns a canonical string suitable for grouping (e.g. 'SqlState:HY000/1205', 'ORA-00054').
"""
import re
from typing import Optional

_SQLSTATE_RE = re.compile(
    r'SqlState:\s*(\w+)\s+NativeError:\s*(\d+)', re.IGNORECASE
)
_ORA_RE = re.compile(r'(ORA-\d{5})', re.IGNORECASE)
_MYSQL_RE = re.compile(r'MySQL.*?Error\s+(\d{4})', re.IGNORECASE)
_PG_RE = re.compile(r'(?:SQLSTATE|PG)\s*[=:]?\s*(\d{5})', re.IGNORECASE)
_ODBC_RE = re.compile(r'RetCode:\s*(SQL_\w+)', re.IGNORECASE)
_NATIVE_ONLY_RE = re.compile(r'NativeError:\s*(\d+)', re.IGNORECASE)


def extract_error_code(line: str) -> Optional[str]:
    """Return a canonical error code from a log line, or None."""
    m = _SQLSTATE_RE.search(line)
    if m:
        return f"SqlState:{m.group(1)}/{m.group(2)}"

    m = _ORA_RE.search(line)
    if m:
        return m.group(1).upper()

    m = _MYSQL_RE.search(line)
    if m:
        return f"MySQL:{m.group(1)}"

    m = _PG_RE.search(line)
    if m:
        return f"PG:{m.group(1)}"

    m = _ODBC_RE.search(line)
    if m:
        code = m.group(1).upper()
        if code != "SQL_SUCCESS":
            return code

    m = _NATIVE_ONLY_RE.search(line)
    if m and int(m.group(1)) != 0:
        return f"Native:{m.group(1)}"

    return None
