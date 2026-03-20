"""
Release Notes discovery for Qlik Community.

Same manual-save approach as kb_discovery.py since the Qlik Community site
is JS-rendered and can't be scraped with simple HTTP requests.

Steps:
1. User opens: https://community.qlik.com/t5/b-ReleaseNotes/Qlik+Replicate/pd-p/qlikReplicate
2. Saves the page (Ctrl+S) as 'release_notes_page.html' in kb-assistant/
3. This module parses the saved HTML to extract release note article links
"""
import re
import logging
from typing import List, Optional
from pathlib import Path

from bs4 import BeautifulSoup
from rich.console import Console

LOG_FILE = Path(__file__).parent / "release_notes_discovery.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

console = Console()

BASE_URL = "https://community.qlik.com"

RELEASE_NOTES_LISTING_URL = (
    "https://community.qlik.com/t5/b-ReleaseNotes/Qlik+Replicate/pd-p/qlikReplicate"
)


def parse_saved_html(html_path: str) -> List[dict]:
    """
    Parse a saved HTML file from the Qlik Community Release Notes page.

    Args:
        html_path: Path to the saved HTML file

    Returns:
        List of release note dicts with url, title, article_id, views, version
    """
    html_file = Path(html_path)
    if not html_file.exists():
        logger.error(f"HTML file not found: {html_path}")
        return []

    logger.info(f"Parsing HTML file: {html_path}")
    html = html_file.read_text(encoding='utf-8')
    logger.info(f"Read {len(html):,} bytes")

    try:
        soup = BeautifulSoup(html, 'lxml')
    except Exception:
        soup = BeautifulSoup(html, 'html.parser')

    articles = []
    seen_urls = set()

    all_rows = []

    message_lists = soup.find_all('div', class_='ProductMessageList')
    logger.info(f"Found {len(message_lists)} ProductMessageList sections")

    for msg_list in message_lists:
        parent = msg_list.find_parent('div', class_='lia-panel')
        if parent:
            heading = parent.find('span', class_='lia-panel-heading-bar-title')
            if heading:
                heading_text = heading.get_text(strip=True)
                if heading_text in ['Top Topics', 'My Topics', 'Latest Replies']:
                    logger.debug(f"Skipping section: {heading_text}")
                    continue

        rows = msg_list.find_all('tr', class_=re.compile(r'lia-list-row'))
        all_rows.extend(rows)

    rows = all_rows
    logger.info(f"Found {len(rows)} total rows")

    for row in rows:
        link = row.find('a', class_=re.compile(r'page-link.*lia-link-navigation'))
        if not link:
            continue

        href = link.get('href', '')
        title = link.get_text(strip=True)

        if '/ta-p/' not in href:
            continue
        if not title or len(title) < 5:
            continue

        if href.startswith('/'):
            full_url = BASE_URL + href
        elif href.startswith('http'):
            full_url = href
        else:
            continue

        full_url = full_url.split('?')[0].split('#')[0]
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        match = re.search(r'/ta-p/(\d+)', href)
        article_id = match.group(1) if match else None

        views = 0
        views_cell = row.find('td', class_=re.compile(r'cViewsCountColumn'))
        if views_cell:
            views_span = views_cell.find('span', class_='lia-message-stats-count')
            if views_span:
                try:
                    views = int(views_span.get_text(strip=True).replace(',', ''))
                except ValueError:
                    pass

        version = _extract_version_from_title(title)

        articles.append({
            "url": full_url,
            "title": title,
            "article_id": article_id,
            "views": views,
            "version": version,
        })

    logger.info(f"Extracted {len(articles)} unique release note articles")
    articles.sort(key=lambda x: x.get("views", 0), reverse=True)
    return articles


def _extract_version_from_title(title: str) -> str:
    """
    Extract a Qlik Replicate version identifier from the release note title.

    Examples:
        "Qlik Replicate - November 2025 ..." -> "November 2025"
        "Qlik Replicate May 2024 ..."        -> "May 2024"
    """
    match = re.search(
        r'(?:January|February|March|April|May|June|July|August|September|'
        r'October|November|December)\s+\d{4}',
        title, re.IGNORECASE
    )
    return match.group(0) if match else ""


def discover_release_notes(
    html_path: Optional[str] = None,
    show_progress: bool = True,
) -> List[dict]:
    """
    Discover release note articles from a saved HTML file.

    Args:
        html_path: Path to saved HTML file. If None, looks for defaults.
        show_progress: Show progress indicators

    Returns:
        List of article dicts
    """
    if show_progress:
        console.print("[bold]Discovering Qlik Replicate release notes...[/bold]")

    if html_path is None:
        default_paths = [
            Path(__file__).parent / "release_notes_page.html",
            Path(__file__).parent.parent / "release_notes_page.html",
        ]

        for path in default_paths:
            if path.exists():
                html_path = str(path)
                if show_progress:
                    console.print(f"[dim]Found saved HTML: {html_path}[/dim]")
                break

        if html_path is None:
            console.print("[yellow]No saved HTML file found.[/yellow]")
            console.print("\n[bold]To index release notes:[/bold]")
            console.print(f"1. Open: {RELEASE_NOTES_LISTING_URL}")
            console.print("2. Save the page (Ctrl+S) as 'release_notes_page.html' in the kb-assistant folder")
            console.print("3. Run this script again")
            return []

    articles = parse_saved_html(html_path)

    if show_progress:
        if articles:
            console.print(f"[green]Found {len(articles)} release note articles[/green]")
        else:
            console.print("[yellow]No articles found in the HTML file.[/yellow]")

    return articles


if __name__ == "__main__":
    import sys

    console.print("[bold]Release Notes Article Parser[/bold]\n")

    html_path = None
    if len(sys.argv) > 1:
        html_path = sys.argv[1]

    articles = discover_release_notes(html_path=html_path, show_progress=True)

    if articles:
        console.print(f"\n[bold]Release notes found:[/bold]")
        for i, article in enumerate(articles, 1):
            title = article['title'][:70] + "..." if len(article['title']) > 70 else article['title']
            version = article.get('version', '')
            console.print(f"  {i:>2}. [{version:>15}] {title}")
