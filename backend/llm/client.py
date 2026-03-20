"""
OpenRouter LLM Client

Provides access to multiple LLM models via the OpenRouter API.
Supports model listing, cost estimation, and report generation.

Models are fetched dynamically from the OpenRouter API to ensure
we only show models that are actually available.
"""

import os
import json
import time
import logging
from typing import Optional, List, Dict, Any, Generator, Set
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

# OpenRouter API configuration
OPENROUTER_API_BASE = "https://openrouter.ai/api/v1"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# Cache settings
MODELS_CACHE_TTL_SECONDS = 3600  # 1 hour cache for model list

# Default model for log analysis (using a free model as default)
DEFAULT_MODEL = "google/gemini-2.0-flash-exp:free"

# Recommended models for log analysis with pricing (per million tokens)
# Models are organized: FREE models first, then PAID models by price
RECOMMENDED_MODELS = {
    # === FREE MODELS ===
    "google/gemini-2.0-flash-exp:free": {
        "name": "🆓 Gemini 2.0 Flash (Free)",
        "description": "FREE - Google's latest flash model, great for log analysis",
        "context_length": 1048576,
        "pricing": {"prompt": 0.0, "completion": 0.0},
        "is_free": True,
        "capabilities": ["vision"]
    },
    "meta-llama/llama-3.2-3b-instruct:free": {
        "name": "🆓 Llama 3.2 3B (Free)",
        "description": "FREE - Lightweight Meta model, fast responses",
        "context_length": 131072,
        "pricing": {"prompt": 0.0, "completion": 0.0},
        "is_free": True,
        "capabilities": []
    },
    "qwen/qwen-2.5-7b-instruct:free": {
        "name": "🆓 Qwen 2.5 7B (Free)",
        "description": "FREE - Alibaba's efficient model, good reasoning",
        "context_length": 32768,
        "pricing": {"prompt": 0.0, "completion": 0.0},
        "is_free": True,
        "capabilities": []
    },
    "microsoft/phi-3-mini-128k-instruct:free": {
        "name": "🆓 Phi-3 Mini (Free)",
        "description": "FREE - Microsoft's compact model, 128k context",
        "context_length": 128000,
        "pricing": {"prompt": 0.0, "completion": 0.0},
        "is_free": True,
        "capabilities": []
    },
    "x-ai/grok-4.1-fast:free": {
        "name": "🆓 Grok 4.1 Fast (Free)",
        "description": "FREE - xAI's fast model, 2M context window",
        "context_length": 2000000,
        "pricing": {"prompt": 0.0, "completion": 0.0},
        "is_free": True,
        "capabilities": ["vision"]
    },
    "google/gemma-3n-e2b-it:free": {
        "name": "🆓 Gemma 3n E2B (Free)",
        "description": "FREE - Google's efficient edge model",
        "context_length": 32768,
        "pricing": {"prompt": 0.0, "completion": 0.0},
        "is_free": True,
        "capabilities": []
    },
    "deepseek/deepseek-r1:free": {
        "name": "🆓 DeepSeek R1 (Free)",
        "description": "FREE - Strong reasoning model, great for analysis",
        "context_length": 163840,
        "pricing": {"prompt": 0.0, "completion": 0.0},
        "is_free": True,
        "capabilities": []
    },
    "nousresearch/deephermes-3-llama-3-8b-preview:free": {
        "name": "🆓 DeepHermes 3 8B (Free)",
        "description": "FREE - Nous Research model, good instruction following",
        "context_length": 131072,
        "pricing": {"prompt": 0.0, "completion": 0.0},
        "is_free": True,
        "capabilities": []
    },
    
    # === PAID MODELS (Budget-friendly) ===
    "google/gemini-2.0-flash-001": {
        "name": "💰 Gemini 2.0 Flash",
        "description": "Very cheap - Fast and cost-effective analysis",
        "context_length": 1000000,
        "pricing": {"prompt": 0.10, "completion": 0.40},
        "is_free": False,
        "capabilities": ["vision"]
    },
    "openai/gpt-4o-mini": {
        "name": "💰 GPT-4o Mini",
        "description": "Budget - Balanced speed and quality",
        "context_length": 128000,
        "pricing": {"prompt": 0.15, "completion": 0.60},
        "is_free": False,
        "capabilities": ["vision"]
    },
    "anthropic/claude-3-haiku": {
        "name": "💰 Claude 3 Haiku",
        "description": "Budget - Very fast, good for quick analysis",
        "context_length": 200000,
        "pricing": {"prompt": 0.25, "completion": 1.25},
        "is_free": False,
        "capabilities": ["vision"]
    },
    "meta-llama/llama-3.3-70b-instruct": {
        "name": "💰 Llama 3.3 70B",
        "description": "Budget - Open model, great reasoning",
        "context_length": 131072,
        "pricing": {"prompt": 0.30, "completion": 0.30},
        "is_free": False,
        "capabilities": []
    },
    
    # === PAID MODELS (Premium) ===
    "anthropic/claude-3.5-sonnet": {
        "name": "💎 Claude 3.5 Sonnet",
        "description": "Premium - Excellent reasoning, best for complex logs",
        "context_length": 200000,
        "pricing": {"prompt": 3.00, "completion": 15.00},
        "is_free": False,
        "capabilities": ["vision"]
    },
    "openai/gpt-4o": {
        "name": "💎 GPT-4o",
        "description": "Premium - OpenAI's best model",
        "context_length": 128000,
        "pricing": {"prompt": 2.50, "completion": 10.00},
        "is_free": False,
        "capabilities": ["vision"]
    },
    "mistralai/mistral-large-2411": {
        "name": "💎 Mistral Large",
        "description": "Premium - Strong European model, multilingual",
        "context_length": 128000,
        "pricing": {"prompt": 2.00, "completion": 6.00},
        "is_free": False,
        "capabilities": []
    }
}


@dataclass
class ModelInfo:
    """Information about an LLM model."""
    id: str
    name: str
    description: str
    context_length: int
    prompt_price: float  # Per million tokens
    completion_price: float  # Per million tokens
    
    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost in USD for given token counts."""
        prompt_cost = (prompt_tokens / 1_000_000) * self.prompt_price
        completion_cost = (completion_tokens / 1_000_000) * self.completion_price
        return prompt_cost + completion_cost


@dataclass
class CompletionResult:
    """Result from a completion request."""
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    finish_reason: str


class OpenRouterClient:
    """
    Client for the OpenRouter API.
    
    OpenRouter provides unified access to multiple LLM providers
    (OpenAI, Anthropic, Google, Meta, etc.) through a single API.
    
    Models are fetched dynamically from the API to ensure availability.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the OpenRouter client.
        
        Args:
            api_key: OpenRouter API key. If not provided, reads from OPENROUTER_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.base_url = OPENROUTER_API_BASE
        
        # Model cache with expiration
        self._models_cache: Optional[List[ModelInfo]] = None
        self._models_cache_time: float = 0
        self._available_model_ids: Set[str] = set()
    
    @property
    def is_configured(self) -> bool:
        """Check if the client has an API key configured."""
        return bool(self.api_key)
    
    def set_api_key(self, api_key: str):
        """Set the API key."""
        self.api_key = api_key
        self._invalidate_cache()
    
    def _invalidate_cache(self):
        """Clear the models cache."""
        self._models_cache = None
        self._models_cache_time = 0
        self._available_model_ids = set()
    
    def _is_cache_valid(self) -> bool:
        """Check if the models cache is still valid."""
        if self._models_cache is None:
            return False
        return (time.time() - self._models_cache_time) < MODELS_CACHE_TTL_SECONDS
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        if not self.api_key:
            raise ValueError("OpenRouter API key not configured")
        
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/log-analyzer",  # Required by OpenRouter
            "X-Title": "Log Analyzer"
        }
    
    def refresh_models(self) -> bool:
        """
        Fetch the latest model list from OpenRouter API.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.api_key:
            logger.warning("Cannot refresh models: API key not configured")
            return False
        
        try:
            logger.info("Fetching models from OpenRouter API...")
            with httpx.Client(timeout=15.0) as client:
                response = client.get(
                    OPENROUTER_MODELS_URL,
                    headers=self._get_headers()
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch models: {response.status_code}")
                    return False
                
                data = response.json()
                models = []
                available_ids = set()
                
                for model in data.get("data", []):
                    model_id = model.get("id")
                    if not model_id:
                        continue
                    
                    available_ids.add(model_id)
                    
                    pricing = model.get("pricing", {})
                    # OpenRouter returns pricing as strings in per-token format
                    # Convert to per-million-tokens for display
                    try:
                        prompt_price = float(pricing.get("prompt", "0")) * 1_000_000
                        completion_price = float(pricing.get("completion", "0")) * 1_000_000
                    except (ValueError, TypeError):
                        prompt_price = 0.0
                        completion_price = 0.0
                    
                    models.append(ModelInfo(
                        id=model_id,
                        name=model.get("name", model_id),
                        description=model.get("description", ""),
                        context_length=model.get("context_length", 4096),
                        prompt_price=prompt_price,
                        completion_price=completion_price
                    ))
                
                self._models_cache = models
                self._models_cache_time = time.time()
                self._available_model_ids = available_ids
                
                logger.info(f"Loaded {len(models)} models from OpenRouter")
                return True
                
        except httpx.TimeoutException:
            logger.error("Timeout fetching models from OpenRouter")
            return False
        except Exception as e:
            logger.error(f"Error fetching models: {e}")
            return False
    
    def is_model_available(self, model_id: str) -> bool:
        """
        Check if a specific model is available on OpenRouter.
        
        Args:
            model_id: The model ID to check
            
        Returns:
            True if the model is available, False otherwise
        """
        # Refresh cache if needed
        if not self._is_cache_valid():
            self.refresh_models()
        
        return model_id in self._available_model_ids
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Test the API connection and key validity.
        
        Returns:
            Dict with success status and message
        """
        if not self.api_key:
            return {
                "success": False,
                "message": "API key not configured"
            }
        
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    OPENROUTER_MODELS_URL,
                    headers=self._get_headers()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    model_count = len(data.get("data", []))
                    return {
                        "success": True,
                        "message": f"Connected successfully. {model_count} models available.",
                        "model_count": model_count
                    }
                elif response.status_code == 401:
                    return {
                        "success": False,
                        "message": "Invalid API key"
                    }
                else:
                    return {
                        "success": False,
                        "message": f"API error: {response.status_code}"
                    }
        except httpx.TimeoutException:
            return {
                "success": False,
                "message": "Connection timeout"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Connection error: {str(e)}"
            }
    
    def get_models(self, recommended_only: bool = True) -> List[ModelInfo]:
        """
        Get available models.
        
        Args:
            recommended_only: If True, only return recommended models that are 
                            verified available on OpenRouter.
                            If False, return all models from OpenRouter API.
        
        Returns:
            List of ModelInfo objects
        """
        # Ensure we have fresh model availability data
        if not self._is_cache_valid() and self.api_key:
            self.refresh_models()
        
        if recommended_only:
            # Return recommended models, filtering out unavailable ones
            models = []
            for model_id, info in RECOMMENDED_MODELS.items():
                # Check availability if we have API data
                if self._available_model_ids and model_id not in self._available_model_ids:
                    logger.debug(f"Skipping unavailable model: {model_id}")
                    continue
                
                models.append(ModelInfo(
                    id=model_id,
                    name=info.get("name", model_id),
                    description=info.get("description", ""),
                    context_length=info.get("context_length", 4096),
                    prompt_price=info.get("pricing", {}).get("prompt", 0.0),
                    completion_price=info.get("pricing", {}).get("completion", 0.0)
                ))
            
            # If we filtered out all models, return at least what we have in cache
            if not models and self._models_cache:
                # Return some free models from the full list
                free_models = [m for m in self._models_cache 
                              if m.prompt_price == 0 and m.completion_price == 0]
                return free_models[:10]  # Return up to 10 free models
            
            return models
        
        # Return all models from cache
        if self._models_cache:
            return self._models_cache
        
        # If no cache, try to get recommended models instead
        return self.get_models(recommended_only=True)
    
    def get_model_info(self, model_id: str) -> Optional[ModelInfo]:
        """
        Get info for a specific model.
        
        Args:
            model_id: The model ID to look up
            
        Returns:
            ModelInfo if found, None otherwise
        """
        # First check recommended models (has nice display names)
        if model_id in RECOMMENDED_MODELS:
            info = RECOMMENDED_MODELS[model_id]
            return ModelInfo(
                id=model_id,
                name=info.get("name", model_id),
                description=info.get("description", ""),
                context_length=info.get("context_length", 4096),
                prompt_price=info.get("pricing", {}).get("prompt", 0.0),
                completion_price=info.get("pricing", {}).get("completion", 0.0)
            )
        
        # Check the full model cache
        if self._models_cache:
            for model in self._models_cache:
                if model.id == model_id:
                    return model
        
        # Try to refresh and search again
        if self.api_key and not self._is_cache_valid():
            self.refresh_models()
            if self._models_cache:
                for model in self._models_cache:
                    if model.id == model_id:
                        return model
        
        # Return a basic ModelInfo for unknown models (allows custom models)
        return ModelInfo(
            id=model_id,
            name=model_id,
            description="Custom model",
            context_length=8192,  # Conservative default
            prompt_price=0.0,
            completion_price=0.0
        )
    
    def estimate_cost(
        self,
        model_id: str,
        prompt_tokens: int,
        estimated_completion_tokens: int = 1000
    ) -> Dict[str, Any]:
        """
        Estimate the cost of a completion.
        
        Args:
            model_id: Model ID to use
            prompt_tokens: Number of tokens in the prompt
            estimated_completion_tokens: Estimated completion tokens
        
        Returns:
            Dict with cost estimate details
        """
        model_info = self.get_model_info(model_id) or self.get_model_info(DEFAULT_MODEL)
        
        if not model_info:
            return {
                "model": model_id,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": estimated_completion_tokens,
                "estimated_cost_usd": 0.01,  # Default estimate
                "error": "Model not found"
            }
        
        cost = model_info.estimate_cost(prompt_tokens, estimated_completion_tokens)
        
        return {
            "model": model_id,
            "model_name": model_info.name,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": estimated_completion_tokens,
            "total_tokens": prompt_tokens + estimated_completion_tokens,
            "estimated_cost_usd": round(cost, 6)
        }
    
    def complete(
        self,
        messages: List[Dict[str, str]],
        model: str = DEFAULT_MODEL,
        max_tokens: int = 2000,
        temperature: float = 0.3,
        stream: bool = False,
        web_search: bool = False,
        image_data: Optional[bytes] = None,
        image_mime_type: str = "image/png",
    ) -> CompletionResult:
        """
        Generate a completion.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model ID to use
            max_tokens: Maximum tokens in completion
            temperature: Sampling temperature (0-1)
            stream: Whether to stream the response
            web_search: Whether to enable web search for the model
            image_data: Optional image bytes to include with the user message
            image_mime_type: MIME type of the image (default: image/png)
        
        Returns:
            CompletionResult with the generated content
        """
        if not self.api_key:
            raise ValueError("OpenRouter API key not configured")

        import base64 as _b64

        # If image_data is provided, convert messages to multimodal format
        if image_data:
            b64_str = _b64.b64encode(image_data).decode("utf-8")
            data_url = f"data:{image_mime_type};base64,{b64_str}"
            converted = []
            image_attached = False
            for msg in messages:
                if msg.get("role") == "user" and not image_attached:
                    converted.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": msg.get("content", "")},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ]
                    })
                    image_attached = True
                else:
                    converted.append(msg)
            messages = converted
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream
        }
        
        # Enable web search plugin if requested
        # See: https://openrouter.ai/docs/requests#web-search
        if web_search:
            payload["plugins"] = [{"id": "web", "max_results": 5}]
        
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers=self._get_headers(),
                json=payload
            )
            
            if response.status_code != 200:
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get("error", {}).get("message", error_detail)
                except Exception:
                    pass
                raise Exception(f"OpenRouter API error ({response.status_code}): {error_detail}")
            
            data = response.json()
            
            choice = data["choices"][0]
            usage = data.get("usage", {})
            
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            
            # Calculate cost
            model_info = self.get_model_info(model)
            cost = 0.0
            if model_info:
                cost = model_info.estimate_cost(prompt_tokens, completion_tokens)
            
            return CompletionResult(
                content=choice["message"]["content"],
                model=data.get("model", model),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                cost_usd=round(cost, 6),
                finish_reason=choice.get("finish_reason", "unknown")
            )
    
    def complete_stream(
        self,
        messages: List[Dict[str, str]],
        model: str = DEFAULT_MODEL,
        max_tokens: int = 2000,
        temperature: float = 0.3
    ) -> Generator[str, None, None]:
        """
        Generate a streaming completion.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model ID to use
            max_tokens: Maximum tokens in completion
            temperature: Sampling temperature (0-1)
        
        Yields:
            Content chunks as they are generated
        """
        if not self.api_key:
            raise ValueError("OpenRouter API key not configured")
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True
        }
        
        with httpx.Client(timeout=120.0) as client:
            with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._get_headers(),
                json=payload
            ) as response:
                if response.status_code != 200:
                    raise Exception(f"OpenRouter API error: {response.status_code}")
                
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            if "content" in delta:
                                yield delta["content"]
                        except json.JSONDecodeError:
                            continue


# Singleton instance
_client: Optional[OpenRouterClient] = None


def get_llm_client() -> OpenRouterClient:
    """Get the singleton LLM client instance."""
    global _client
    if _client is None:
        _client = OpenRouterClient()
    return _client


def set_api_key(api_key: str):
    """Set the API key for the singleton client."""
    client = get_llm_client()
    client.set_api_key(api_key)


def openrouter_model_supports_vision(model_id: str) -> bool:
    """Check if an OpenRouter model supports vision/image input."""
    info = RECOMMENDED_MODELS.get(model_id, {})
    return "vision" in info.get("capabilities", [])

