"""
Pydantic models for LLM integration API requests and responses.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class LLMConfigRequest(BaseModel):
    """Request to save LLM configuration."""
    api_key: str = Field(..., description="OpenRouter API key")
    default_model: Optional[str] = Field(
        default="google/gemini-2.0-flash-001",
        description="Default model to use for report generation"
    )


class LLMConfigResponse(BaseModel):
    """Response containing current LLM configuration."""
    is_configured: bool
    default_model: Optional[str] = None
    api_key_preview: Optional[str] = None  # e.g., "sk-or-...abc"
    updated_at: Optional[datetime] = None


class ModelInfo(BaseModel):
    """Information about an available LLM model."""
    id: str
    name: str
    description: Optional[str] = None
    context_length: int
    pricing: dict  # {"prompt": float, "completion": float} per million tokens
    

class ModelListResponse(BaseModel):
    """Response containing list of available models."""
    models: List[ModelInfo]


class TestConnectionResponse(BaseModel):
    """Response from testing API connection."""
    success: bool
    message: str
    model_count: Optional[int] = None


class LLMReportRequest(BaseModel):
    """Request to generate an LLM report."""
    model: Optional[str] = None  # If None, use default model
    regenerate: bool = Field(
        default=False,
        description="Force regeneration even if cached report exists"
    )


class LLMReportResponse(BaseModel):
    """Response containing generated LLM report."""
    file_id: int
    model_used: str
    report_content: str  # Markdown formatted report
    prompt_tokens: int
    completion_tokens: int
    estimated_cost: float  # In USD
    generated_at: datetime
    cached: bool = False  # True if returned from cache


class CostEstimate(BaseModel):
    """Cost estimate for generating a report."""
    estimated_tokens: int
    estimated_cost_usd: float
    model: str


class EmbeddingStats(BaseModel):
    """Statistics about embedded content for a log file."""
    file_id: int
    summary_chunks: int
    error_chunks: int
    anomaly_chunks: int
    total_chunks: int
    last_embedded_at: Optional[datetime] = None

