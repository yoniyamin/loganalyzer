#!/usr/bin/env python3
"""
Build a pre-parsed JSON cache of Qlik Replicate release notes.

Fetches community.qlik.com pages, parses RECOB entries and EOL info,
and writes a JSON file that the API reads instantly at runtime.

No ChromaDB or embedding models are needed.
"""

import json
import hashlib
import re
import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

COMMUNITY_URLS = [
    "https://community.qlik.com/t5/Release-Notes/Qlik-Replicate-November-2025-Initial-Release-until-Service/ta-p/2533591",
    "https://community.qlik.com/t5/Release-Notes/Qlik-Replicate-May-2025-Initial-Release-until-Service-Release-1/ta-p/2526880",
    "https://community.qlik.com/t5/Release-Notes/Qlik-Replicate-November-2024-Initial-Release-until-Service/ta-p/2486983",
    "https://community.qlik.com/t5/Release-Notes/Qlik-Replicate-May-2024-Initial-Release-and-Service-Release-1/ta-p/2487023",
    "https://community.qlik.com/t5/Release-Notes/Qlik-Replicate-Release-Notes-November-2023-Initial-Release-until/ta-p/2110765",
    "https://community.qlik.com/t5/Release-Notes/Qlik-Replicate-May-2023-Release-Notes-Initial-Release-until/ta-p/2055251",
    "https://community.qlik.com/t5/Release-Notes/Qlik-Replicate-Release-notes-May-2022-Initial-Release-to-Service/ta-p/1930767",
    "https://community.qlik.com/t5/Release-Notes/Qlik-Replicate-Release-notes-November-2021-Initial-Release-to/ta-p/1980489",
]

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "release_notes_cache.json"


def fetch_page(url: str) -> str | None:
    try:
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=25)
        if r.status_code == 200 and len(r.text) > 500:
            return r.text
    except Exception as e:
        logger.debug(f"Failed: {e}")
    return None


def _extract_version(title: str) -> str:
    m = re.search(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{4}",
        title, re.IGNORECASE,
    )
    return m.group(0) if m else ""


def parse_community_page(html: str, url: str) -> dict | None:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    content_elem = None
    for sel in [".lia-message-body-content", ".lia-message-body",
                ".lia-tkb-article-body-content", ".MessageBody"]:
        content_elem = soup.select_one(sel)
        if content_elem and len(content_elem.get_text(strip=True)) > 200:
            break
    if not content_elem:
        return None

    raw_text = content_elem.get_text(separator="\n", strip=True)
    raw_text = re.sub(r"\n{3,}", "\n\n", raw_text)
    if len(raw_text) < 200:
        return None

    title = ""
    for sel in ["h1.lia-message-subject", "h2.lia-message-subject", ".page-header h1"]:
        el = soup.select_one(sel)
        if el:
            title = el.get_text(strip=True)
            break
    if not title:
        te = soup.find("title")
        if te:
            title = re.sub(r"\s*[-|]\s*Qlik Community.*$", "", te.get_text(strip=True))

    version = _extract_version(title or "")
    return {"url": url, "version": version, "content": raw_text}


def _parse_recob_entries(text: str) -> list[dict]:
    entries = []
    blocks = re.split(r'(?=Jira\s+issue\s*:\s*RECOB-)', text)
    for block in blocks:
        fid_m = re.search(r'Jira\s+issue\s*:\s*(RECOB-\d+(?:\s*,\s*RECOB-\d+)*)', block)
        if not fid_m:
            continue
        fix_id = fid_m.group(1).strip()
        sf_m = re.search(r'Salesforce\s+case\s*:\s*(.+?)(?:\n|$)', block)
        sf_case = sf_m.group(1).strip() if sf_m else ""
        type_m = re.search(r'Type\s*:\s*(.+?)(?:\n|$)', block)
        entry_type = type_m.group(1).strip() if type_m else ""
        comp_m = re.search(r'Component/Process\s*:\s*(.+?)(?:\n|$)', block)
        component = comp_m.group(1).strip() if comp_m else ""
        desc_m = re.search(r'Description\s*:\s*(.+)', block, re.DOTALL)
        description = ""
        if desc_m:
            description = desc_m.group(1).strip()
            description = re.sub(r'\s+', ' ', description)[:300]
        entries.append({
            "fix_id": fix_id,
            "component": component,
            "entry_type": entry_type,
            "description": description,
            "salesforce_case": sf_case,
            "source": "chromadb",
        })
    return entries


def _parse_eol_entries(text: str) -> list[dict]:
    entries = []
    lines = text.split('\n')
    capture = False
    section_count = 0
    for line in lines:
        lower = line.lower().strip()
        if any(kw in lower for kw in ("has been discontinued", "no longer supported", "end of support")):
            capture = True
            section_count = 0
            continue
        if capture:
            if not lower or lower.startswith(("resolved", "known", "downloads", "what", "migration")):
                capture = False
                continue
            if section_count >= 20:
                capture = False
                continue
            stripped = line.strip()
            if len(stripped) > 3:
                section_count += 1
                entries.append({
                    "entry_type": "End of Support",
                    "description": stripped,
                    "component": "",
                    "fix_id": "",
                    "salesforce_case": "",
                    "source": "chromadb",
                })
    return entries


def main():
    CACHE_PATH.parent.mkdir(exist_ok=True)

    all_entries: list[dict] = []
    eol_entries: list[dict] = []
    seen_fix_ids: set[str] = set()

    for url in COMMUNITY_URLS:
        short_name = url.split("/")[-2][:50]
        logger.info(f"Fetching {short_name}...")
        html = fetch_page(url)
        if not html:
            logger.warning(f"  Skipped (403/timeout)")
            continue

        article = parse_community_page(html, url)
        if not article:
            logger.warning(f"  Skipped (parse failed)")
            continue

        ver = article["version"]
        logger.info(f"  Version: {ver}")

        for recob in _parse_recob_entries(article["content"]):
            fid = recob["fix_id"]
            if fid in seen_fix_ids:
                continue
            seen_fix_ids.add(fid)
            recob["version"] = ver
            recob["url"] = url
            all_entries.append(recob)

        for eol in _parse_eol_entries(article["content"]):
            eol["version"] = ver
            eol["url"] = url
            eol_entries.append(eol)

        logger.info(f"  Parsed {len(all_entries)} total RECOB, {len(eol_entries)} EOL so far")

    cache = {
        "total_entries": len(all_entries),
        "total_eol": len(eol_entries),
        "entries": all_entries,
        "eol_entries": eol_entries,
    }

    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    logger.info(f"\nDone! Wrote {CACHE_PATH}")
    logger.info(f"  {len(all_entries)} RECOB entries, {len(eol_entries)} EOL entries")


if __name__ == "__main__":
    main()
