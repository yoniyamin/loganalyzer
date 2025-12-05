"""
Sitemap discovery for Qlik Community KB articles.
Parses sitemaps to find Qlik Replicate related support articles.
"""
import re
import time
from typing import List, Optional, Set
from xml.etree import ElementTree

import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import (
    QLIK_COMMUNITY_SITEMAP_ROOT,
    KB_URL_PATTERNS,
    REPLICATE_KEYWORDS,
    USER_AGENT,
    REQUEST_TIMEOUT,
    CRAWL_DELAY_SECONDS,
)

console = Console()

# XML namespaces for sitemaps (some sites use namespace, some don't)
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def fetch_sitemap(url: str) -> Optional[str]:
    """
    Fetch sitemap XML content from URL.
    
    Args:
        url: Sitemap URL to fetch
        
    Returns:
        XML content as string, or None if fetch failed
    """
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        console.print(f"[yellow]Warning: Failed to fetch {url}: {e}[/yellow]")
        return None


def parse_sitemap_index(xml_content: str) -> List[str]:
    """
    Parse a sitemap index to extract child sitemap URLs.
    Handles both namespaced and non-namespaced XML.
    
    Args:
        xml_content: XML content of sitemap index
        
    Returns:
        List of child sitemap URLs
    """
    sitemap_urls = []
    try:
        root = ElementTree.fromstring(xml_content)
        
        # Try with namespace first
        for sitemap in root.findall(".//sm:sitemap", SITEMAP_NS):
            loc = sitemap.find("sm:loc", SITEMAP_NS)
            if loc is not None and loc.text:
                sitemap_urls.append(loc.text.strip())
        
        # Try without namespace if none found
        if not sitemap_urls:
            # Remove namespace from tags for easier parsing
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}', 1)[1]
            
            for sitemap in root.findall(".//sitemap"):
                loc = sitemap.find("loc")
                if loc is not None and loc.text:
                    sitemap_urls.append(loc.text.strip())
                    
    except ElementTree.ParseError as e:
        console.print(f"[red]Error parsing sitemap index: {e}[/red]")
    
    return sitemap_urls


def parse_sitemap_urls(xml_content: str) -> List[dict]:
    """
    Parse a sitemap to extract article URLs with metadata.
    Handles both namespaced and non-namespaced XML.
    
    Args:
        xml_content: XML content of sitemap
        
    Returns:
        List of dicts with 'url' and 'lastmod' keys
    """
    articles = []
    try:
        root = ElementTree.fromstring(xml_content)
        
        # Try with namespace first
        for url_elem in root.findall(".//sm:url", SITEMAP_NS):
            loc = url_elem.find("sm:loc", SITEMAP_NS)
            lastmod = url_elem.find("sm:lastmod", SITEMAP_NS)
            
            if loc is not None and loc.text:
                articles.append({
                    "url": loc.text.strip(),
                    "lastmod": lastmod.text.strip() if lastmod is not None and lastmod.text else None
                })
        
        # Try without namespace if none found
        if not articles:
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}', 1)[1]
            
            for url_elem in root.findall(".//url"):
                loc = url_elem.find("loc")
                lastmod = url_elem.find("lastmod")
                
                if loc is not None and loc.text:
                    articles.append({
                        "url": loc.text.strip(),
                        "lastmod": lastmod.text.strip() if lastmod is not None and lastmod.text else None
                    })
                    
    except ElementTree.ParseError as e:
        console.print(f"[red]Error parsing sitemap: {e}[/red]")
    
    return articles


def is_kb_article_url(url: str) -> bool:
    """
    Check if URL matches KB article patterns.
    
    Args:
        url: URL to check
        
    Returns:
        True if URL is a KB article
    """
    return any(pattern in url for pattern in KB_URL_PATTERNS)


def is_replicate_related(url: str) -> bool:
    """
    Check if URL appears to be related to Qlik Replicate.
    
    Args:
        url: URL to check
        
    Returns:
        True if URL contains Replicate-related keywords
    """
    url_lower = url.lower()
    return any(keyword in url_lower for keyword in REPLICATE_KEYWORDS)


def discover_kb_articles(
    filter_replicate_only: bool = True,
    show_progress: bool = True,
    debug: bool = False
) -> List[dict]:
    """
    Discover all Qlik Replicate KB articles from sitemaps.
    
    Args:
        filter_replicate_only: If True, only return Replicate-related articles
        show_progress: If True, show progress indicators
        debug: If True, show detailed debug info
        
    Returns:
        List of article dicts with 'url' and 'lastmod' keys
    """
    all_articles: List[dict] = []
    seen_urls: Set[str] = set()
    
    if show_progress:
        console.print("[blue]Fetching root sitemap...[/blue]")
    
    # Fetch root sitemap
    root_xml = fetch_sitemap(QLIK_COMMUNITY_SITEMAP_ROOT)
    if not root_xml:
        console.print("[red]Failed to fetch root sitemap[/red]")
        return []
    
    if debug:
        console.print(f"[dim]Root sitemap length: {len(root_xml)} bytes[/dim]")
        console.print(f"[dim]First 500 chars: {root_xml[:500]}[/dim]")
    
    # First check if root sitemap contains URLs directly
    direct_urls = parse_sitemap_urls(root_xml)
    if debug:
        console.print(f"[dim]Direct URLs in root: {len(direct_urls)}[/dim]")
    
    # Parse sitemap index to get child sitemaps
    child_sitemaps = parse_sitemap_index(root_xml)
    
    if show_progress:
        console.print(f"[green]Found {len(child_sitemaps)} child sitemaps[/green]")
    
    if debug and child_sitemaps:
        console.print("[dim]Child sitemaps:[/dim]")
        for s in child_sitemaps[:5]:
            console.print(f"[dim]  - {s}[/dim]")
    
    # Process direct URLs from root sitemap first
    for article in direct_urls:
        url = article["url"]
        if url in seen_urls:
            continue
        
        if is_kb_article_url(url):
            if not filter_replicate_only or is_replicate_related(url):
                seen_urls.add(url)
                all_articles.append(article)
                if debug:
                    console.print(f"[dim]Found KB article: {url}[/dim]")
    
    # Filter to only KB-related sitemaps (optimization)
    kb_sitemaps = [s for s in child_sitemaps if "support" in s.lower() or "article" in s.lower() or "knowledge" in s.lower()]
    
    # If no KB-specific sitemaps found, check all of them
    if not kb_sitemaps:
        kb_sitemaps = child_sitemaps
    
    if show_progress:
        console.print(f"[blue]Scanning {len(kb_sitemaps)} sitemaps for KB articles...[/blue]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        disable=not show_progress
    ) as progress:
        task = progress.add_task("Scanning sitemaps...", total=len(kb_sitemaps))
        
        for sitemap_url in kb_sitemaps:
            progress.update(task, description=f"Scanning: {sitemap_url[:60]}...")
            
            sitemap_xml = fetch_sitemap(sitemap_url)
            if sitemap_xml:
                articles = parse_sitemap_urls(sitemap_xml)
                
                if debug:
                    console.print(f"[dim]  {sitemap_url}: {len(articles)} URLs[/dim]")
                
                for article in articles:
                    url = article["url"]
                    
                    # Skip duplicates
                    if url in seen_urls:
                        continue
                    
                    # Check if it's a KB article
                    if not is_kb_article_url(url):
                        continue
                    
                    # Optionally filter for Replicate-related articles
                    if filter_replicate_only and not is_replicate_related(url):
                        continue
                    
                    seen_urls.add(url)
                    all_articles.append(article)
                    
                    if debug:
                        console.print(f"[dim]Found: {url}[/dim]")
            
            progress.advance(task)
            time.sleep(CRAWL_DELAY_SECONDS / 2)  # Be polite
    
    if show_progress:
        console.print(f"[green]Discovered {len(all_articles)} KB articles[/green]")
    
    return all_articles


def discover_all_kb_articles(show_progress: bool = True) -> List[dict]:
    """
    Discover ALL KB articles (not filtered by Replicate).
    Useful for building a comprehensive KB.
    
    Args:
        show_progress: If True, show progress indicators
        
    Returns:
        List of article dicts with 'url' and 'lastmod' keys
    """
    return discover_kb_articles(filter_replicate_only=False, show_progress=show_progress)


if __name__ == "__main__":
    import sys
    
    # Test discovery with debug mode
    debug_mode = "--debug" in sys.argv
    filter_replicate = "--all" not in sys.argv
    
    console.print("[bold]Testing sitemap discovery...[/bold]")
    console.print(f"[dim]Debug: {debug_mode}, Filter Replicate only: {filter_replicate}[/dim]")
    
    articles = discover_kb_articles(
        filter_replicate_only=filter_replicate,
        debug=debug_mode
    )
    
    console.print(f"\n[bold green]Found {len(articles)} KB articles[/bold green]")
    
    if articles:
        console.print("\n[bold]Sample articles:[/bold]")
        for article in articles[:10]:
            console.print(f"  - {article['url']}")
    
    # Usage help
    if not articles:
        console.print("\n[yellow]Try running with --debug for more info:[/yellow]")
        console.print("  python sitemap_discovery.py --debug")
        console.print("  python sitemap_discovery.py --debug --all  (include all KB articles)")
