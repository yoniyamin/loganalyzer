#!/usr/bin/env python3
"""
Debug script to analyze the KB listing page HTML structure.
"""

import requests
import re
import logging
from bs4 import BeautifulSoup
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('debug_scraper.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

BASE_URL = "https://community.qlik.com"
KB_URL = "https://community.qlik.com/t5/Official-Support-Articles/tkb-p/qlik-support-knowledge-base/label-name/Qlik%20Replicate"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def fetch_page(url: str) -> str:
    """Fetch a page and return its HTML."""
    logger.info(f"Fetching: {url}")
    response = requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        },
        timeout=30
    )
    response.raise_for_status()
    logger.info(f"Got {len(response.text)} bytes, status {response.status_code}")
    return response.text


def analyze_html(html: str, save_file: str = "debug_page.html"):
    """Analyze HTML structure to find articles."""
    
    # Save raw HTML for inspection
    Path(save_file).write_text(html, encoding='utf-8')
    logger.info(f"Saved HTML to {save_file}")
    
    soup = BeautifulSoup(html, 'lxml')
    
    # Method 1: Find all links that match article pattern /ta-p/NNNN
    logger.info("\n=== METHOD 1: All /ta-p/ links ===")
    ta_p_links = soup.find_all('a', href=re.compile(r'/ta-p/\d+'))
    logger.info(f"Found {len(ta_p_links)} links with /ta-p/ pattern")
    
    seen_urls = set()
    for link in ta_p_links[:20]:  # Show first 20
        href = link.get('href', '')
        text = link.get_text(strip=True)[:80]
        if href not in seen_urls:
            seen_urls.add(href)
            logger.info(f"  Link: {href}")
            logger.info(f"  Text: {text}")
            logger.info("")
    
    # Method 2: Find all links with Official-Support-Articles
    logger.info("\n=== METHOD 2: Links with Official-Support-Articles ===")
    article_links = soup.find_all('a', href=re.compile(r'/t5/Official-Support-Articles/'))
    logger.info(f"Found {len(article_links)} links with Official-Support-Articles")
    
    seen_urls = set()
    for link in article_links[:20]:
        href = link.get('href', '')
        text = link.get_text(strip=True)[:80]
        if href not in seen_urls and '/ta-p/' in href:
            seen_urls.add(href)
            logger.info(f"  Link: {href}")
            logger.info(f"  Text: {text}")
            logger.info("")
    
    # Method 3: Look for article containers by class names
    logger.info("\n=== METHOD 3: Looking for common container classes ===")
    
    # Common Lithium/Khoros class patterns
    class_patterns = [
        'lia-message',
        'message-list',
        'tkb-article',
        'lia-list-row',
        'MessageList',
        'TkbBoardMessage',
        'tkb-board',
        'lia-component',
    ]
    
    for pattern in class_patterns:
        elements = soup.find_all(class_=re.compile(pattern, re.I))
        if elements:
            logger.info(f"  Found {len(elements)} elements with class matching '{pattern}'")
            # Show first element's class
            if elements:
                classes = elements[0].get('class', [])
                logger.info(f"    Example classes: {classes}")
    
    # Method 4: Find the Recent Documents section
    logger.info("\n=== METHOD 4: Looking for 'Recent Documents' section ===")
    
    # Find heading
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4'], string=re.compile(r'Recent\s*Document', re.I))
    logger.info(f"Found {len(headings)} 'Recent Documents' headings")
    
    for heading in headings:
        parent = heading.parent
        for _ in range(5):  # Go up 5 levels
            if parent:
                # Look for links in this parent
                links_in_section = parent.find_all('a', href=re.compile(r'/ta-p/\d+'))
                if links_in_section:
                    logger.info(f"  Found {len(links_in_section)} article links in section")
                    for link in links_in_section[:10]:
                        href = link.get('href', '')
                        text = link.get_text(strip=True)[:60]
                        logger.info(f"    {href} - {text}")
                    break
                parent = parent.parent
    
    # Method 5: Look for any list items with article links
    logger.info("\n=== METHOD 5: List items with article content ===")
    
    list_items = soup.find_all('li')
    article_list_items = []
    for li in list_items:
        link = li.find('a', href=re.compile(r'/ta-p/\d+'))
        if link:
            href = link.get('href', '')
            text = link.get_text(strip=True)
            # Skip if it's in "Top Topics" section
            parent_text = li.parent.get_text() if li.parent else ""
            if "Top Topics" not in parent_text[:200]:
                article_list_items.append((href, text))
    
    logger.info(f"Found {len(article_list_items)} list items with article links (excluding Top Topics)")
    for href, text in article_list_items[:15]:
        logger.info(f"  {href[:60]} - {text[:50]}")
    
    # Method 6: Look at page structure - find divs with data attributes
    logger.info("\n=== METHOD 6: Elements with data- attributes ===")
    
    data_attrs = soup.find_all(attrs={"data-lia-message-uid": True})
    logger.info(f"Found {len(data_attrs)} elements with data-lia-message-uid")
    
    for elem in data_attrs[:5]:
        uid = elem.get('data-lia-message-uid')
        link = elem.find('a', href=re.compile(r'/ta-p/'))
        if link:
            logger.info(f"  UID: {uid}, Link: {link.get('href', '')[:60]}")
    
    # Show all unique article URLs found
    logger.info("\n=== SUMMARY: All unique article URLs ===")
    all_article_urls = set()
    for link in soup.find_all('a', href=re.compile(r'/ta-p/\d+')):
        href = link.get('href', '')
        # Clean the URL
        if href.startswith('/'):
            href = BASE_URL + href
        href = href.split('?')[0].split('#')[0]
        all_article_urls.add(href)
    
    logger.info(f"Total unique article URLs: {len(all_article_urls)}")
    for url in sorted(all_article_urls)[:30]:
        logger.info(f"  {url}")


def main():
    logger.info("=== KB Page Debug Script ===")
    logger.info(f"Target URL: {KB_URL}")
    
    try:
        html = fetch_page(KB_URL)
        analyze_html(html)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)


if __name__ == "__main__":
    main()

