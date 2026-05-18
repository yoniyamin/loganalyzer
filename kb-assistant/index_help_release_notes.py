#!/usr/bin/env python3
"""
Qlik Replicate release notes indexer.

Fetches from two sources:
1. help.qlik.com - features/what's new pages (static, always accessible)
2. community.qlik.com - resolved issues with RECOB fix IDs (requires browser headers)

Both are indexed into the same ChromaDB collection.
"""
import sys
import hashlib
import re
import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from backend.release_notes_eol import parse_eol_entries_from_release_note_text

sys.path.insert(0, str(Path(__file__).parent))

from config import CHROMA_PERSIST_DIR
from release_notes_loader import embed_release_note, _get_rn_collection, show_stats
from release_notes_fetcher import _extract_endpoint_types

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# --- Source 1: help.qlik.com (features pages) ---
HELP_VERSIONS = [
    "November2025", "May2025", "November2024", "May2024",
    "November2023", "May2023", "November2022", "May2022", "November2021",
]
HELP_BASE = "https://help.qlik.com/en-US/replicate/{version}/Content/Replicate/Main/Release_Notes/features.htm"

# --- Source 2: community.qlik.com (resolved issues with RECOB IDs) ---
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
SIMPLE_HEADERS = {"User-Agent": "QlikReplicateLogAnalyzer/1.0"}


def fetch_page(url: str, headers: dict | None = None) -> str | None:
    try:
        r = requests.get(url, headers=headers or SIMPLE_HEADERS, timeout=25)
        if r.status_code == 200 and len(r.text) > 500:
            return r.text
    except Exception as e:
        logger.debug(f"Failed to fetch {url}: {e}")
    return None


# ---------- help.qlik.com parser ----------

def parse_help_page(html: str, url: str, version: str) -> dict | None:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")

    main = soup.find("main") or soup.find("div", class_="body-container") or soup.find("body")
    if not main:
        return None

    for tag in main.find_all(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    text = main.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)

    if len(text) < 200:
        return None
    if "this page has been archived" in text.lower():
        return None

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else f"Qlik Replicate {version}"
    title = re.sub(r"\s*\|.*$", "", title)
    if title.lower() in ("start", ""):
        return None

    version_clean = re.sub(r"(\w+?)(\d{4})", r"\1 \2", version)

    return {
        "url": url,
        "article_id": f"help_{version}_features",
        "title": title,
        "content": text,
        "content_hash": hashlib.md5(text.encode()).hexdigest()[:12],
        "content_length": len(text),
        "version": version_clean,
        "fix_ids": re.findall(r"RECOB-\d+", text),
        "endpoint_types": _extract_endpoint_types(text),
    }


# ---------- community.qlik.com parser ----------

def _extract_version_from_title(title: str) -> str:
    m = re.search(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{4}",
        title, re.IGNORECASE,
    )
    return m.group(0) if m else ""


def parse_community_page(html: str, url: str) -> dict | None:
    """Parse a Qlik Community release notes page to extract resolved issues."""
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

    # Extract title
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
    title = title or "Qlik Replicate Release Notes"

    version = _extract_version_from_title(title)
    fix_ids = list(dict.fromkeys(re.findall(r"RECOB-\d+", raw_text)))
    endpoint_types = _extract_endpoint_types(raw_text)
    article_id_m = re.search(r"/ta-p/(\d+)", url)
    article_id = article_id_m.group(1) if article_id_m else ""

    return {
        "url": url,
        "article_id": article_id,
        "title": title,
        "content": raw_text,
        "content_hash": hashlib.md5(raw_text.encode()).hexdigest()[:12],
        "content_length": len(raw_text),
        "version": version,
        "fix_ids": fix_ids,
        "endpoint_types": endpoint_types,
    }


# ---------- RECOB / EOL parsers (same logic as backend) ----------

def _parse_recob_entries(text: str) -> list[dict]:
    """Parse individual RECOB fix entries from community release notes text."""
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
    return parse_eol_entries_from_release_note_text(text, task_endpoint_keys=None)


def _build_json_cache(all_articles: list[dict]):
    """Build a pre-parsed JSON cache file for the API to consume.

    Avoids any ChromaDB access at runtime.
    """
    import json

    cache_dir = Path(__file__).resolve().parent.parent / "data"
    cache_dir.mkdir(exist_ok=True)
    cache_path = cache_dir / "release_notes_cache.json"

    entries = []
    eol_entries = []
    seen_fix_ids: set[str] = set()

    for article in all_articles:
        ver = article.get("version", "")
        url = article.get("url", "")
        content = article.get("content", "")

        for recob in _parse_recob_entries(content):
            fid = recob["fix_id"]
            if fid in seen_fix_ids:
                continue
            seen_fix_ids.add(fid)
            recob["version"] = ver
            recob["url"] = url
            entries.append(recob)

        for eol in _parse_eol_entries(content):
            eol["version"] = ver
            eol["url"] = url
            eol_entries.append(eol)

    cache = {
        "total_entries": len(entries),
        "total_eol": len(eol_entries),
        "entries": entries,
        "eol_entries": eol_entries,
    }

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    logger.info(f"JSON cache written: {cache_path} ({len(entries)} RECOB, {len(eol_entries)} EOL)")


# ---------- main ----------

def main():
    total_chunks = 0
    indexed = 0
    all_articles: list[dict] = []

    collection = _get_rn_collection()
    logger.info(f"Current collection has {collection.count()} chunks")

    # Phase 1: help.qlik.com features pages
    logger.info("\n=== Phase 1: help.qlik.com (features) ===")
    for version in HELP_VERSIONS:
        url = HELP_BASE.format(version=version)
        logger.info(f"Fetching {version} features...")
        html = fetch_page(url)
        if not html:
            logger.warning(f"  Skipped: {url}")
            continue
        article = parse_help_page(html, url, version)
        if not article:
            logger.warning(f"  Skipped (no content)")
            continue
        all_articles.append(article)
        chunks = embed_release_note(article)
        if chunks > 0:
            total_chunks += chunks
            indexed += 1
            logger.info(f"  OK: {article['title'][:55]} ({chunks} chunks, {len(article['endpoint_types'])} endpoints)")

    # Phase 2: community.qlik.com resolved issues (RECOB IDs)
    logger.info("\n=== Phase 2: community.qlik.com (resolved issues) ===")
    for url in COMMUNITY_URLS:
        logger.info(f"Fetching {url.split('/')[-2][:50]}...")
        html = fetch_page(url, headers=BROWSER_HEADERS)
        if not html:
            logger.warning(f"  Skipped (403/timeout): {url}")
            continue
        article = parse_community_page(html, url)
        if not article:
            logger.warning(f"  Skipped (parse failed)")
            continue
        all_articles.append(article)
        chunks = embed_release_note(article)
        if chunks > 0:
            total_chunks += chunks
            indexed += 1
            logger.info(
                f"  OK: {article['version'] or 'Unknown'} - "
                f"{chunks} chunks, {len(article['fix_ids'])} RECOB IDs, "
                f"{len(article['endpoint_types'])} endpoints"
            )

    logger.info(f"\nDone! Indexed {indexed} pages, {total_chunks} total chunks.")
    show_stats()

    # Build JSON cache for fast API access (no ChromaDB at runtime)
    _build_json_cache(all_articles)


if __name__ == "__main__":
    main()
