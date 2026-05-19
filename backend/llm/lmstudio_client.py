"""
LM Studio Local LLM Client

Uses the native LM Studio REST API (/api/v1/) which supports:
- MCPs configured in LM Studio (e.g. Tavily) — invoked automatically by the model
- Streaming
- Stateful chats

The native API uses an `input` string rather than a role-based messages array.
Messages passed from the rest of the app (system + user) are converted to a
structured input string that instruction-tuned models understand well.
"""

import logging
import re
from typing import Optional, List, Dict, Any, Generator

import httpx

from backend.llm.client import ModelInfo, CompletionResult

logger = logging.getLogger(__name__)

_MD_LINK_RE = re.compile(r'\[([^\]]+)\]\(https?://[^)]+\)')


def _strip_markdown_links(text: str) -> str:
    """Replace [anchor](url) with just the anchor text.

    Called when the model produced no tool_call output items, meaning it never
    actually ran a web search — any URLs it wrote are therefore fabricated.
    """
    return _MD_LINK_RE.sub(r'\1', text)


DEFAULT_LMSTUDIO_BASE_URL = "http://localhost:1234"
# Lower than cloud providers: local models run slower, and the Python pre-processing
# already produces a highly-structured summary, so 1 500 tokens covers a full report.
LMSTUDIO_DEFAULT_MAX_TOKENS = 1500


class LMStudioClient:
    """
    Client for the native LM Studio REST API.

    Targets /api/v1/chat for completions and /api/v1/models for model listing.
    The app does not call Tavily separately when using this client — the Tavily
    MCP configured inside LM Studio is invoked automatically by the model.
    """

    def __init__(self, base_url: str = DEFAULT_LMSTUDIO_BASE_URL):
        self.base_url = base_url.rstrip("/")

    def set_base_url(self, url: str):
        self.base_url = url.rstrip("/")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _convert_messages_to_input(self, messages: List[Dict[str, str]]) -> str:
        """
        Convert OpenAI-format role-based messages into the flat input string
        expected by the native /api/v1/chat endpoint.

        System messages are wrapped in <instructions> tags that instruction-
        tuned models reliably recognise. Previous assistant turns (rare in this
        app) are wrapped in <previous_response> tags.
        """
        parts: List[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if not content:
                continue
            if role == "system":
                parts.append(f"<instructions>\n{content}\n</instructions>")
            elif role == "assistant":
                parts.append(f"<previous_response>\n{content}\n</previous_response>")
            else:  # user
                parts.append(content)
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_models(self) -> List[ModelInfo]:
        """
        Fetch available models from GET /api/v1/models.

        Returns all LLM-type models. Loaded models (with active instances)
        are listed first; unloaded models are appended with a note.
        """
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(f"{self.base_url}/api/v1/models")
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError:
            logger.warning("LM Studio: connection refused at %s", self.base_url)
            return []
        except Exception as e:
            logger.warning("LM Studio get_models error: %s", e)
            return []

        models: List[ModelInfo] = []
        loaded_ids: List[ModelInfo] = []
        unloaded_ids: List[ModelInfo] = []

        for m in data.get("models", []):
            if m.get("type") != "llm":
                continue  # skip embedding models etc.

            key = m.get("key", "")
            display_name = m.get("display_name", key)
            params = m.get("params_string", "")
            max_ctx = m.get("max_context_length", 4096)
            has_vision = bool(m.get("capabilities", {}).get("vision", False))

            loaded_instances = m.get("loaded_instances", [])
            if loaded_instances:
                model_id = loaded_instances[0].get("id", key)
                inst_ctx = loaded_instances[0].get("config", {}).get("context_length", max_ctx)
                description = f"Loaded — {params} params, context {inst_ctx:,}" if params else f"Loaded — context {inst_ctx:,}"
                info = ModelInfo(
                    id=model_id,
                    name=f"{display_name} (loaded)",
                    description=description,
                    context_length=inst_ctx,
                    prompt_price=0.0,
                    completion_price=0.0,
                )
                loaded_ids.append(info)
            else:
                description = f"Not loaded — {params} params" if params else "Not loaded"
                info = ModelInfo(
                    id=key,
                    name=display_name,
                    description=description,
                    context_length=max_ctx,
                    prompt_price=0.0,
                    completion_price=0.0,
                )
                unloaded_ids.append(info)

            _ = has_vision  # reserved for future use

        models = loaded_ids + unloaded_ids
        return models

    def test_connection(self) -> Dict[str, Any]:
        """
        Ping /api/v1/models and return success/message/model_count.
        model_count reflects the number of currently-loaded models.
        """
        try:
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.base_url}/api/v1/models")
                if response.status_code == 200:
                    data = response.json()
                    all_models = [m for m in data.get("models", []) if m.get("type") == "llm"]
                    loaded = [m for m in all_models if m.get("loaded_instances")]
                    count = len(loaded) or len(all_models)
                    if loaded:
                        msg = (
                            f"Connected to LM Studio. "
                            f"{len(loaded)} model(s) loaded, {len(all_models)} available."
                        )
                    else:
                        msg = (
                            f"Connected to LM Studio. "
                            f"{len(all_models)} model(s) available but none currently loaded. "
                            "Load a model in LM Studio before generating a report."
                        )
                    return {"success": True, "message": msg, "model_count": count}
                else:
                    return {
                        "success": False,
                        "message": f"LM Studio returned HTTP {response.status_code}",
                    }
        except httpx.ConnectError:
            return {
                "success": False,
                "message": (
                    f"Cannot connect to LM Studio at {self.base_url}. "
                    "Make sure the server is running (Developer tab → Start Server)."
                ),
            }
        except httpx.TimeoutException:
            return {"success": False, "message": "Connection timeout — LM Studio not responding."}
        except Exception as e:
            return {"success": False, "message": f"Connection error: {e}"}

    def complete(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = LMSTUDIO_DEFAULT_MAX_TOKENS,
        temperature: float = 0.3,
        cancel_file_id: Optional[int] = None,
        cancel_kind: str = "report",
        **kwargs,
    ) -> CompletionResult:
        """
        POST /api/v1/chat — synchronous completion.

        Ignores kwargs (web_search, image_data, etc.) because:
        - web_search is handled automatically by the Tavily MCP inside LM Studio
        - image_data is not yet supported via the native API in this client
        """
        input_text = self._convert_messages_to_input(messages)

        # Size the KV window for the full prompt + completion. LM Studio defaults
        # to small contexts (e.g. 4096) which truncates long structured prompts.
        est_prompt_tokens = max(len(input_text) // 4 + 1024, 3072)
        ctx_len = min(max(est_prompt_tokens + max_tokens + 1024, 8192), 65536)

        payload: Dict[str, Any] = {
            "input": input_text,
            "temperature": temperature,
            "context_length": ctx_len,
        }
        if model:
            payload["model"] = model

        from backend.llm.generation_cancel import (
            check_cancelled,
            maybe_raise_cancelled,
            register_client,
            unregister_client,
        )

        client = httpx.Client(timeout=180.0)
        if cancel_file_id is not None:
            register_client(cancel_file_id, client, kind=cancel_kind)
        response = None
        try:
            if cancel_file_id is not None:
                check_cancelled(cancel_file_id, kind=cancel_kind)
            response = client.post(f"{self.base_url}/api/v1/chat", json=payload)
        except httpx.ConnectError as e:
            maybe_raise_cancelled(cancel_file_id, e, kind=cancel_kind)
            raise ValueError(
                f"Cannot connect to LM Studio at {self.base_url}. "
                "Make sure the server is running."
            ) from e
        except httpx.TimeoutException as e:
            maybe_raise_cancelled(cancel_file_id, e, kind=cancel_kind)
            raise ValueError(
                "LM Studio request timed out. The model may still be loading or processing."
            ) from e
        except Exception as e:
            maybe_raise_cancelled(cancel_file_id, e, kind=cancel_kind)
            raise
        finally:
            if cancel_file_id is not None:
                unregister_client(cancel_file_id, client, kind=cancel_kind)
            client.close()

        if response is None:
            if cancel_file_id is not None:
                check_cancelled(cancel_file_id, kind=cancel_kind)
            raise ValueError("LM Studio request ended without a response")

        if response.status_code != 200:
            raise ValueError(
                f"LM Studio API error ({response.status_code}): {response.text[:500]}"
            )

        data = response.json()

        output_items = data.get("output", [])

        # Collect all text from message-type output items
        content_parts: List[str] = []
        for item in output_items:
            if item.get("type") == "message":
                content_parts.append(item.get("content", ""))

        content = "".join(content_parts)

        # If no tool_call items are present the model never ran a real web
        # search, so any URLs in the text are hallucinated — strip them.
        has_tool_calls = any(item.get("type") == "tool_call" for item in output_items)
        if not has_tool_calls:
            stripped = _strip_markdown_links(content)
            if stripped != content:
                logger.info(
                    "Stripped %d fabricated markdown link(s) from LM Studio response "
                    "(no tool_call items in output).",
                    len(_MD_LINK_RE.findall(content)),
                )
            content = stripped

        stats = data.get("stats", {})
        prompt_tokens = int(stats.get("input_tokens", 0))
        completion_tokens = int(stats.get("total_output_tokens", 0))
        used_model = data.get("model_instance_id", model or "lmstudio-local")

        return CompletionResult(
            content=content,
            model=used_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=0.0,
            finish_reason="stop",
        )

    def complete_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: int = LMSTUDIO_DEFAULT_MAX_TOKENS,
        temperature: float = 0.3,
    ) -> Generator[str, None, None]:
        """
        Streaming completion — calls complete() and yields the full content
        as a single chunk.  Proper SSE streaming can be added in a future
        iteration once the exact native-API event format is confirmed.
        """
        result = self.complete(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if result.content:
            yield result.content


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_client: Optional[LMStudioClient] = None


def get_lmstudio_client() -> LMStudioClient:
    """Return the singleton LM Studio client."""
    global _client
    if _client is None:
        _client = LMStudioClient()
    return _client


def set_lmstudio_base_url(url: str):
    """Update the base URL on the singleton client."""
    client = get_lmstudio_client()
    client.set_base_url(url)
    logger.info("LM Studio base URL set to: %s", url)
