"""Tests for LM Studio native API client."""
import os
import sys
from unittest.mock import MagicMock, patch

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.llm.lmstudio_client import LMStudioClient


class TestLMStudioReasoningParam:
    def test_skips_reasoning_for_models_without_capability(self):
        client = LMStudioClient()
        with patch.object(
            client,
            "_model_exposes_reasoning_config",
            return_value=False,
        ):
            payload: dict = {"input": "hi", "model": "qwen3.5-9b-deepseek-v4-flash"}
            client._apply_reasoning_param(payload, model=payload["model"], reasoning=None)
            assert "reasoning" not in payload

    def test_sets_reasoning_off_for_capable_models(self):
        client = LMStudioClient()
        with patch.object(
            client,
            "_model_exposes_reasoning_config",
            return_value=True,
        ):
            payload: dict = {"input": "hi", "model": "gemma-4-reasoning"}
            client._apply_reasoning_param(payload, model=payload["model"], reasoning=None)
            assert payload["reasoning"] == "off"

    def test_post_chat_retries_without_reasoning_on_400(self):
        client = LMStudioClient()
        http = MagicMock()
        bad = httpx.Response(
            400,
            json={
                "error": {
                    "message": "Model 'qwen' does not expose reasoning configuration.",
                    "param": "reasoning",
                }
            },
            request=httpx.Request("POST", "http://localhost:1234/api/v1/chat"),
        )
        ok = httpx.Response(
            200,
            json={
                "output": [{"type": "message", "content": "OK"}],
                "stats": {"input_tokens": 1, "total_output_tokens": 1},
                "model_instance_id": "qwen",
            },
            request=httpx.Request("POST", "http://localhost:1234/api/v1/chat"),
        )
        http.post.side_effect = [bad, ok]

        payload = {
            "input": "Say OK",
            "model": "qwen",
            "reasoning": "off",
        }
        response = client._post_chat(http, payload)
        assert response.status_code == 200
        assert http.post.call_count == 2
        assert "reasoning" not in http.post.call_args_list[1].kwargs["json"]

    def test_complete_omits_reasoning_for_non_reasoning_model(self):
        client = LMStudioClient()
        captured: dict = {}

        def _fake_post_chat(_http, payload):
            captured.update(payload)
            return httpx.Response(
                200,
                json={
                    "output": [{"type": "message", "content": "Report body"}],
                    "stats": {"input_tokens": 10, "total_output_tokens": 5},
                    "model_instance_id": "qwen",
                },
                request=httpx.Request("POST", "http://localhost:1234/api/v1/chat"),
            )

        with patch.object(client, "_model_exposes_reasoning_config", return_value=False):
            with patch("httpx.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client_cls.return_value = mock_client
                with patch.object(client, "_post_chat", side_effect=_fake_post_chat):
                    result = client.complete(
                        messages=[{"role": "user", "content": "Analyze"}],
                        model="qwen3.5-9b-deepseek-v4-flash",
                    )
        assert result.content == "Report body"
        assert "reasoning" not in captured
