"""Tests for Gemini API client."""
import os
import sys
from unittest.mock import MagicMock, patch

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.llm.gemini_client import GeminiClient


class TestGeminiClientAuth:
    def test_complete_sends_api_key_in_header_not_url(self):
        client = GeminiClient(api_key="secret-gemini-key")
        http = MagicMock()
        response = httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "ok"}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 10,
                    "candidatesTokenCount": 5,
                    "totalTokenCount": 15,
                },
            },
            request=httpx.Request(
                "POST",
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            ),
        )
        http.post.return_value = response

        with patch("httpx.Client", return_value=http):
            result = client.complete(
                messages=[{"role": "user", "content": "hello"}],
                model="gemini-2.5-flash",
            )

        assert result.content == "ok"
        http.post.assert_called_once()
        url, = http.post.call_args[0]
        kwargs = http.post.call_args[1]
        assert "secret-gemini-key" not in url
        assert "key=" not in url
        assert kwargs["headers"]["x-goog-api-key"] == "secret-gemini-key"

    def test_connection_test_uses_header_auth(self):
        client = GeminiClient(api_key="secret-gemini-key")
        http = MagicMock()
        http.get.return_value = httpx.Response(
            200,
            json={"models": []},
            request=httpx.Request(
                "GET",
                "https://generativelanguage.googleapis.com/v1beta/models",
            ),
        )

        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value = http
            assert client.test_connection() is True

        http.get.assert_called_once()
        url, = http.get.call_args[0]
        kwargs = http.get.call_args[1]
        assert "secret-gemini-key" not in url
        assert kwargs["headers"]["x-goog-api-key"] == "secret-gemini-key"
