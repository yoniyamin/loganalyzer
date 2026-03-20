"""
Release notes fetcher for Qlik Community.

Fetches, parses, and structures release note content. Release notes
have a different HTML structure than KB articles: they contain fix
lists with RECOB IDs and endpoint-specific sections.
"""
import hashlib
import re
import logging
from typing import Optional, Dict, Any, List

from bs4 import BeautifulSoup
from rich.console import Console

from article_fetcher import fetch_article_html, clean_text

logger = logging.getLogger('kb_loader.release_notes_fetcher')
console = Console()


def parse_release_note_html(html: str, url: str) -> Optional[Dict[str, Any]]:
    """
    Parse a release note page to extract structured fix/feature content.

    Returns a dict with the full text content plus extracted fix entries
    and endpoint types mentioned.
    """
    try:
        soup = BeautifulSoup(html, 'lxml')
    except Exception:
        soup = BeautifulSoup(html, 'html.parser')

    content_elem = None
    for selector in [
        '.lia-message-body-content',
        '.lia-message-body',
        '.lia-tkb-article-body-content',
        '.lia-tkb-body',
        '.MessageBody',
        '.message-body-content',
    ]:
        content_elem = soup.select_one(selector)
        if content_elem and len(content_elem.get_text(strip=True)) > 100:
            break

    if not content_elem:
        logger.warning(f"No content found for release note: {url}")
        return None

    raw_text = content_elem.get_text(separator='\n', strip=True)
    raw_text = clean_text(raw_text)

    if len(raw_text) < 100:
        logger.warning(f"Content too short ({len(raw_text)} chars) for {url}")
        return None

    title = None
    for sel in [
        'h1.lia-message-subject',
        'h2.lia-message-subject',
        '.page-header h1',
    ]:
        elem = soup.select_one(sel)
        if elem:
            title = elem.get_text(strip=True)
            break
    if not title:
        title_elem = soup.find('title')
        if title_elem:
            title = re.sub(r'\s*[-|]\s*Qlik Community.*$', '', title_elem.get_text(strip=True))
    title = title or "Untitled Release Note"

    fix_ids = re.findall(r'RECOB-\d+', raw_text)

    endpoint_types = _extract_endpoint_types(raw_text)

    article_id_match = re.search(r'/ta-p/(\d+)', url)
    article_id = article_id_match.group(1) if article_id_match else None

    version_match = re.search(
        r'(?:January|February|March|April|May|June|July|August|September|'
        r'October|November|December)\s+\d{4}',
        title, re.IGNORECASE
    )
    version = version_match.group(0) if version_match else ""

    content_hash = hashlib.md5(raw_text.encode()).hexdigest()[:12]

    return {
        "url": url,
        "article_id": article_id,
        "title": title,
        "content": raw_text,
        "content_hash": content_hash,
        "content_length": len(raw_text),
        "version": version,
        "fix_ids": fix_ids,
        "endpoint_types": endpoint_types,
    }


# Comprehensive list of Qlik Replicate endpoint names
_ENDPOINT_NAMES = [
    "Oracle", "SQL Server", "Microsoft SQL Server", "MySQL", "PostgreSQL",
    "IBM DB2", "DB2", "SAP HANA", "SAP ASE", "Sybase",
    "Snowflake", "Amazon Redshift", "Redshift", "Google BigQuery", "BigQuery",
    "Azure Synapse", "Azure SQL", "Databricks", "Amazon S3", "S3",
    "Azure Data Lake", "ADLS", "Google Cloud Storage", "GCS",
    "Kafka", "Amazon Kinesis", "Kinesis", "HDFS", "Hadoop",
    "Teradata", "Informix", "MongoDB", "Cassandra",
    "Amazon RDS", "RDS", "Amazon Aurora", "Aurora",
    "File Channel", "Flat File",
    "IBM iSeries", "AS/400", "Mainframe",
    "HP NonStop", "NonStop",
    "SAP Application", "SAP",
]

_ENDPOINT_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(e) for e in sorted(_ENDPOINT_NAMES, key=len, reverse=True)) + r')\b',
    re.IGNORECASE
)


def _extract_endpoint_types(text: str) -> List[str]:
    """Extract unique endpoint type names mentioned in text."""
    matches = _ENDPOINT_PATTERN.findall(text)
    seen = set()
    unique = []
    for m in matches:
        key = m.lower()
        if key not in seen:
            seen.add(key)
            unique.append(m)
    return unique


def fetch_and_parse_release_note(url: str) -> Optional[Dict[str, Any]]:
    """
    Fetch and parse a single release note article.

    Args:
        url: Release note URL

    Returns:
        Release note data dict or None
    """
    logger.debug(f"Fetching release note: {url}")
    html = fetch_article_html(url)
    if not html:
        logger.warning(f"No HTML returned for {url}")
        return None

    result = parse_release_note_html(html, url)
    if result:
        logger.debug(
            f"Parsed OK: title='{result['title'][:50]}', "
            f"fixes={len(result['fix_ids'])}, endpoints={result['endpoint_types']}"
        )
    else:
        logger.warning(f"Parse failed for {url}")
    return result
