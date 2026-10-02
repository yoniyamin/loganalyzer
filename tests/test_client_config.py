"""Tests for LLM client credential sync from DB."""
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import LLMConfig
from backend.llm.client_config import ensure_gemini_configured, sync_llm_clients_from_db
from backend.llm.gemini_client import get_gemini_client


class TestClientConfigSync:
    def test_sync_gemini_key_from_db(self, tmp_db):
        db = tmp_db
        encoded = base64.b64encode(b"test-gemini-key").decode()
        cfg = LLMConfig(provider="gemini", gemini_api_key_encrypted=encoded)
        db.add(cfg)
        db.commit()

        get_gemini_client().set_api_key("")
        sync_llm_clients_from_db(db)
        assert get_gemini_client().is_configured
        assert ensure_gemini_configured(db)
