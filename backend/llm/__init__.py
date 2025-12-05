"""
LLM Integration Module for Log Analyzer

Provides AI-powered log analysis using OpenRouter API and ChromaDB for RAG.
"""

from backend.llm.models import (
    LLMConfigRequest,
    LLMConfigResponse,
    LLMReportRequest,
    LLMReportResponse,
    ModelInfo,
    TestConnectionResponse,
)

__all__ = [
    "LLMConfigRequest",
    "LLMConfigResponse", 
    "LLMReportRequest",
    "LLMReportResponse",
    "ModelInfo",
    "TestConnectionResponse",
]

