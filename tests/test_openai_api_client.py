"""Tests for OpenAI-compatible local client (FLM / openai_api provider)."""
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.llm.client import CompletionResult
from backend.llm.openai_api_client import (
    OpenAIApiClient,
    _extract_openai_message_content,
    FLM_MAX_ATTEMPTS,
)


class TestExtractOpenAIMessageContent:
    def test_plain_content(self):
        assert _extract_openai_message_content({"content": "Hello"}) == "Hello"

    def test_reasoning_content_fallback(self):
        msg = {"content": "", "reasoning_content": "Analysis...\n\nFinal answer."}
        assert _extract_openai_message_content(msg) == "Analysis...\n\nFinal answer."

    def test_multimodal_text_parts(self):
        msg = {
            "content": [
                {"type": "text", "text": "Part one. "},
                {"type": "text", "text": "Part two."},
            ]
        }
        assert _extract_openai_message_content(msg) == "Part one. Part two."


def _mock_response(status_code: int, payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = json.dumps(payload)
    resp.json.return_value = payload
    return resp


class TestFlmSessionRetry:
    """FLM retries empty choices on the same HTTP session."""

    @patch("backend.llm.openai_api_client.time.sleep")
    @patch("backend.llm.openai_api_client.httpx.Client")
    def test_retries_empty_then_succeeds(self, mock_client_cls, mock_sleep):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        empty_payload = {"choices": [], "model": "test-model", "usage": {}}
        good_payload = {
            "choices": [{"message": {"content": "# Report\n\nDone."}, "finish_reason": "stop"}],
            "model": "test-model",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }

        mock_client.post.side_effect = [
            _mock_response(200, empty_payload),  # warmup
            _mock_response(200, empty_payload),  # attempt 1
            _mock_response(200, good_payload),   # attempt 2
        ]

        client = OpenAIApiClient()
        result = client.complete(
            messages=[{"role": "user", "content": "Analyze"}],
            model="test-model",
            flm_reliability=True,
        )

        assert "Report" in result.content
        assert mock_client.post.call_count >= 3
        mock_client_cls.assert_called_once()
        mock_client.close.assert_called_once()

    @patch("backend.llm.openai_api_client.time.sleep")
    @patch("backend.llm.openai_api_client.httpx.Client")
    def test_returns_empty_after_max_attempts(self, mock_client_cls, mock_sleep):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        empty_payload = {"choices": [], "model": "test-model", "usage": {}}
        mock_client.post.return_value = _mock_response(200, empty_payload)

        client = OpenAIApiClient()
        result = client.complete(
            messages=[{"role": "user", "content": "Analyze"}],
            model="test-model",
            flm_reliability=True,
        )

        assert result.content == ""
        # warmup + FLM_MAX_ATTEMPTS main attempts
        assert mock_client.post.call_count == 1 + FLM_MAX_ATTEMPTS


class TestOpenAIApiReportGenerator:
    """generate_report delegates FLM retries to the client."""

    @patch("backend.llm.report_generator.ReportGenerator.build_report_messages")
    def test_openai_api_single_complete_call_on_success(self, mock_build, indexed_file):
        db, file_id, _ = indexed_file
        from backend.llm.report_generator import ReportGenerator, ReportPromptBundle

        mock_build.return_value = ReportPromptBundle(
            messages=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "test prompt"},
            ],
            est_tokens=100,
            context_stats={"errors": 0, "anomalies": 0, "kb": 0, "release_notes": 0},
        )

        good = CompletionResult(
            content="# Log Analysis Report\n\nFindings here.",
            model="qwen3.5:9b",
            prompt_tokens=2603,
            completion_tokens=400,
            total_tokens=3003,
            cost_usd=0.0,
            finish_reason="stop",
        )

        gen = ReportGenerator(db)
        gen.provider = "openai_api"

        with patch.object(gen.openai_api_client, "complete", return_value=good) as mock_complete:
            result = gen.generate_report(file_id, quick=True)

        assert mock_complete.call_count == 1
        assert result["report_content"].startswith("# Log Analysis Report")

    @patch("backend.llm.report_generator.ReportGenerator.build_report_messages")
    def test_openai_api_raises_on_empty_from_client(self, mock_build, indexed_file):
        db, file_id, _ = indexed_file
        from backend.llm.report_generator import ReportGenerator, ReportPromptBundle

        mock_build.return_value = ReportPromptBundle(
            messages=[{"role": "user", "content": "test"}],
            est_tokens=50,
            context_stats={"errors": 0, "anomalies": 0, "kb": 0, "release_notes": 0},
        )

        empty = CompletionResult(
            content="",
            model="qwen3.5:9b",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=0.0,
            finish_reason="stop",
        )

        gen = ReportGenerator(db)
        gen.provider = "openai_api"

        with patch.object(gen.openai_api_client, "complete", return_value=empty):
            with pytest.raises(ValueError, match="FLM retries"):
                gen.generate_report(file_id, quick=True)
