"""
Article fetcher for Qlik Community KB articles.
Fetches, parses, and cleans HTML content from KB article URLs.
"""
import hashlib
import re
import time
import logging
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

# Setup logging
logger = logging.getLogger('kb_loader.article_fetcher')

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
            logger.debug(f"Fetching URL (attempt {attempt+1}/{retries}): {url}")
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
            logger.debug(f"Fetch OK: {len(response.text)} bytes, status {response.status_code}")
            return response.text
        except requests.Timeout as e:
            logger.warning(f"Timeout fetching {url} (attempt {attempt+1}): {e}")
            if attempt < retries - 1:
                wait_time = 2 ** attempt
                logger.debug(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
        except requests.HTTPError as e:
            logger.warning(f"HTTP error {response.status_code} fetching {url}: {e}")
            if response.status_code == 429:  # Rate limited
                wait_time = 30 + (10 * attempt)  # Longer wait for rate limits
                logger.warning(f"Rate limited! Waiting {wait_time}s...")
                time.sleep(wait_time)
            elif response.status_code >= 500:  # Server error
                if attempt < retries - 1:
                    wait_time = 5 * (attempt + 1)
                    logger.debug(f"Server error, waiting {wait_time}s...")
                    time.sleep(wait_time)
            else:
                logger.error(f"Non-retryable HTTP error {response.status_code} for {url}")
                return None
        except requests.RequestException as e:
            logger.warning(f"Request error fetching {url} (attempt {attempt+1}): {e}")
            if attempt < retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
            else:
                logger.error(f"All retries failed for {url}: {e}")
                return None
    
    logger.error(f"All {retries} attempts failed for {url}")
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
    
    # Remove common boilerplate phrases (non-greedy, limited scope)
    boilerplate = [
        r'Was this article helpful\?\s*(Yes|No)?\s*(Yes|No)?',
        r'Labels:\s*[\w\s,]+(?=\s{2}|$)',
        r'Tags:\s*[\w\s,]+(?=\s{2}|$)',
        r'Share this article',
        r'Print this article',
        r'Email this article',
        r'Mark as New',
        r'Bookmark',
        r'Subscribe',
        r'Mute',
        r'Subscribe to RSS Feed',
        r'Permalink',
        r'Print',
        r'Report Inappropriate Content',
    ]
    for pattern in boilerplate:
        text = re.sub(pattern, ' ', text, flags=re.IGNORECASE)
    
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
    
    # IMPORTANT: Extract content FIRST before decomposing any elements
    # This prevents accidentally removing parent containers
    
    # Extract main content - try multiple selectors for article body
    content = None
    content_selectors = [
        # Primary content selectors (most specific first)
        '.lia-message-body-content',
        '.lia-message-body',
        '.lia-tkb-article-body-content',
        '.lia-tkb-body',
        '.MessageBody',
        '.message-body-content',
    ]
    
    for selector in content_selectors:
        content_elem = soup.select_one(selector)
        if content_elem:
            content = content_elem.get_text(separator=' ', strip=True)
            logger.debug(f"Selector '{selector}' found {len(content)} chars")
            if len(content) > 100:
                break
    
    # Try finding div with specific class patterns if still not found
    if not content or len(content) < 100:
        for div in soup.find_all('div', class_=True):
            classes = ' '.join(div.get('class', []))
            if any(x in classes.lower() for x in ['message-body', 'body-content']):
                text = div.get_text(separator=' ', strip=True)
                if len(text) > len(content or ''):
                    content = text
                    logger.debug(f"Found content in div.{div.get('class')[0]}: {len(content)} chars")
    
    if not content:
        logger.warning(f"No content found for {url}")
        return None
    
    # Extract title
    title = None
    
    # Try article title selectors
    title_selectors = [
        'h1.lia-message-subject',
        'h2.lia-message-subject',
        '.page-header h1',
        '.lia-tkb-article-subject',
        'h1[itemprop="name"]',
    ]
    
    for selector in title_selectors:
        title_elem = soup.select_one(selector)
        if title_elem:
            title = title_elem.get_text(strip=True)
            break
    
    # Try generic h1/h2 with lia class
    if not title:
        title_elem = soup.find(['h1', 'h2'], class_=re.compile(r'lia-message-subject|page-title|article-title'))
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
    
    # Clean the content
    content = clean_text(content)
    
    # Skip if content is too short (lowered threshold for short articles)
    if len(content) < 100:
        logger.warning(f"Content too short ({len(content)} chars) for {url}")
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
    logger.debug(f"Fetching and parsing: {url}")
    
    html = fetch_article_html(url)
    if not html:
        logger.warning(f"No HTML returned for {url}")
        return None
    
    result = parse_article_html(html, url)
    
    if result:
        logger.debug(f"Parsed OK: title='{result.get('title', '')[:50]}', content={result.get('content_length', 0)} chars")
    else:
        logger.warning(f"Parse failed for {url} (content too short or missing)")
    
    return result


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
