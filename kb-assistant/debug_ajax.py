#!/usr/bin/env python3
"""Debug script to analyze AJAX response format."""

import requests
from pathlib import Path

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
KB_LISTING_URL = "https://community.qlik.com/t5/b-qlik-support-knowledge-base/Qlik+Replicate/pd-p/qlikReplicate"

# AJAX endpoint
AJAX_PAGER_URL = "https://community.qlik.com/t5/products/productpage.messagelist.grid.pager_0:changepage"

def fetch_and_save_ajax():
    params = {
        "t:ac": "node-display-id/board:qlik-support-knowledge-base/product-id/qlikReplicate",
        "t:cp": "messages/contributions/messagelistcontributionpage",
        "page": "2"
    }
    
    print(f"Fetching AJAX page 2...")
    print(f"URL: {AJAX_PAGER_URL}")
    print(f"Params: {params}")
    
    response = requests.get(
        AJAX_PAGER_URL,
        params=params,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": KB_LISTING_URL,
        },
        timeout=30
    )
    
    print(f"\nStatus: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type')}")
    print(f"Content length: {len(response.text)} bytes")
    
    # Save response
    Path("ajax_response.html").write_text(response.text, encoding='utf-8')
    print(f"\nSaved to ajax_response.html")
    
    # Show first 2000 chars
    print(f"\n=== Response content (first 2000 chars) ===")
    print(response.text[:2000])
    
    if len(response.text) > 2000:
        print(f"\n... ({len(response.text) - 2000} more chars)")

if __name__ == "__main__":
    fetch_and_save_ajax()
