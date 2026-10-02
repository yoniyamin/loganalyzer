"""Sync persisted LLM provider credentials into process singleton clients."""

from __future__ import annotations

import base64
import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from backend.database import LLMConfig
from backend.llm.client import get_llm_client, set_api_key
from backend.llm.gemini_client import get_gemini_client, set_gemini_api_key
from backend.llm.openai_api_client import (
    DEFAULT_OPENAI_API_BASE_URL,
    get_openai_api_client,
)
from backend.llm.lmstudio_client import DEFAULT_LMSTUDIO_BASE_URL, get_lmstudio_client

logger = logging.getLogger(__name__)

PROVIDER_GEMINI = "gemini"
PROVIDER_OPENROUTER = "openrouter"
PROVIDER_LMSTUDIO = "lmstudio"
PROVIDER_OPENAI_API = "openai_api"


def _decode_api_key(encoded: str) -> Optional[str]:
    try:
        return base64.b64decode(encoded.encode()).decode().strip()
    except Exception:
        return None


def sync_llm_clients_from_db(db: Session) -> None:
    """Load API keys and local server URLs from ``llm_config`` into singleton clients."""
    config = db.query(LLMConfig).first()
    if not config:
        return

    if config.gemini_api_key_encrypted:
        key = _decode_api_key(config.gemini_api_key_encrypted)
        if key:
            set_gemini_api_key(key)

    if config.api_key_encrypted:
        key = _decode_api_key(config.api_key_encrypted)
        if key:
            set_api_key(key)

    lmstudio_url = getattr(config, "lmstudio_base_url", None) or DEFAULT_LMSTUDIO_BASE_URL
    get_lmstudio_client().set_base_url(lmstudio_url)

    oa_url = getattr(config, "openai_api_base_url", None) or DEFAULT_OPENAI_API_BASE_URL
    oa_client = get_openai_api_client()
    oa_client.set_base_url(oa_url)
    encrypted_oa_key = getattr(config, "openai_api_key_encrypted", None)
    if encrypted_oa_key:
        oa_key = _decode_api_key(encrypted_oa_key)
        if oa_key:
            oa_client.set_api_key(oa_key)

    tavily_encrypted = getattr(config, "tavily_api_key_encrypted", None)
    if tavily_encrypted:
        tavily_key = _decode_api_key(tavily_encrypted)
        if tavily_key:
            os.environ["TAVILY_API_KEY"] = tavily_key


def ensure_gemini_configured(db: Session) -> bool:
    sync_llm_clients_from_db(db)
    return get_gemini_client().is_configured


def ensure_openrouter_configured(db: Session) -> bool:
    sync_llm_clients_from_db(db)
    return get_llm_client().is_configured
