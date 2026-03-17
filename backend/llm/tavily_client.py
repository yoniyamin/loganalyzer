"""
Lightweight Tavily client for advanced answers.
Placed in its own module to keep external search isolated.
"""

import os
import logging
from typing import Optional, Dict, Any, List

import httpx

logger = logging.getLogger(__name__)

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class TavilyClient:
    def __init__(self, api_key: Optional[str] = None, timeout: float = 20.0):
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY")
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def set_api_key(self, api_key: str):
        self.api_key = api_key

    def advanced_answer(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "advanced",
    ) -> Dict[str, Any]:
        """
        Call Tavily advanced answer API.
        Returns raw JSON with answer and sources.
        """
        if not self.api_key:
            raise ValueError("Tavily API key not configured")

        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "include_answer": True,
            "include_raw_content": False,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(TAVILY_SEARCH_URL, json=payload)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning("Tavily search failed: %s", e)
            raise


def format_tavily_sources(data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Normalize source list for frontend consumption."""
    sources = data.get("results") or []
    formatted = []
    for item in sources:
        formatted.append(
            {
                "title": item.get("title") or item.get("url") or "Source",
                "url": item.get("url"),
            }
        )
    return formatted








