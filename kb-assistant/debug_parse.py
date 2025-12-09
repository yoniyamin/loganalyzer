"""Debug script to test article parsing."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import requests
from bs4 import BeautifulSoup
from article_fetcher import fetch_and_parse_article, parse_article_html

# Test URL - use one that was failing
urls = [
    'https://community.qlik.com/t5/Official-Support-Articles/ERR-SSL-KEY-USAGE-INCOMPATIBLE-Error-After-Qlik-Replicate/ta-p/2073067',
    'https://community.qlik.com/t5/Official-Support-Articles/How-to-download-Qlik-Products/ta-p/1906869',
]

for url in urls:
    print(f"\n{'='*60}")
    print(f"Testing: {url}")
    print('='*60)
    
    r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    print(f"Status: {r.status_code}, Size: {len(r.text)} bytes")
    
    soup = BeautifulSoup(r.text, 'html.parser')
    
    # Check various selectors
    selectors = [
        '.lia-message-body-content',
        '.lia-tkb-article-body-content',
        '.lia-message-body',
        '.lia-tkb-body',
        '.MessageBody',
        '.message-body-content',
        '.lia-component-tkb-widget-article-body',
        '.lia-quilt-column-main',
    ]
    
    print("\n=== Testing selectors ===")
    for sel in selectors:
        elem = soup.select_one(sel)
        if elem:
            text = elem.get_text(strip=True)
            print(f"  {sel}: FOUND ({len(text)} chars)")
            if len(text) > 100:
                print(f"    Preview: {text[:150]}...")
        else:
            print(f"  {sel}: NOT FOUND")
    
    # Find divs with relevant classes
    print("\n=== Divs with message/body/content in class ===")
    found_divs = []
    for div in soup.find_all('div', class_=True):
        classes = ' '.join(div.get('class', []))
        if any(x in classes.lower() for x in ['message-body', 'body-content', 'article-body', 'tkb-body']):
            text = div.get_text(strip=True)
            if len(text) > 100:
                found_divs.append((div.get('class')[0], len(text), text[:100]))
    
    for cls, length, preview in found_divs[:5]:
        print(f"  .{cls}: {length} chars - {preview}...")
    
    # Check title
    print("\n=== Title search ===")
    h2 = soup.select_one('h2.lia-message-subject')
    if h2:
        print(f"  h2.lia-message-subject: {h2.get_text(strip=True)[:80]}")
    
    title = soup.find('title')
    if title:
        print(f"  <title>: {title.get_text()[:80]}")
    
    # Test actual parser
    print("\n=== Testing article_fetcher.parse_article_html ===")
    result = parse_article_html(r.text, url)
    if result:
        print(f"  SUCCESS!")
        print(f"  Title: {result.get('title', 'N/A')[:60]}")
        print(f"  Content length: {result.get('content_length', 0)} chars")
        print(f"  Content preview: {result.get('content', '')[:200]}...")
    else:
        print(f"  FAILED - returned None")

print("\n=== Done ===")
