"""
Article fetcher for Qlik Community KB articles.
Fetches, parses, and cleans HTML content from KB article URLs.
"""
import hashlib
import re
import time
from typing import Optional, Dict, Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from rich.console import Console

from config import (
    USER_AGENT,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    CRAWL_DELAY_SECONDS,
)

console = Console()


def extract_article_id(url: str) -> Optional[str]:
    """
    Extract article ID from Qlik Community URL.
    
    Args:
        url: Article URL
        
    Returns:
        Article ID or None
    """
    # Pattern: /ta-p/123456 at end of URL
    match = re.search(r'/ta-p/(\d+)', url)
    if match:
        return match.group(1)
    
    # Pattern: /m-p/123456
    match = re.search(r'/m-p/(\d+)', url)
    if match:
        return match.group(1)
    
    return None


def fetch_article_html(url: str, retries: int = MAX_RETRIES) -> Optional[str]:
    """
    Fetch article HTML with retries.
    
    Args:
        url: Article URL
        retries: Number of retries on failure
        
    Returns:
        HTML content or None
    """
    for attempt in range(retries):
        try:
            response = requests.get(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                console.print(f"[yellow]Failed to fetch {url}: {e}[/yellow]")
                return None
    return None


def clean_text(text: str) -> str:
    """
    Clean extracted text content.
    
    Args:
        text: Raw text content
        
    Returns:
        Cleaned text
    """
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove common boilerplate phrases
    boilerplate = [
        r'Was this article helpful\?.*',
        r'Related Articles.*',
        r'Labels:.*',
        r'Tags:.*',
        r'Share this article.*',
        r'Print this article.*',
        r'Email this article.*',
    ]
    for pattern in boilerplate:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Clean up whitespace again
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def parse_article_html(html: str, url: str) -> Optional[Dict[str, Any]]:
    """
    Parse article HTML to extract content and metadata.
    
    Args:
        html: Raw HTML content
        url: Article URL (for metadata)
        
    Returns:
        Dict with article data or None
    """
    try:
        soup = BeautifulSoup(html, 'lxml')
    except Exception:
        # Fallback to html.parser if lxml fails
        soup = BeautifulSoup(html, 'html.parser')
    
    # Remove unwanted elements
    for element in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 
                                   'aside', 'iframe', 'noscript']):
        element.decompose()
    
    # Remove navigation and sidebar elements
    for selector in ['.lia-menu', '.lia-breadcrumb', '.lia-navigation', 
                     '.lia-component-common-widget-page-header',
                     '.lia-component-common-widget-page-footer',
                     '.lia-quilt-column-side', '.sidebar']:
        for element in soup.select(selector):
            element.decompose()
    
    # Extract title
    title = None
    
    # Try article title first
    title_elem = soup.find('h1', class_=re.compile(r'lia-message-subject|page-title|article-title'))
    if title_elem:
        title = title_elem.get_text(strip=True)
    
    # Fallback to page title
    if not title:
        title_elem = soup.find('title')
        if title_elem:
            title = title_elem.get_text(strip=True)
            # Remove site name suffix
            title = re.sub(r'\s*[-|]\s*Qlik Community.*$', '', title)
    
    if not title:
        title = "Untitled Article"
    
    # Extract main content
    content = None
    
    # Try to find article body
    content_selectors = [
        '.lia-message-body-content',
        '.lia-message-body',
        '.article-body',
        '.message-body',
        'article',
        '.lia-quilt-column-main',
        'main',
    ]
    
    for selector in content_selectors:
        content_elem = soup.select_one(selector)
        if content_elem:
            content = content_elem.get_text(separator=' ', strip=True)
            if len(content) > 100:  # Ensure we have meaningful content
                break
    
    # Fallback to body
    if not content or len(content) < 100:
        body = soup.find('body')
        if body:
            content = body.get_text(separator=' ', strip=True)
    
    if not content:
        return None
    
    # Clean the content
    content = clean_text(content)
    
    # Skip if content is too short
    if len(content) < 200:
        return None
    
    # Extract article ID
    article_id = extract_article_id(url)
    
    # Generate content hash for deduplication
    content_hash = hashlib.md5(content.encode()).hexdigest()[:12]
    
    return {
        "url": url,
        "article_id": article_id,
        "title": title,
        "content": content,
        "content_hash": content_hash,
        "content_length": len(content),
    }


def fetch_and_parse_article(url: str) -> Optional[Dict[str, Any]]:
    """
    Fetch and parse a single article.
    
    Args:
        url: Article URL
        
    Returns:
        Article data dict or None
    """
    html = fetch_article_html(url)
    if not html:
        return None
    
    return parse_article_html(html, url)


def fetch_articles_batch(
    urls: list,
    delay: float = CRAWL_DELAY_SECONDS,
    progress_callback=None
) -> list:
    """
    Fetch multiple articles with delay between requests.
    
    Args:
        urls: List of article URLs
        delay: Delay between requests in seconds
        progress_callback: Optional callback(current, total, article) for progress
        
    Returns:
        List of successfully parsed articles
    """
    articles = []
    
    for i, url in enumerate(urls):
        article = fetch_and_parse_article(url)
        
        if article:
            articles.append(article)
        
        if progress_callback:
            progress_callback(i + 1, len(urls), article)
        
        # Polite delay between requests
        if i < len(urls) - 1:
            time.sleep(delay)
    
    return articles


if __name__ == "__main__":
    # Test with a sample article
    test_url = "https://community.qlik.com/t5/Official-Support-Articles/Qlik-Replicate-How-to-configure-Replicate-to-use-TLS-1-2-for/ta-p/1714978"
    
    console.print(f"[bold]Testing article fetcher with:[/bold]\n{test_url}\n")
    
    article = fetch_and_parse_article(test_url)
    
    if article:
        console.print(f"[green]Title:[/green] {article['title']}")
        console.print(f"[green]Article ID:[/green] {article['article_id']}")
        console.print(f"[green]Content length:[/green] {article['content_length']} chars")
        console.print(f"\n[green]Content preview:[/green]\n{article['content'][:500]}...")
    else:
        console.print("[red]Failed to fetch/parse article[/red]")
