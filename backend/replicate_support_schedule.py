"""Qlik Replicate release vs. product-level end-of-support dates (marketing schedule)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional

# Rows: Product name label, GA / release milestone, formal support end
_SCHEDULE_ROWS: List[tuple[str, str, str]] = [
    ("Qlik Replicate November 2025", "November 17, 2025", "November 17, 2027"),
    ("Qlik Replicate May 2025", "May 14, 2025", "May 13, 2027"),
    ("Qlik Replicate November 2024", "November 13, 2024", "November 11, 2026"),
    ("Qlik Replicate May 2024", "May 16, 2024", "May 15, 2026"),
    ("Qlik Replicate November 2023", "November 14, 2023", "November 13, 2025"),
    ("Qlik Replicate May 2023", "May 9, 2023", "May 9, 2025"),
    ("Qlik Replicate November 2022", "November 8, 2022", "November 8, 2024"),
    ("Qlik Replicate May 2022", "May 10, 2022", "May 10, 2024"),
    ("Qlik Replicate November 2021", "November 8, 2021", "November 8, 2023"),
    ("Qlik Replicate May 2021", "May 11, 2021", "May 11, 2023"),
    ("Qlik Replicate November 2020", "November 10, 2020", "November 30, 2022"),
    ("Qlik Replicate April 2020 (6.6)", "April 16, 2020", "April 30, 2022"),
    ("Qlik Replicate 6.5", "November 14, 2019", "November 30, 2021"),
    ("Qlik Replicate 6.4", "April 1, 2019", "April 14, 2021"),
    ("Qlik Replicate 5.5", "August 1, 2017", "November 30, 2020"),
]

_MONTH_YEAR = re.compile(
    r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ReplicateSupportRow:
    version_label: str
    release_date: str
    support_end_date: str
    release_date_parsed: date
    support_end_date_parsed: date


def _parse_us_date(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s.strip(), "%B %d, %Y").date()
    except ValueError:
        return None


def _load_rows() -> List[ReplicateSupportRow]:
    out: List[ReplicateSupportRow] = []
    for vl, rd, ed in _SCHEDULE_ROWS:
        rdp = _parse_us_date(rd)
        edp = _parse_us_date(ed)
        if rdp is None or edp is None:
            continue
        out.append(ReplicateSupportRow(vl, rd, ed, rdp, edp))
    return out


_PARSED_ROWS = _load_rows()


def _extract_month_year(s: str) -> Optional[tuple[int, str]]:
    m = _MONTH_YEAR.search(s)
    if not m:
        return None
    from calendar import month_name  # local import avoided; use numeric

    mn = m.group(1).lower()
    yr = int(m.group(2))
    months_map = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10,
        "november": 11, "december": 12,
    }
    return months_map.get(mn), str(yr)


def match_replicate_schedule(release_hint: Optional[str]) -> Optional[ReplicateSupportRow]:
    """Match ``May 2023``-style hints from logs or full product labels."""
    if not release_hint:
        return None
    raw = release_hint.strip()
    if not raw:
        return None
    nl = raw.lower()

    my = _extract_month_year(raw)
    if my:
        nm, ys = my
        for row in _PARSED_ROWS:
            ry = _extract_month_year(row.version_label)
            if ry and ry[0] == nm and ry[1] == ys:
                return row

    # Numbered trains (e.g. 6.6, 6.5)
    ver_m = re.search(r"\b(6\.[456]|5\.5)\b", nl)
    if ver_m:
        token = ver_m.group(1)
        for row in _PARSED_ROWS:
            if token in row.version_label.lower():
                return row

    for row in _PARSED_ROWS:
        vl = row.version_label.lower()
        if nl in vl or vl in nl:
            return row

    return None


def replicate_support_payload(
    release_hint: Optional[str],
    *,
    as_of: Optional[date] = None,
) -> Dict[str, Any]:
    """API-friendly dict for the Release Notes UI."""
    row = match_replicate_schedule(release_hint)
    if not row:
        return {"matched": False}

    reference = as_of if as_of is not None else date.today()
    eos = row.support_end_date_parsed

    return {
        "matched": True,
        "version_label": row.version_label,
        "release_date": row.release_date,
        "support_end_date": row.support_end_date,
        "is_out_of_support": reference > eos,
        "support_ended_iso": eos.isoformat(),
        "reference_date_iso": reference.isoformat(),
    }
