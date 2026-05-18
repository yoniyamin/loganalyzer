"""
Endpoint parameter lookup from ar_props.json.

Parses the Qlik Replicate endpoint property definitions and resolves
inheritance (`based_on`) to produce a flat list of parameters for any
given endpoint type. Used to inject endpoint-specific tuning references
into LLM prompts.
"""

import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

_AR_PROPS_PATH = Path(__file__).resolve().parents[2] / "static" / "ar_props.json"

# Parameters relevant to performance tuning / timeout troubleshooting.
# Only these are surfaced in prompt context to keep token cost low.
_TUNING_RELEVANT_NAMES = frozenset({
    "executeTimeout",
    "cdcTimeout",
    "connectTimeout",
    "fetchTimeout",
    "loadTimeout",
    "commandTimeout",
    "retryCount",
    "retryInterval",
    "retryTimeoutInMinutes",
    "waitForMissingRedoLogInMinutes",
    "BulkArraySize",
    "bulkArraySize",
    "batch_size",
    "maxFileSize",
    "writeBufferSize",
    "pollingInterval",
    "PacketSize",
    "cdcBatchSize",
    "parallelASMReadThreads",
    "readAheadBlocks",
    "maxLogsInLogMinerSession",
    "dumpActionIntervalSec",
    "setTruncIntervalSec",
    "textSize",
})


def _strip_json_comments(text: str) -> str:
    """Remove // and /* */ comments outside of strings and sanitize for JSON.

    Walks the text character-by-character tracking string boundaries to avoid
    stripping comment-like sequences inside JSON string values (e.g. URLs).
    """
    result = []
    i = 0
    n = len(text)
    in_string = False

    while i < n:
        ch = text[i]

        # Handle escape sequences inside strings
        if in_string and ch == '\\':
            result.append(ch)
            i += 1
            if i < n:
                result.append(text[i])
                i += 1
            continue

        # Toggle string state
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            i += 1
            continue

        if not in_string:
            # Check for // single-line comment
            if ch == '/' and i + 1 < n and text[i + 1] == '/':
                # Skip to end of line
                while i < n and text[i] != '\n':
                    i += 1
                continue
            # Check for /* block comment */
            if ch == '/' and i + 1 < n and text[i + 1] == '*':
                i += 2
                while i < n - 1 and not (text[i] == '*' and text[i + 1] == '/'):
                    i += 1
                i += 2  # skip */
                continue

        result.append(ch)
        i += 1

    text = ''.join(result)
    text = text.replace('\t', ' ')
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    return text


@lru_cache(maxsize=1)
def _load_ar_props() -> Dict[str, Any]:
    """Load and parse ar_props.json, caching the result."""
    if not _AR_PROPS_PATH.exists():
        logger.warning("ar_props.json not found at %s", _AR_PROPS_PATH)
        return {}
    try:
        raw = _AR_PROPS_PATH.read_text(encoding="utf-8")
        cleaned = _strip_json_comments(raw)
        return json.loads(cleaned)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to parse ar_props.json: %s", e)
        return {}


def _build_type_index() -> Dict[str, Dict[str, Any]]:
    """Build a lookup from type name → dbprop definition."""
    data = _load_ar_props()
    obj = data.get("object", data)
    dbprops = obj.get("dbprops", [])
    index: Dict[str, Dict[str, Any]] = {}
    for entry in dbprops:
        t = entry.get("type", "")
        if t:
            index[t.lower()] = entry
    return index


def _resolve_items(
    entry: Dict[str, Any],
    type_index: Dict[str, Dict[str, Any]],
    visited: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """Recursively resolve connect_info items including inherited ones."""
    if visited is None:
        visited = set()

    entry_type = entry.get("type", "").lower()
    if entry_type in visited:
        return []
    visited.add(entry_type)

    items: List[Dict[str, Any]] = []

    # Resolve parent first
    based_on = entry.get("based_on", "")
    if based_on:
        parent = type_index.get(based_on.lower())
        if parent:
            items.extend(_resolve_items(parent, type_index, visited))

    # Own items
    connect_info = entry.get("connect_info", {})
    own_items = connect_info.get("items", [])
    items.extend(own_items)

    return items


def get_endpoint_tuning_params(endpoint_type: str) -> List[Dict[str, str]]:
    """
    Get tuning-relevant parameters for an endpoint type.

    Resolves inheritance and returns only parameters in the tuning-relevant set.

    Args:
        endpoint_type: The endpoint type string (e.g. "sybase", "oracle", "odbc",
                       "sqlServer", "postgresql"). Case-insensitive.

    Returns:
        List of dicts with keys: name, ui_name, default_value, role (if any)
    """
    type_index = _build_type_index()
    key = endpoint_type.strip().lower()

    entry = type_index.get(key)
    if not entry:
        # Try common aliases
        aliases = {
            "sap ase": "sybase",
            "sap_ase": "sybase",
            "ase": "sybase",
            "sql server": "sqlserver",
            "mssql": "sqlserver",
            "postgres": "postgresql",
            "pg": "postgresql",
            "snowflake": "snowflake",
            "mysql": "mysql",
            "db2": "db2luw",
            "db2 luw": "db2luw",
            "db2luw": "db2luw",
            "db2 z/os": "db2z",
            "db2z": "db2z",
        }
        key = aliases.get(key, key)
        entry = type_index.get(key)
        if not entry:
            return []

    all_items = _resolve_items(entry, type_index)

    # Deduplicate by name (child overrides parent)
    seen: Dict[str, Dict[str, Any]] = {}
    for item in all_items:
        name = item.get("name", "")
        if name:
            seen[name] = item  # last wins (child overrides parent)

    results: List[Dict[str, str]] = []
    for name, item in seen.items():
        if name not in _TUNING_RELEVANT_NAMES:
            continue
        results.append({
            "name": name,
            "ui_name": item.get("ui_name", name),
            "default_value": str(item.get("default_value", "N/A")),
            "role": item.get("role", ""),
            "level": item.get("level", ""),
        })

    # Sort: executeTimeout and cdcTimeout first, then alphabetical
    priority = {"executeTimeout": 0, "cdcTimeout": 1, "loadTimeout": 2}
    results.sort(key=lambda p: (priority.get(p["name"], 99), p["name"]))

    return results


def format_tuning_reference(endpoint_type: str, role: str = "") -> str:
    """
    Build a Markdown tuning reference block for prompt injection.

    Args:
        endpoint_type: Detected endpoint type (e.g. "sybase", "oracle")
        role: Optional filter — "SOURCE" or "TARGET". If empty, show all.

    Returns:
        Markdown string ready for prompt injection, or empty string if no params found.
    """
    params = get_endpoint_tuning_params(endpoint_type)
    if not params:
        return ""

    if role:
        role_upper = role.upper()
        params = [p for p in params if not p["role"] or p["role"].upper() == role_upper]

    if not params:
        return ""

    title = endpoint_type.replace("_", " ").title()
    lines = [
        f"## Tuning Reference -- {title} Endpoint Parameters\n",
        "Use these **exact parameter names** (set via endpoint Advanced tab, Internal parameters):\n",
        "| Parameter | UI Name | Default | Scope |",
        "|---|---|---|---|",
    ]

    for p in params:
        scope = p["role"] if p["role"] else "Both"
        lines.append(f"| `{p['name']}` | {p['ui_name']} | {p['default_value']} | {scope} |")

    lines.append(
        "\n**Typical remediation for timeouts**: Increase `executeTimeout` iteratively "
        "(e.g. double the current value). Verify source DB is not holding locks during "
        "Full Load windows. Set via endpoint Advanced tab > Internal parameters.\n"
    )

    return "\n".join(lines)


def get_available_endpoint_types() -> List[str]:
    """Return all endpoint type names available in ar_props."""
    type_index = _build_type_index()
    return sorted(type_index.keys())
