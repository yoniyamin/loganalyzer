"""
KB Article discovery for Qlik Community.

Simple approach:
1. User saves the KB page after clicking "Load more" until all articles are loaded
2. This script parses the saved HTML file to extract all articles
3. Articles are stored with URL, title, article_id, and view count

The page URL: https://community.qlik.com/t5/b-qlik-support-knowledge-base/Qlik+Replicate/pd-p/qlikReplicate
"""
import re
import logging
from typing import List, Optional
from pathlib import Path

from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import (
    REPLICATE_KEYWORDS,
)

# Setup logging
LOG_FILE = Path(__file__).parent / "kb_discovery.log"
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

# The KB listing page
KB_LISTING_URL = "https://community.qlik.com/t5/b-qlik-support-knowledge-base/Qlik+Replicate/pd-p/qlikReplicate"


def parse_saved_html(html_path: str) -> List[dict]:
    """
    Parse a saved HTML file from the Qlik Community KB page.
    
    The user should:
    1. Go to: https://community.qlik.com/t5/b-qlik-support-knowledge-base/Qlik+Replicate/pd-p/qlikReplicate
    2. Click "Load more" until all articles are loaded (921 articles)
    3. Save the page as HTML (Ctrl+S)
    4. Run this function with the saved file path
    
    Args:
        html_path: Path to the saved HTML file
        
    Returns:
        List of article dicts with url, title, article_id, views
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
    
    # "Load more" creates multiple productMessageList divs:
    # - productMessageList (original)
    # - productMessageList_XXXX (each load more click)
    # We need to get rows from ALL these sections, but SKIP "Top Topics"
    
    # Find all "Latest Topics" sections (they have "ProductMessageList" class and 
    # heading text "Latest Topics")
    all_rows = []
    
    # Find all divs with ProductMessageList class
    message_lists = soup.find_all('div', class_='ProductMessageList')
    logger.info(f"Found {len(message_lists)} ProductMessageList sections")
    
    for msg_list in message_lists:
        # Check if this is a "Latest Topics" section (not "Top Topics")
        # Look for the heading
        parent = msg_list.find_parent('div', class_='lia-panel')
        if parent:
            heading = parent.find('span', class_='lia-panel-heading-bar-title')
            if heading:
                heading_text = heading.get_text(strip=True)
                # Skip "Top Topics" and "My Topics" sections
                if heading_text in ['Top Topics', 'My Topics', 'Latest Replies']:
                    logger.debug(f"Skipping section: {heading_text}")
                    continue
        
        # Get rows from this section
        rows = msg_list.find_all('tr', class_=re.compile(r'lia-list-row'))
        all_rows.extend(rows)
        logger.debug(f"Added {len(rows)} rows from section")
    
    rows = all_rows
    logger.info(f"Found {len(rows)} total rows in Latest Topics sections")
    
    for row in rows:
        # Find article link
        # <a class="page-link lia-link-navigation lia-custom-event" href="/t5/Official-Support-Articles/...">
        link = row.find('a', class_=re.compile(r'page-link.*lia-link-navigation'))
        
        if not link:
            continue
        
        href = link.get('href', '')
        title = link.get_text(strip=True)
        
        # Skip if not an article link
        if '/ta-p/' not in href:
            continue
        
        # Skip empty or short titles
        if not title or len(title) < 5:
            continue
        
        # Build full URL
        if href.startswith('/'):
            full_url = BASE_URL + href
        elif href.startswith('http'):
            full_url = href
        else:
            continue
        
        # Clean URL (remove query params, fragments)
        full_url = full_url.split('?')[0].split('#')[0]
        
        # Skip duplicates
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)
        
        # Extract article ID from URL
        match = re.search(r'/ta-p/(\d+)', href)
        article_id = match.group(1) if match else None
        
        # Find view count
        # <td class="cViewsCountColumn ..."><span class="lia-message-stats-count">28</span>
        views = 0
        views_cell = row.find('td', class_=re.compile(r'cViewsCountColumn'))
        if views_cell:
            views_span = views_cell.find('span', class_='lia-message-stats-count')
            if views_span:
                try:
                    views = int(views_span.get_text(strip=True).replace(',', ''))
                except ValueError:
                    pass
        
        articles.append({
            "url": full_url,
            "title": title,
            "article_id": article_id,
            "views": views,
        })
    
    logger.info(f"Extracted {len(articles)} unique articles")
    
    # Sort by views (highest first) for better retrieval priority
    articles.sort(key=lambda x: x.get("views", 0), reverse=True)
    
    return articles


def discover_kb_articles(
    html_path: Optional[str] = None,
    show_progress: bool = True,
) -> List[dict]:
    """
    Discover KB articles from Qlik Community.
    
    Args:
        html_path: Path to saved HTML file. If None, prompts user.
        show_progress: Show progress indicators
        
    Returns:
        List of article dicts with url, title, article_id, views
    """
    if show_progress:
        console.print("[bold]Discovering Qlik Replicate KB articles...[/bold]")
    
    if html_path is None:
        # Look for default file locations
        default_paths = [
            Path(__file__).parent / "kb_page.html",
            Path(__file__).parent.parent / "kb_page.html",
            Path.home() / "Downloads" / "qlikcommunityscrape" / "debug_page.html",
        ]
        
        for path in default_paths:
            if path.exists():
                html_path = str(path)
                if show_progress:
                    console.print(f"[dim]Found saved HTML: {html_path}[/dim]")
                break
        
        if html_path is None:
            console.print("[yellow]No saved HTML file found.[/yellow]")
            console.print("\n[bold]To scrape KB articles:[/bold]")
            console.print(f"1. Open: {KB_LISTING_URL}")
            console.print("2. Click 'Load more' until all ~921 articles are loaded")
            console.print("3. Save the page (Ctrl+S) as 'kb_page.html' in the kb-assistant folder")
            console.print("4. Run this script again")
            return []
    
    articles = parse_saved_html(html_path)
    
    if show_progress:
        if articles:
            console.print(f"[green]Found {len(articles)} articles (sorted by views)[/green]")
        else:
            console.print("[yellow]No articles found in the HTML file.[/yellow]")
    
    return articles


def discover_all_kb_articles(show_progress: bool = True) -> List[dict]:
    """
    Discover all KB articles (same as discover_kb_articles for this implementation).
    """
    return discover_kb_articles(show_progress=show_progress)


if __name__ == "__main__":
    import sys
    
    console.print("[bold]KB Article Parser[/bold]\n")
    
    # Check for HTML file argument
    html_path = None
    if len(sys.argv) > 1:
        html_path = sys.argv[1]
    
    articles = discover_kb_articles(html_path=html_path, show_progress=True)
    
    if articles:
        console.print(f"\n[bold]Top 15 articles by views:[/bold]")
        for i, article in enumerate(articles[:15], 1):
            title = article['title'][:50] + "..." if len(article['title']) > 50 else article['title']
            views = article.get('views', 0)
            console.print(f"  {i:>2}. [{article.get('article_id', '?'):>7}] ({views:>6} views) {title}")
        
        if len(articles) > 15:
            console.print(f"\n  ... and {len(articles) - 15} more articles")
        
        # Show stats
        total_views = sum(a.get('views', 0) for a in articles)
        avg_views = total_views // len(articles) if articles else 0
        console.print(f"\n[dim]Total views: {total_views:,} | Average: {avg_views:,} views/article[/dim]")
    else:
        console.print("\n[yellow]Instructions:[/yellow]")
        console.print(f"1. Open: {KB_LISTING_URL}")
        console.print("2. Click 'Load more' until all articles are loaded")
        console.print("3. Save the page as HTML")
        console.print("4. Run: python kb_discovery.py <path_to_saved.html>")
