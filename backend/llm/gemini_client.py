"""
Google Gemini API Client

Provides access to Gemini models via the Google AI Studio API.
Free tier includes 500 requests/day and 1M tokens/minute.

Reference: https://ai.google.dev/gemini-api/docs/models
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# Gemini API configuration
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Default model - Gemini 2.5 Flash has excellent free tier
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

# Available Gemini models with their specs
# Reference: https://ai.google.dev/gemini-api/docs/models
GEMINI_MODELS = {
    # Latest and most capable
    "gemini-2.5-flash": {
        "name": "Gemini 2.5 Flash",
        "description": "Best price-performance, great for large scale processing and agentic tasks",
        "context_length": 1048576,
        "output_limit": 65536,
        "pricing": {"prompt": 0.0, "completion": 0.0},  # Free tier available
        "is_free": True,
        "capabilities": ["thinking", "code_execution", "function_calling", "search_grounding", "vision"]
    },
    "gemini-2.0-flash": {
        "name": "Gemini 2.0 Flash",
        "description": "Fast multimodal model with 1M context, Live API support",
        "context_length": 1048576,
        "output_limit": 8192,
        "pricing": {"prompt": 0.0, "completion": 0.0},
        "is_free": True,
        "capabilities": ["live_api", "code_execution", "function_calling", "search_grounding", "vision"]
    },
    "gemini-2.0-flash-lite": {
        "name": "Gemini 2.0 Flash-Lite",
        "description": "Cost-efficient and low latency, 1M context",
        "context_length": 1048576,
        "output_limit": 8192,
        "pricing": {"prompt": 0.0, "completion": 0.0},
        "is_free": True,
        "capabilities": ["function_calling", "structured_outputs", "vision"]
    },
    "gemini-1.5-flash": {
        "name": "Gemini 1.5 Flash",
        "description": "Fast and versatile, good for most tasks",
        "context_length": 1048576,
        "output_limit": 8192,
        "pricing": {"prompt": 0.0, "completion": 0.0},
        "is_free": True,
        "capabilities": ["code_execution", "function_calling", "search_grounding", "vision"]
    },
    "gemini-1.5-pro": {
        "name": "Gemini 1.5 Pro",
        "description": "Complex reasoning tasks, 2M context window",
        "context_length": 2097152,
        "output_limit": 8192,
        "pricing": {"prompt": 1.25, "completion": 5.00},  # Per million tokens
        "is_free": False,
        "capabilities": ["code_execution", "function_calling", "search_grounding", "vision"]
    },
}


@dataclass
class GeminiCompletionResult:
    """Result from a Gemini completion request."""
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    finish_reason: str


@dataclass
class GeminiModelInfo:
    """Information about a Gemini model."""
    id: str
    name: str
    description: str
    context_length: int
    output_limit: int
    prompt_price: float  # Per million tokens
    completion_price: float
    is_free: bool
    capabilities: List[str]
    
    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost for given token counts."""
        if self.is_free:
            return 0.0
        prompt_cost = (prompt_tokens / 1_000_000) * self.prompt_price
        completion_cost = (completion_tokens / 1_000_000) * self.completion_price
        return prompt_cost + completion_cost


class GeminiClient:
    """
    Client for the Google Gemini API.
    
    Usage:
        client = GeminiClient()
        client.set_api_key("your-api-key")
        result = client.complete(messages=[...], model="gemini-2.5-flash")
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.base_url = GEMINI_API_BASE
    
    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)
    
    def set_api_key(self, api_key: str):
        """Set the API key."""
        self.api_key = api_key
    
    def get_models(self) -> List[GeminiModelInfo]:
        """Get list of available Gemini models."""
        models = []
        for model_id, info in GEMINI_MODELS.items():
            models.append(GeminiModelInfo(
                id=model_id,
                name=info["name"],
                description=info["description"],
                context_length=info["context_length"],
                output_limit=info["output_limit"],
                prompt_price=info["pricing"]["prompt"],
                completion_price=info["pricing"]["completion"],
                is_free=info["is_free"],
                capabilities=info.get("capabilities", [])
            ))
        # Sort: free first, then by name
        models.sort(key=lambda x: (not x.is_free, x.name))
        return models
    
    def get_model_info(self, model_id: str) -> Optional[GeminiModelInfo]:
        """Get info for a specific model."""
        if model_id in GEMINI_MODELS:
            info = GEMINI_MODELS[model_id]
            return GeminiModelInfo(
                id=model_id,
                name=info["name"],
                description=info["description"],
                context_length=info["context_length"],
                output_limit=info["output_limit"],
                prompt_price=info["pricing"]["prompt"],
                completion_price=info["pricing"]["completion"],
                is_free=info["is_free"],
                capabilities=info.get("capabilities", [])
            )
        return None
    
    def test_connection(self) -> bool:
        """Test if the API key is valid."""
        if not self.api_key:
            return False
        
        try:
            # Try to list models as a simple test
            url = f"{self.base_url}/models?key={self.api_key}"
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url)
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Gemini connection test failed: {e}")
            return False
    
    def complete(
        self,
        messages: List[Dict[str, str]],
        model: str = DEFAULT_GEMINI_MODEL,
        max_tokens: int = 2000,
        temperature: float = 0.3,
        web_search: bool = False,
        image_data: Optional[bytes] = None,
        image_mime_type: str = "image/png",
        cancel_file_id: Optional[int] = None,
        cancel_kind: str = "report",
    ) -> GeminiCompletionResult:
        """
        Generate a completion using Gemini.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model ID to use
            max_tokens: Maximum tokens in completion
            temperature: Sampling temperature (0-2)
            web_search: Enable Google Search grounding
            image_data: Optional image bytes to include with the user message
            image_mime_type: MIME type of the image (default: image/png)
        
        Returns:
            GeminiCompletionResult with the generated content
        """
        if not self.api_key:
            raise ValueError("Gemini API key not configured")
        
        import base64 as _b64

        # Convert OpenAI-style messages to Gemini format
        contents = []
        system_instruction = None
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                system_instruction = content
            elif role == "assistant":
                contents.append({
                    "role": "model",
                    "parts": [{"text": content}]
                })
            else:  # user
                parts = [{"text": content}]
                if image_data and role == "user":
                    parts.append({
                        "inlineData": {
                            "mimeType": image_mime_type,
                            "data": _b64.b64encode(image_data).decode("utf-8"),
                        }
                    })
                    image_data = None  # only attach to the first user message
                contents.append({
                    "role": "user",
                    "parts": parts,
                })
        
        # Build request payload
        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            }
        }
        
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }
        
        # Enable Google Search grounding if requested
        if web_search:
            payload["tools"] = [{"googleSearch": {}}]
        
        # Make API request
        url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"
        
        logger.info(f"Calling Gemini API: model={model}, max_tokens={max_tokens}")

        from backend.llm.generation_cancel import (
            check_cancelled,
            maybe_raise_cancelled,
            register_client,
            unregister_client,
        )

        client = httpx.Client(timeout=120.0)
        if cancel_file_id is not None:
            register_client(cancel_file_id, client, kind=cancel_kind)
        response = None
        try:
            if cancel_file_id is not None:
                check_cancelled(cancel_file_id, kind=cancel_kind)
            response = client.post(url, json=payload)
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
            raise Exception("Gemini request ended without a response")

        try:
            if response.status_code != 200:
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get("error", {}).get("message", error_detail)
                except Exception:
                    pass
                logger.error(f"Gemini API error ({response.status_code}): {error_detail}")
                raise Exception(f"Gemini API error ({response.status_code}): {error_detail}")

            data = response.json()

            # Extract response
            candidates = data.get("candidates", [])
            if not candidates:
                raise Exception("No response candidates from Gemini")

            candidate = candidates[0]
            content_parts = candidate.get("content", {}).get("parts", [])
            content = "".join(p.get("text", "") for p in content_parts)
            finish_reason = candidate.get("finishReason", "STOP")

            # Get token counts
            usage = data.get("usageMetadata", {})
            prompt_tokens = usage.get("promptTokenCount", 0)
            completion_tokens = usage.get("candidatesTokenCount", 0)
            total_tokens = usage.get("totalTokenCount", prompt_tokens + completion_tokens)

            # Calculate cost
            model_info = self.get_model_info(model)
            cost = 0.0
            if model_info:
                cost = model_info.estimate_cost(prompt_tokens, completion_tokens)

            logger.info(f"Gemini response: {prompt_tokens} prompt + {completion_tokens} completion tokens, finish_reason={finish_reason}")

            if completion_tokens == 0 and finish_reason != "STOP":
                logger.warning(
                    f"Gemini returned 0 completion tokens with finish_reason={finish_reason}. "
                    f"Candidate: {json.dumps(candidate, default=str)[:500]}"
                )

            return GeminiCompletionResult(
                content=content,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=round(cost, 6),
                finish_reason=finish_reason
            )

        except httpx.TimeoutException as e:
            maybe_raise_cancelled(cancel_file_id, e, kind=cancel_kind)
            logger.error("Gemini API request timed out")
            raise Exception("Gemini API request timed out") from e
        except Exception as e:
            maybe_raise_cancelled(cancel_file_id, e, kind=cancel_kind)
            logger.error(f"Gemini API error: {e}")
            raise


# Singleton instance
_gemini_client: Optional[GeminiClient] = None


def get_gemini_client() -> GeminiClient:
    """Get the singleton Gemini client instance."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = GeminiClient()
    return _gemini_client


def set_gemini_api_key(api_key: str):
    """Set the API key for the singleton client."""
    client = get_gemini_client()
    client.set_api_key(api_key)


def gemini_model_supports_vision(model_id: str) -> bool:
    """Check if a Gemini model supports vision/image input."""
    info = GEMINI_MODELS.get(model_id, {})
    return "vision" in info.get("capabilities", [])

