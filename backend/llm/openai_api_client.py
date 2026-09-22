"""
OpenAI-compatible local LLM client.

Targets servers that expose the standard OpenAI REST API (e.g. FastFlowLM at
http://127.0.0.1:52625/v1). Uses /v1/models and /v1/chat/completions.

FLM (FastFlowLM) often returns HTTP 200 with an empty ``choices`` array on a
cold prompt-cache miss when each request uses a new TCP connection. This client
uses a single keep-alive session, an optional warmup completion, and bounded
retries on the same connection before failing.
"""

import json
import logging
import time
from typing import Optional, List, Dict, Any, Tuple

import httpx

from backend.llm.client import ModelInfo, CompletionResult
from backend.llm.lmstudio_client import (
    _normalize_latex_math,
    _strip_markdown_links,
    _MD_LINK_RE,
)

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_API_BASE_URL = "http://127.0.0.1:52625/v1"
DEFAULT_OPENAI_API_KEY = "flm"
OPENAI_API_DEFAULT_TIMEOUT_SECONDS = 600.0
OPENAI_API_DEFAULT_MAX_TOKENS = 1500
OPENAI_API_REPORT_MAX_TEMPERATURE = 0.35

# FLM framework: cold cache miss → empty choices; retry on same HTTP session.
FLM_WARMUP_ENABLED = True
FLM_WARMUP_MAX_TOKENS = 16
FLM_MAX_ATTEMPTS = 3
FLM_RETRY_BACKOFF_SECONDS = (0.0, 2.0, 5.0)
FLM_EMPTY_RESPONSE_LOG_CHARS = 500


def _estimate_tokens(text: str) -> int:
    """Rough token estimate when the server omits usage stats."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _extract_openai_message_content(message: Dict[str, Any]) -> str:
    """Extract assistant text from an OpenAI-style message object."""
    if not message:
        return ""

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text" and part.get("text"):
                    parts.append(str(part["text"]))
                elif part.get("text"):
                    parts.append(str(part["text"]))
        joined = "".join(parts).strip()
        if joined:
            return joined

    for key in ("reasoning_content", "reasoning", "text"):
        alt = message.get(key)
        if isinstance(alt, str) and alt.strip():
            return alt

    return content if isinstance(content, str) else ""


def _parse_chat_completion_response(
    data: Dict[str, Any],
    model: Optional[str],
    messages: List[Dict[str, str]],
) -> Tuple[str, str, int, int, str]:
    """Return content, finish_reason, prompt_tokens, completion_tokens, used_model."""
    choices = data.get("choices", [])
    content = ""
    finish_reason = "stop"
    if choices:
        choice = choices[0]
        message = choice.get("message", {})
        content = _extract_openai_message_content(message)
        if not content.strip():
            legacy_text = choice.get("text")
            if isinstance(legacy_text, str):
                content = legacy_text
        finish_reason = choice.get("finish_reason") or "stop"

    stripped = _strip_markdown_links(content)
    if stripped != content:
        logger.info(
            "Stripped %d markdown link(s) from OpenAI API response.",
            len(_MD_LINK_RE.findall(content)),
        )
        content = stripped

    normalized = _normalize_latex_math(content)
    if normalized != content:
        logger.info("Normalized LaTeX math in OpenAI API response.")
        content = normalized

    usage = data.get("usage", {})
    prompt_tokens = int(usage.get("prompt_tokens", 0))
    completion_tokens = int(usage.get("completion_tokens", 0))
    if completion_tokens == 0 and content.strip():
        completion_tokens = _estimate_tokens(content)
    if prompt_tokens == 0 and messages:
        prompt_chars = sum(len(m.get("content") or "") for m in messages)
        prompt_tokens = _estimate_tokens(" " * prompt_chars)
    used_model = data.get("model", model or "openai-api-local")
    return content, finish_reason, prompt_tokens, completion_tokens, used_model


def _log_flm_empty_response(
    data: Dict[str, Any],
    raw_text: str,
    used_model: str,
    finish_reason: str,
    choices_count: int,
    attempt: int,
) -> None:
    snippet = (
        raw_text[:FLM_EMPTY_RESPONSE_LOG_CHARS]
        if raw_text
        else json.dumps(data)[:FLM_EMPTY_RESPONSE_LOG_CHARS]
    )
    logger.warning(
        "FLM/OpenAI-compatible server returned empty content "
        "(attempt=%d, model=%s, finish_reason=%s, choices=%d). Raw: %s",
        attempt,
        used_model,
        finish_reason,
        choices_count,
        snippet,
    )


class OpenAIApiClient:
    """Client for OpenAI-compatible local inference servers."""

    def __init__(
        self,
        base_url: str = DEFAULT_OPENAI_API_BASE_URL,
        api_key: str = DEFAULT_OPENAI_API_KEY,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or DEFAULT_OPENAI_API_KEY

    def set_base_url(self, url: str):
        self.base_url = url.rstrip("/")

    def set_api_key(self, api_key: str):
        self.api_key = (api_key or DEFAULT_OPENAI_API_KEY).strip()

    def _api_base(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/v1"):
            return base
        return f"{base}/v1"

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def get_models(self) -> List[ModelInfo]:
        """Fetch models from GET /v1/models."""
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{self._api_base()}/models",
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError:
            logger.warning("OpenAI API: connection refused at %s", self.base_url)
            return []
        except Exception as e:
            logger.warning("OpenAI API get_models error: %s", e)
            return []

        models: List[ModelInfo] = []
        for m in data.get("data", []):
            model_id = m.get("id", "")
            if not model_id:
                continue
            models.append(
                ModelInfo(
                    id=model_id,
                    name=model_id,
                    description="OpenAI-compatible local model",
                    context_length=8192,
                    prompt_price=0.0,
                    completion_price=0.0,
                )
            )
        return models

    def test_connection(self) -> Dict[str, Any]:
        """Ping /v1/models and return success/message/model_count."""
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(
                    f"{self._api_base()}/models",
                    headers=self._headers(),
                )
                if response.status_code == 200:
                    data = response.json()
                    model_list = data.get("data", [])
                    count = len(model_list)
                    if count:
                        msg = (
                            f"Connected to OpenAI-compatible server. "
                            f"{count} model(s) available."
                        )
                    else:
                        msg = (
                            "Connected to OpenAI-compatible server, "
                            "but no models were returned. "
                            "Start your local server and load a model first."
                        )
                    return {"success": True, "message": msg, "model_count": count}
                return {
                    "success": False,
                    "message": f"Server returned HTTP {response.status_code}",
                }
        except httpx.ConnectError:
            return {
                "success": False,
                "message": (
                    f"Cannot connect to {self.base_url}. "
                    "Make sure your OpenAI-compatible server is running "
                    "(e.g. flm serve <model>)."
                ),
            }
        except httpx.TimeoutException:
            return {
                "success": False,
                "message": "Connection timeout — server not responding.",
            }
        except Exception as e:
            return {"success": False, "message": f"Connection error: {e}"}

    def _post_chat_completion(
        self,
        client: httpx.Client,
        payload: Dict[str, Any],
        cancel_file_id: Optional[int],
        cancel_kind: str,
    ) -> httpx.Response:
        from backend.llm.generation_cancel import check_cancelled, maybe_raise_cancelled

        if cancel_file_id is not None:
            check_cancelled(cancel_file_id, kind=cancel_kind)
        try:
            return client.post(
                f"{self._api_base()}/chat/completions",
                headers=self._headers(),
                json=payload,
            )
        except httpx.ConnectError as e:
            maybe_raise_cancelled(cancel_file_id, e, kind=cancel_kind)
            raise ValueError(
                f"Cannot connect to OpenAI-compatible server at {self.base_url}. "
                "Make sure the server is running."
            ) from e
        except httpx.TimeoutException as e:
            maybe_raise_cancelled(cancel_file_id, e, kind=cancel_kind)
            raise ValueError(
                "OpenAI-compatible server timed out. "
                "Try a faster model or lower Max tokens in AI config."
            ) from e
        except Exception as e:
            maybe_raise_cancelled(cancel_file_id, e, kind=cancel_kind)
            raise

    def _run_flm_warmup(
        self,
        client: httpx.Client,
        model: Optional[str],
        temperature: float,
        cancel_file_id: Optional[int],
        cancel_kind: str,
    ) -> None:
        """Prime FLM prompt cache on the same HTTP session before the real request."""
        warmup_payload: Dict[str, Any] = {
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "max_tokens": FLM_WARMUP_MAX_TOKENS,
            "temperature": min(temperature, 0.1),
            "stream": False,
        }
        if model:
            warmup_payload["model"] = model
        logger.debug("FLM warmup request on shared session (model=%s)", model or "(default)")
        response = self._post_chat_completion(
            client, warmup_payload, cancel_file_id, cancel_kind
        )
        if response.status_code != 200:
            logger.debug(
                "FLM warmup returned HTTP %s (continuing): %s",
                response.status_code,
                response.text[:200],
            )

    def complete(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = OPENAI_API_DEFAULT_MAX_TOKENS,
        temperature: float = 0.3,
        cancel_file_id: Optional[int] = None,
        cancel_kind: str = "report",
        timeout_seconds: Optional[float] = None,
        flm_reliability: bool = True,
        **kwargs,
    ) -> CompletionResult:
        """POST /v1/chat/completions with FLM-aware session reuse and retries."""
        payload: Dict[str, Any] = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if model:
            payload["model"] = model

        request_timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else OPENAI_API_DEFAULT_TIMEOUT_SECONDS
        )
        logger.info(
            "OpenAI API request: model=%s max_tokens=%d timeout=%.0fs flm_reliability=%s",
            model or "(default)",
            max_tokens,
            request_timeout,
            flm_reliability,
        )

        from backend.llm.generation_cancel import (
            check_cancelled,
            register_client,
            unregister_client,
        )

        client = httpx.Client(timeout=request_timeout)
        if cancel_file_id is not None:
            register_client(cancel_file_id, client, kind=cancel_kind)

        last_result: Optional[CompletionResult] = None
        try:
            if flm_reliability and FLM_WARMUP_ENABLED:
                self._run_flm_warmup(
                    client, model, temperature, cancel_file_id, cancel_kind
                )

            for attempt in range(1, FLM_MAX_ATTEMPTS + 1):
                if attempt > 1 and flm_reliability:
                    backoff = FLM_RETRY_BACKOFF_SECONDS[
                        min(attempt - 1, len(FLM_RETRY_BACKOFF_SECONDS) - 1)
                    ]
                    if backoff > 0:
                        logger.info(
                            "FLM empty response — retry %d/%d after %.1fs (same session)",
                            attempt,
                            FLM_MAX_ATTEMPTS,
                            backoff,
                        )
                        time.sleep(backoff)

                response = self._post_chat_completion(
                    client, payload, cancel_file_id, cancel_kind
                )

                if response.status_code != 200:
                    raise ValueError(
                        f"OpenAI API error ({response.status_code}): {response.text[:500]}"
                    )

                raw_text = response.text
                data = response.json()
                content, finish_reason, prompt_tokens, completion_tokens, used_model = (
                    _parse_chat_completion_response(data, model, messages)
                )

                last_result = CompletionResult(
                    content=content,
                    model=used_model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                    cost_usd=0.0,
                    finish_reason=finish_reason,
                )

                if flm_reliability:
                    from backend.llm.flm_metrics import record_flm_completion

                    record_flm_completion(empty=not content.strip())

                if content.strip():
                    if attempt > 1:
                        logger.info(
                            "FLM request succeeded on attempt %d/%d",
                            attempt,
                            FLM_MAX_ATTEMPTS,
                        )
                    return last_result

                _log_flm_empty_response(
                    data,
                    raw_text,
                    used_model,
                    finish_reason,
                    len(data.get("choices", [])),
                    attempt,
                )

                if not flm_reliability or attempt >= FLM_MAX_ATTEMPTS:
                    break

            if last_result is not None:
                return last_result

            if cancel_file_id is not None:
                check_cancelled(cancel_file_id, kind=cancel_kind)
            raise ValueError("OpenAI API request ended without a response")
        finally:
            if cancel_file_id is not None:
                unregister_client(cancel_file_id, client, kind=cancel_kind)
            client.close()


_client: Optional[OpenAIApiClient] = None


def get_openai_api_client() -> OpenAIApiClient:
    """Return the singleton OpenAI-compatible client."""
    global _client
    if _client is None:
        _client = OpenAIApiClient()
    return _client


def set_openai_api_base_url(url: str):
    """Update base URL on the singleton client."""
    client = get_openai_api_client()
    client.set_base_url(url)
    logger.info("OpenAI API base URL set to: %s", url)


def set_openai_api_key(api_key: str):
    """Update API key on the singleton client."""
    client = get_openai_api_client()
    client.set_api_key(api_key)
    logger.info("OpenAI API key updated.")
