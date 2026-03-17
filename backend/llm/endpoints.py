"""
LLM API Endpoints

Provides REST API endpoints for LLM configuration and report generation.
Mounted at /api/llm/
"""

import base64
import io
import os
import re
import logging
import traceback
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import text
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database import get_db, LLMConfig, LLMReport, LogFile, KBArticle
from backend.llm.client import get_llm_client, set_api_key, DEFAULT_MODEL
from backend.llm.gemini_client import get_gemini_client, set_gemini_api_key, DEFAULT_GEMINI_MODEL, GEMINI_MODELS
from backend.llm.report_generator import ReportGenerator
from backend.llm.vectorstore import get_vector_store
from backend.llm.error_resolution import resolve_issue

# Configure logging
logger = logging.getLogger(__name__)

# Provider constants
PROVIDER_GEMINI = "gemini"
PROVIDER_OPENROUTER = "openrouter"


router = APIRouter(prefix="/llm", tags=["LLM"])


# ============================================================
# Pydantic Models for API
# ============================================================

class ConfigRequest(BaseModel):
    """Request to save LLM configuration."""
    provider: Optional[str] = "gemini"  # "gemini" or "openrouter"
    gemini_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    tavily_api_key: Optional[str] = None
    default_model: Optional[str] = None  # Provider-specific model ID
    web_search_enabled: Optional[bool] = None  # Enable web search in reports


class ConfigResponse(BaseModel):
    """Response with current LLM configuration."""
    is_configured: bool
    provider: str = "gemini"
    default_model: Optional[str] = None
    gemini_configured: bool = False
    openrouter_configured: bool = False
    gemini_api_key_preview: Optional[str] = None
    openrouter_api_key_preview: Optional[str] = None
    tavily_configured: bool = False
    tavily_api_key_preview: Optional[str] = None
    web_search_enabled: bool = False
    updated_at: Optional[datetime] = None


class TestConnectionResponse(BaseModel):
    """Response from testing API connection."""
    success: bool
    message: str
    model_count: Optional[int] = None


class ModelInfo(BaseModel):
    """Information about an available model."""
    id: str
    name: str
    description: Optional[str] = None
    context_length: int
    prompt_price: float
    completion_price: float
    is_free: bool = False
    provider: str = "gemini"


class ModelsResponse(BaseModel):
    """Response containing available models."""
    provider: str
    models: List[ModelInfo]


class IssueResolveRequest(BaseModel):
    """Request to resolve a specific error/issue."""
    message_summary: str
    error_code: Optional[str] = None
    line_number: Optional[int] = None
    component: Optional[str] = None
    context_snippet: Optional[str] = None
    full_error_text: Optional[str] = None  # Full error line for better search
    custom_query: Optional[str] = None  # User-edited search query
    search: bool = False


class ReportRequest(BaseModel):
    """Request to generate a report."""
    model: Optional[str] = None
    regenerate: bool = False
    quick: bool = False
    web_search: bool = False  # Enable web search for additional context


class ReportResponse(BaseModel):
    """Response containing generated report."""
    report_id: Optional[int] = None
    file_id: int
    model_used: str
    report_content: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    generated_at: datetime
    cached: bool = False


class ReportHistoryItem(BaseModel):
    """Summary of a report for history list."""
    report_id: int
    model_used: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    generated_at: datetime


class ReportHistoryResponse(BaseModel):
    """Response containing report history for a file."""
    file_id: int
    reports: List[ReportHistoryItem]
    total_count: int


class CostEstimateResponse(BaseModel):
    """Cost estimate for generating a report."""
    model: str
    model_name: Optional[str] = None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class EmbeddingStatsResponse(BaseModel):
    """Statistics about embeddings for a file."""
    file_id: int
    summaries: int
    errors: int
    anomalies: int
    total: int


# ============================================================
# Helper Functions
# ============================================================

def _encode_api_key(api_key: str) -> str:
    """Simple encoding for API key storage (not secure, just obfuscation)."""
    return base64.b64encode(api_key.encode()).decode()


def _decode_api_key(encoded: str) -> str:
    """Decode the API key."""
    return base64.b64decode(encoded.encode()).decode()


def _get_api_key_preview(api_key: str) -> str:
    """Get a preview of the API key (first 8 and last 4 chars)."""
    if len(api_key) > 12:
        return f"{api_key[:8]}...{api_key[-4:]}"
    return "***"


def _ensure_tavily_column(db: Session):
    """Ensure tavily_api_key_encrypted column exists to avoid migration errors."""
    try:
        db.execute(text("SELECT tavily_api_key_encrypted FROM llm_config LIMIT 1"))
    except Exception:
        try:
            db.execute(text("ALTER TABLE llm_config ADD COLUMN tavily_api_key_encrypted VARCHAR"))
            db.commit()
        except Exception as e:
            logger.warning("Failed to add tavily_api_key_encrypted column: %s", e)


def _load_tavily_api_key(db: Session) -> Optional[str]:
    """Load Tavily API key from DB or env."""
    _ensure_tavily_column(db)
    config = db.query(LLMConfig).first()
    if not config:
        return os.environ.get("TAVILY_API_KEY")
    if config.tavily_api_key_encrypted:
        try:
            return _decode_api_key(config.tavily_api_key_encrypted)
        except Exception:
            return os.environ.get("TAVILY_API_KEY")
    return os.environ.get("TAVILY_API_KEY")


def _load_api_key_from_db(db: Session, provider: str = PROVIDER_OPENROUTER) -> Optional[str]:
    """Load and decode API key from database for the specified provider."""
    config = db.query(LLMConfig).first()
    if not config:
        return None
    
    if provider == PROVIDER_GEMINI:
        if config.gemini_api_key_encrypted:
            try:
                return _decode_api_key(config.gemini_api_key_encrypted)
            except Exception:
                pass
    else:
        if config.api_key_encrypted:
            try:
                return _decode_api_key(config.api_key_encrypted)
            except Exception:
                pass
    return None


def _ensure_client_configured(db: Session):
    """Ensure the OpenRouter LLM client has the API key loaded."""
    client = get_llm_client()
    if not client.is_configured:
        api_key = _load_api_key_from_db(db, PROVIDER_OPENROUTER)
        if api_key:
            set_api_key(api_key)


def _ensure_gemini_configured(db: Session):
    """Ensure the Gemini client has the API key loaded."""
    client = get_gemini_client()
    if not client.is_configured:
        api_key = _load_api_key_from_db(db, PROVIDER_GEMINI)
        if api_key:
            set_gemini_api_key(api_key)


# ============================================================
# Configuration Endpoints
# ============================================================

@router.get("/config", response_model=ConfigResponse)
def get_config(db: Session = Depends(get_db)):
    """Get current LLM configuration status."""
    _ensure_tavily_column(db)
    config = db.query(LLMConfig).first()
    
    if not config:
        return ConfigResponse(
            is_configured=False,
            provider=PROVIDER_GEMINI,
            default_model=DEFAULT_GEMINI_MODEL,
            gemini_configured=False,
            openrouter_configured=False,
            tavily_configured=False
        )
    
    # Check which providers are configured
    gemini_configured = bool(config.gemini_api_key_encrypted)
    openrouter_configured = bool(config.api_key_encrypted)
    tavily_configured = bool(getattr(config, "tavily_api_key_encrypted", None))
    
    # Get API key previews
    gemini_preview = None
    openrouter_preview = None
    tavily_preview = None
    
    if gemini_configured:
        try:
            gemini_key = _decode_api_key(config.gemini_api_key_encrypted)
            gemini_preview = _get_api_key_preview(gemini_key)
        except Exception:
            gemini_preview = "***"
    
    if openrouter_configured:
        try:
            openrouter_key = _decode_api_key(config.api_key_encrypted)
            openrouter_preview = _get_api_key_preview(openrouter_key)
        except Exception:
            openrouter_preview = "***"
    
    if tavily_configured and getattr(config, "tavily_api_key_encrypted", None):
        try:
            tavily_key = _decode_api_key(config.tavily_api_key_encrypted)
            tavily_preview = _get_api_key_preview(tavily_key)
        except Exception:
            tavily_preview = "***"
    
    # Determine if configured based on selected provider
    provider = config.provider or PROVIDER_GEMINI
    is_configured = (provider == PROVIDER_GEMINI and gemini_configured) or \
                   (provider == PROVIDER_OPENROUTER and openrouter_configured)
    
    return ConfigResponse(
        is_configured=is_configured,
        provider=provider,
        default_model=config.default_model or (DEFAULT_GEMINI_MODEL if provider == PROVIDER_GEMINI else DEFAULT_MODEL),
        gemini_configured=gemini_configured,
        openrouter_configured=openrouter_configured,
        gemini_api_key_preview=gemini_preview,
        openrouter_api_key_preview=openrouter_preview,
        tavily_configured=tavily_configured,
        tavily_api_key_preview=tavily_preview,
        web_search_enabled=config.web_search_enabled or False,
        updated_at=config.updated_at
    )


@router.post("/config", response_model=ConfigResponse)
def save_config(request: ConfigRequest, db: Session = Depends(get_db)):
    """Save LLM configuration (API keys and preferences)."""
    _ensure_tavily_column(db)
    # Get or create config
    config = db.query(LLMConfig).first()
    if not config:
        config = LLMConfig()
        db.add(config)
    
    # Update provider
    if request.provider:
        config.provider = request.provider
    
    # Update Gemini API key
    if request.gemini_api_key:
        if len(request.gemini_api_key) < 10:
            raise HTTPException(status_code=400, detail="Invalid Gemini API key")
        config.gemini_api_key_encrypted = _encode_api_key(request.gemini_api_key)
        set_gemini_api_key(request.gemini_api_key)
    
    # Update OpenRouter API key
    if request.openrouter_api_key:
        if len(request.openrouter_api_key) < 10:
            raise HTTPException(status_code=400, detail="Invalid OpenRouter API key")
        config.api_key_encrypted = _encode_api_key(request.openrouter_api_key)
        set_api_key(request.openrouter_api_key)

    # Update Tavily API key
    if request.tavily_api_key:
        if len(request.tavily_api_key) < 10:
            raise HTTPException(status_code=400, detail="Invalid Tavily API key")
        config.tavily_api_key_encrypted = _encode_api_key(request.tavily_api_key)
    
    # Validate that selected provider has a key
    provider = request.provider or config.provider or PROVIDER_GEMINI
    if provider == PROVIDER_GEMINI and not config.gemini_api_key_encrypted and not request.gemini_api_key:
        raise HTTPException(status_code=400, detail="Gemini API key required")
    if provider == PROVIDER_OPENROUTER and not config.api_key_encrypted and not request.openrouter_api_key:
        raise HTTPException(status_code=400, detail="OpenRouter API key required")
    
    # Update default model
    if request.default_model:
        config.default_model = request.default_model
    elif not config.default_model:
        # Set default based on provider
        config.default_model = DEFAULT_GEMINI_MODEL if provider == PROVIDER_GEMINI else DEFAULT_MODEL
    
    # Update web search setting
    if request.web_search_enabled is not None:
        config.web_search_enabled = request.web_search_enabled
    
    config.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(config)
    
    # Build response
    gemini_configured = bool(config.gemini_api_key_encrypted)
    openrouter_configured = bool(config.api_key_encrypted)
    tavily_configured = bool(getattr(config, "tavily_api_key_encrypted", None))
    
    gemini_preview = None
    openrouter_preview = None
    tavily_preview = None
    
    if gemini_configured:
        try:
            gemini_preview = _get_api_key_preview(_decode_api_key(config.gemini_api_key_encrypted))
        except Exception:
            gemini_preview = "***"
    
    if openrouter_configured:
        try:
            openrouter_preview = _get_api_key_preview(_decode_api_key(config.api_key_encrypted))
        except Exception:
            openrouter_preview = "***"
    
    if tavily_configured and getattr(config, "tavily_api_key_encrypted", None):
        try:
            tavily_preview = _get_api_key_preview(_decode_api_key(config.tavily_api_key_encrypted))
        except Exception:
            tavily_preview = "***"
    
    return ConfigResponse(
        is_configured=True,
        provider=config.provider,
        default_model=config.default_model,
        gemini_configured=gemini_configured,
        openrouter_configured=openrouter_configured,
        gemini_api_key_preview=gemini_preview,
        openrouter_api_key_preview=openrouter_preview,
        tavily_configured=tavily_configured,
        tavily_api_key_preview=tavily_preview,
        web_search_enabled=config.web_search_enabled or False,
        updated_at=config.updated_at
    )


@router.post("/config/test", response_model=TestConnectionResponse)
def test_connection(
    provider: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Test the API connection with the configured key."""
    config = db.query(LLMConfig).first()
    test_provider = provider or (config.provider if config else PROVIDER_GEMINI)
    
    if test_provider == PROVIDER_GEMINI:
        _ensure_gemini_configured(db)
        client = get_gemini_client()
        if not client.is_configured:
            return TestConnectionResponse(
                success=False,
                message="Gemini API key not configured"
            )
        success = client.test_connection()
        return TestConnectionResponse(
            success=success,
            message="Gemini connection successful" if success else "Gemini connection failed",
            model_count=len(GEMINI_MODELS) if success else None
        )
    else:
        _ensure_client_configured(db)
        client = get_llm_client()
        if not client.is_configured:
            return TestConnectionResponse(
                success=False,
                message="OpenRouter API key not configured"
            )
        result = client.test_connection()
        return TestConnectionResponse(
            success=result["success"],
            message=result["message"],
            model_count=result.get("model_count")
        )


# ============================================================
# Issue Resolution Endpoint
# ============================================================


@router.post("/issues/{file_id}/resolve")
def resolve_issue_endpoint(
    file_id: int,
    request: IssueResolveRequest,
    db: Session = Depends(get_db)
):
    """Resolve a specific issue by aggregating KB, AI report, and Tavily."""
    _ensure_tavily_column(db)
    file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    # Always check if Tavily is configured
    tavily_key_available = _load_tavily_api_key(db)
    tavily_key = tavily_key_available if request.search else None

    result = resolve_issue(
        db,
        file_id,
        message_summary=request.message_summary,
        error_code=request.error_code,
        context_snippet=request.context_snippet,
        component=request.component,
        tavily_api_key=tavily_key,
        full_error_text=request.full_error_text,
        custom_query=request.custom_query,
    )

    # Add Tavily config status (separate from whether search was run)
    result["tavily_configured"] = bool(tavily_key_available)
    result["search_requested"] = request.search

    # Echo inputs for client convenience
    result["file_id"] = file_id
    result["line_number"] = request.line_number
    result["component"] = request.component
    result["error_code"] = request.error_code
    return result


# ============================================================
# Models Endpoint
# ============================================================

@router.get("/models", response_model=ModelsResponse)
def get_models(
    provider: Optional[str] = None,
    recommended_only: bool = True,
    refresh: bool = False,
    db: Session = Depends(get_db)
):
    """
    Get available LLM models for the specified provider.
    
    Args:
        provider: 'gemini' or 'openrouter'. Uses configured default if not specified.
        recommended_only: If True, return only recommended models. If False, return all.
        refresh: If True, force refresh the model list from the API (OpenRouter only).
    """
    config = db.query(LLMConfig).first()
    use_provider = provider or (config.provider if config else PROVIDER_GEMINI)
    
    if use_provider == PROVIDER_GEMINI:
        # Return Gemini models
        gemini_client = get_gemini_client()
        models = gemini_client.get_models()
        return ModelsResponse(
            provider=PROVIDER_GEMINI,
            models=[
                ModelInfo(
                    id=m.id,
                    name=m.name,
                    description=m.description,
                    context_length=m.context_length,
                    prompt_price=m.prompt_price,
                    completion_price=m.completion_price,
                    is_free=m.is_free,
                    provider=PROVIDER_GEMINI
                )
                for m in models
            ]
        )
    else:
        # Return OpenRouter models
        _ensure_client_configured(db)
        client = get_llm_client()
        
        # Force refresh if requested
        if refresh:
            logger.info("Refreshing OpenRouter models list...")
            client.refresh_models()
        
        models = client.get_models(recommended_only=recommended_only)
        return ModelsResponse(
            provider=PROVIDER_OPENROUTER,
            models=[
                ModelInfo(
                    id=m.id,
                    name=m.name,
                    description=m.description,
                    context_length=m.context_length,
                    prompt_price=m.prompt_price,
                    completion_price=m.completion_price,
                    is_free=m.prompt_price == 0 and m.completion_price == 0,
                    provider=PROVIDER_OPENROUTER
                )
                for m in models
            ]
        )


# ============================================================
# Report Endpoints
# ============================================================

@router.get("/report/{file_id}")
def get_report(
    file_id: int,
    db: Session = Depends(get_db)
):
    """Get existing report for a file (without generating).
    
    Returns {"exists": False} if no report exists, allowing frontend
    to decide whether to auto-generate.
    """
    # Check file exists
    file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Get cached report (most recent)
    existing = db.query(LLMReport).filter(
        LLMReport.file_id == file_id
    ).order_by(LLMReport.generated_at.desc()).first()
    
    if not existing:
        return {"exists": False, "file_id": file_id}
    
    return {
        "exists": True,
        "report_id": existing.id,
        "file_id": existing.file_id,
        "model_used": existing.model_used,
        "report_content": existing.report_content,
        "prompt_tokens": existing.prompt_tokens,
        "completion_tokens": existing.completion_tokens,
        "cost_usd": existing.cost_usd,
        "generated_at": existing.generated_at.isoformat() if existing.generated_at else None,
        "cached": True
    }


@router.post("/report/{file_id}", response_model=ReportResponse)
def generate_report(
    file_id: int,
    request: ReportRequest,
    db: Session = Depends(get_db)
):
    """Generate an LLM analysis report for a log file."""
    # Ensure both clients are configured
    _ensure_client_configured(db)
    _ensure_gemini_configured(db)
    
    # Check file exists
    file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    if file.status != "ready":
        raise HTTPException(status_code=400, detail="File is not ready for analysis")
    
    # Check for cached report if not forcing regeneration
    if not request.regenerate:
        existing = db.query(LLMReport).filter(
            LLMReport.file_id == file_id
        ).order_by(LLMReport.generated_at.desc()).first()
        
        if existing:
            return ReportResponse(
                report_id=existing.id,
                file_id=existing.file_id,
                model_used=existing.model_used,
                report_content=existing.report_content,
                prompt_tokens=existing.prompt_tokens,
                completion_tokens=existing.completion_tokens,
                cost_usd=existing.cost_usd,
                generated_at=existing.generated_at,
                cached=True
            )
    
    # Get default model if not specified
    model = request.model
    if not model:
        config = db.query(LLMConfig).first()
        model = config.default_model if config else DEFAULT_MODEL
    
    # Generate report
    try:
        logger.info(f"Generating report for file_id={file_id}, model={model}")
        generator = ReportGenerator(db)
        result = generator.generate_report(
            file_id=file_id,
            model=model,
            quick=request.quick,
            web_search=request.web_search
        )
        logger.info(f"Report generated successfully for file_id={file_id}")
    except ValueError as e:
        logger.error(f"ValueError during report generation: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during report generation: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")
    
    # Save report to database
    report = LLMReport(
        file_id=file_id,
        model_used=result["model_used"],
        prompt_tokens=result["prompt_tokens"],
        completion_tokens=result["completion_tokens"],
        cost_usd=result["cost_usd"],
        report_content=result["report_content"],
        generated_at=datetime.utcnow()
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    
    return ReportResponse(
        report_id=report.id,
        file_id=report.file_id,
        model_used=report.model_used,
        report_content=report.report_content,
        prompt_tokens=report.prompt_tokens,
        completion_tokens=report.completion_tokens,
        cost_usd=report.cost_usd,
        generated_at=report.generated_at,
        cached=False
    )


@router.get("/report/{file_id}/history", response_model=ReportHistoryResponse)
def get_report_history(file_id: int, db: Session = Depends(get_db)):
    """Get all reports for a file (history)."""
    # Check file exists
    file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Get all reports ordered by date (newest first)
    reports = db.query(LLMReport).filter(
        LLMReport.file_id == file_id
    ).order_by(LLMReport.generated_at.desc()).all()
    
    return ReportHistoryResponse(
        file_id=file_id,
        reports=[
            ReportHistoryItem(
                report_id=r.id,
                model_used=r.model_used,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
                cost_usd=r.cost_usd,
                generated_at=r.generated_at
            )
            for r in reports
        ],
        total_count=len(reports)
    )


@router.get("/report/by-id/{report_id}", response_model=ReportResponse)
def get_report_by_id(report_id: int, db: Session = Depends(get_db)):
    """Get a specific report by its ID."""
    report = db.query(LLMReport).filter(LLMReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    return ReportResponse(
        report_id=report.id,
        file_id=report.file_id,
        model_used=report.model_used,
        report_content=report.report_content,
        prompt_tokens=report.prompt_tokens,
        completion_tokens=report.completion_tokens,
        cost_usd=report.cost_usd,
        generated_at=report.generated_at,
        cached=True
    )


@router.delete("/report/{report_id}")
def delete_report(report_id: int, db: Session = Depends(get_db)):
    """Delete a specific report."""
    report = db.query(LLMReport).filter(LLMReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    db.delete(report)
    db.commit()
    
    return {"success": True, "message": "Report deleted"}


@router.get("/report/{file_id}/export/{report_id}")
def export_report_docx(file_id: int, report_id: int, db: Session = Depends(get_db)):
    """Export a specific report as Word document."""
    from io import BytesIO
    from docx import Document
    from docx.shared import Inches, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from fastapi.responses import StreamingResponse
    
    report = db.query(LLMReport).filter(
        LLMReport.id == report_id,
        LLMReport.file_id == file_id
    ).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    file = db.query(LogFile).filter(LogFile.id == file_id).first()
    filename = file.filename if file else f"file_{file_id}"
    
    # Create Word document
    doc = Document()
    
    # Title
    title = doc.add_heading(f"Log Analysis Report: {filename}", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Metadata
    meta = doc.add_paragraph()
    meta.add_run(f"Model: {report.model_used}\n").bold = True
    meta.add_run(f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
    meta.add_run(f"Tokens: {report.prompt_tokens:,} input / {report.completion_tokens:,} output\n")
    cost_str = "FREE" if report.cost_usd == 0 else f"${report.cost_usd:.4f}"
    meta.add_run(f"Cost: {cost_str}")
    
    doc.add_paragraph()  # Spacer
    
    # Convert markdown content to Word
    lines = report.report_content.split('\n')
    for line in lines:
        line = line.rstrip()
        if line.startswith('# '):
            doc.add_heading(line[2:], level=1)
        elif line.startswith('## '):
            doc.add_heading(line[3:], level=2)
        elif line.startswith('### '):
            doc.add_heading(line[4:], level=3)
        elif line.startswith('#### '):
            doc.add_heading(line[5:], level=4)
        elif line.startswith('- ') or line.startswith('* '):
            doc.add_paragraph(line[2:], style='List Bullet')
        elif line.startswith('1. ') or line.startswith('2. ') or line.startswith('3. '):
            doc.add_paragraph(line[3:], style='List Number')
        elif line.startswith('```'):
            continue  # Skip code fence markers
        elif line.strip():
            # Handle bold text
            p = doc.add_paragraph()
            parts = line.split('**')
            for i, part in enumerate(parts):
                run = p.add_run(part)
                if i % 2 == 1:  # Odd indices are bold
                    run.bold = True
    
    # Save to BytesIO
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    
    # Generate filename
    safe_filename = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in filename)
    export_name = f"Report_{safe_filename}_{report.generated_at.strftime('%Y%m%d_%H%M%S')}.docx"
    
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={export_name}"}
    )


@router.get("/report/{file_id}/estimate", response_model=CostEstimateResponse)
def estimate_report_cost(
    file_id: int,
    model: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Estimate the cost of generating a report."""
    _ensure_client_configured(db)
    _ensure_gemini_configured(db)
    
    # Check file exists
    file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Get default model if not specified
    if not model:
        config = db.query(LLMConfig).first()
        model = config.default_model if config else DEFAULT_MODEL
    
    try:
        generator = ReportGenerator(db)
        estimate = generator.estimate_cost(file_id, model)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cost estimation failed: {str(e)}")
    
    return CostEstimateResponse(
        model=estimate["model"],
        model_name=estimate.get("model_name"),
        prompt_tokens=estimate["prompt_tokens"],
        completion_tokens=estimate["completion_tokens"],
        total_tokens=estimate["total_tokens"],
        estimated_cost_usd=estimate["estimated_cost_usd"]
    )


# ============================================================
# Embedding Endpoints
# ============================================================

@router.get("/embeddings/{file_id}/stats", response_model=EmbeddingStatsResponse)
def get_embedding_stats(file_id: int, db: Session = Depends(get_db)):
    """Get embedding statistics for a file."""
    file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    vector_store = get_vector_store()
    stats = vector_store.get_stats(file_id)
    
    return EmbeddingStatsResponse(
        file_id=file_id,
        summaries=stats.get("summaries", 0),
        errors=stats.get("errors", 0),
        anomalies=stats.get("anomalies", 0),
        total=stats.get("total", 0)
    )


@router.post("/embeddings/{file_id}/refresh")
def refresh_embeddings(file_id: int, db: Session = Depends(get_db)):
    """Refresh embeddings for a file."""
    file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    if file.status != "ready":
        raise HTTPException(status_code=400, detail="File is not ready")
    
    # Delete existing embeddings
    vector_store = get_vector_store()
    deleted = vector_store.delete_file_embeddings(file_id)
    
    # Regenerate embeddings
    generator = ReportGenerator(db)
    counts = generator.embed_file_content(file_id)
    
    return {
        "file_id": file_id,
        "deleted": deleted,
        "embedded": counts
    }


# ============================================================
# Export Endpoints
# ============================================================

@router.get("/report/{file_id}/export/docx")
def export_report_docx(file_id: int, db: Session = Depends(get_db)):
    """Export the report as a Word document."""
    try:
        from docx import Document
        from docx.shared import Inches, Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:
        raise HTTPException(
            status_code=500, 
            detail="python-docx not installed. Run: pip install python-docx"
        )
    
    # Get the report
    file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    report = db.query(LLMReport).filter(
        LLMReport.file_id == file_id
    ).order_by(LLMReport.generated_at.desc()).first()
    
    if not report:
        raise HTTPException(status_code=404, detail="No report found for this file")
    
    # Create Word document
    doc = Document()
    
    # Title
    title = doc.add_heading('Log Analysis Report', 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # File info
    doc.add_paragraph(f"File: {file.filename}")
    doc.add_paragraph(f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S') if report.generated_at else 'Unknown'}")
    doc.add_paragraph(f"Model: {report.model_used}")
    doc.add_paragraph(f"Tokens: {report.prompt_tokens + report.completion_tokens} (Cost: ${report.cost_usd:.4f})")
    doc.add_paragraph()
    
    # Parse markdown content and convert to Word
    content = report.report_content
    
    # Split by lines and process
    lines = content.split('\n')
    current_list = None
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            if current_list:
                current_list = None
            continue
        
        # Headers
        if stripped.startswith('### '):
            doc.add_heading(stripped[4:], level=3)
        elif stripped.startswith('## '):
            doc.add_heading(stripped[3:], level=2)
        elif stripped.startswith('# '):
            doc.add_heading(stripped[2:], level=1)
        # Bold header style (e.g., **Section Name**)
        elif stripped.startswith('**') and stripped.endswith('**') and len(stripped) > 4:
            p = doc.add_paragraph()
            run = p.add_run(stripped[2:-2])
            run.bold = True
        # List items
        elif stripped.startswith('- ') or stripped.startswith('* '):
            # Remove markdown formatting from list items
            text = stripped[2:]
            text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Remove bold
            text = re.sub(r'\*([^*]+)\*', r'\1', text)  # Remove italic
            text = re.sub(r'`([^`]+)`', r'\1', text)  # Remove code
            doc.add_paragraph(text, style='List Bullet')
        # Numbered list
        elif re.match(r'^\d+\. ', stripped):
            text = re.sub(r'^\d+\. ', '', stripped)
            text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
            text = re.sub(r'\*([^*]+)\*', r'\1', text)
            text = re.sub(r'`([^`]+)`', r'\1', text)
            doc.add_paragraph(text, style='List Number')
        # Code blocks
        elif stripped.startswith('```'):
            continue  # Skip code fence markers
        # Regular paragraph
        else:
            # Remove markdown formatting
            text = re.sub(r'\*\*([^*]+)\*\*', r'\1', stripped)
            text = re.sub(r'\*([^*]+)\*', r'\1', text)
            text = re.sub(r'`([^`]+)`', r'\1', text)
            if text:
                doc.add_paragraph(text)
    
    # Save to buffer
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    
    # Generate filename
    safe_filename = re.sub(r'[^\w\-_.]', '_', file.filename)
    export_filename = f"report_{safe_filename}.docx"
    
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={export_filename}"}
    )


# ============================================================
# AI Assistant Endpoints
# ============================================================

class AskRequest(BaseModel):
    """Request to ask a question about a log file."""
    file_id: int
    question: str
    allow_ai: bool = False  # Must explicitly allow AI usage


class AskResponse(BaseModel):
    """Response from AI assistant."""
    thread_id: int
    answer: str
    kb_articles: List[dict]
    model_used: str
    prompt_tokens: int
    completion_tokens: int
    routing_mode: str = "LOG_PLUS_KB"  # "LOCAL", "KB_FUSION", or "AI_REQUIRED"
    used_kb: bool = True  # Whether KB articles were consulted
    context_sections: List[str] = []  # Which log summary sections were included
    source: str = "ai"  # "local", "kb", "report" - indicates where answer came from


class ThreadResponse(BaseModel):
    """Single thread in list."""
    id: int
    question: str
    answer: str
    kb_articles: List[dict]
    thumbs_up: bool
    created_at: datetime


class ThreadsListResponse(BaseModel):
    """List of threads for a file."""
    file_id: int
    threads: List[ThreadResponse]


class PreviewRedactionsRequest(BaseModel):
    """Request to preview what will be redacted in text."""
    text: str


class RedactionItem(BaseModel):
    """Single redaction item."""
    type: str
    type_description: str
    original_value: str
    replacement: str
    start: int
    end: int
    score: float


class PreviewRedactionsResponse(BaseModel):
    """Response showing what will be redacted."""
    original: str
    sanitized: str
    redactions: List[RedactionItem]
    summary: str


# ============================================================
# Routing Feedback Models
# ============================================================

class RoutingFeedbackRequest(BaseModel):
    """Request to submit routing feedback."""
    thread_id: int
    should_use_local: bool = False
    should_use_kb: bool = False
    should_use_report: bool = False
    comment: Optional[str] = None
    quality_rating: Optional[int] = None  # 1-5 scale


class RoutingFeedbackResponse(BaseModel):
    """Response after submitting feedback."""
    id: int
    thread_id: int
    message: str


class RoutingFeedbackItem(BaseModel):
    """Single feedback item for listing."""
    id: int
    thread_id: Optional[int] = 0
    question: str
    actual_source: str
    actual_routing_mode: Optional[str]
    should_use_local: bool
    should_use_kb: bool
    should_use_report: bool
    comment: Optional[str]
    quality_rating: Optional[int]
    created_at: datetime
    
    # Computed fields
    mismatch: bool = False  # True if actual != suggested


class RoutingFeedbackListResponse(BaseModel):
    """List of routing feedback entries."""
    total: int
    items: List[RoutingFeedbackItem]


@router.post("/preview-redactions", response_model=PreviewRedactionsResponse)
def preview_redactions_endpoint(request: PreviewRedactionsRequest):
    """
    Preview what sensitive information will be redacted from text.
    
    This endpoint shows users what PII will be masked before sending to the LLM,
    providing transparency about data sanitization.
    """
    from backend.llm.sanitizer import preview_redactions
    
    result = preview_redactions(request.text)
    return PreviewRedactionsResponse(
        original=result["original"],
        sanitized=result["sanitized"],
        redactions=[RedactionItem(**r) for r in result["redactions"]],
        summary=result["summary"]
    )


class PromptPreviewRequest(BaseModel):
    """Request for comprehensive prompt preview."""
    file_id: int
    question: str


class KBArticlePreview(BaseModel):
    """KB article info for preview."""
    title: str
    url: str
    similarity: float
    content_preview: str


class ContextSection(BaseModel):
    """A section of context that will be included."""
    type: str  # "kb_article", "log_error", "log_anomaly", "user_snippet"
    title: str
    content: str
    sanitized_content: str


class ProcessingStep(BaseModel):
    """A single step in the prompt processing flow."""
    step: str
    status: str  # "completed", "skipped", "warning"
    detail: str


class PromptPreviewResponse(BaseModel):
    """Comprehensive preview of what will be sent to the LLM."""
    question: str
    sanitized_question: str
    routing_mode: str  # "LOG_ONLY" or "LOG_PLUS_KB"
    relevant_sections: List[str]  # Which log summary sections are included
    log_summary_context: str  # Formatted log summary
    report_context: str  # Extracted sections from existing report
    kb_articles: List[KBArticlePreview]
    log_errors: List[str]
    log_anomalies: List[str]
    context_sections: List[ContextSection]
    full_prompt: str
    sanitized_prompt: str
    redactions: List[RedactionItem]
    summary: str
    processing_flow: List[ProcessingStep] = []  # Processing pipeline steps


@router.post("/prompt-preview", response_model=PromptPreviewResponse)
def preview_prompt(
    request: PromptPreviewRequest,
    db: Session = Depends(get_db)
):
    """
    Preview the complete prompt that will be sent to the LLM.
    
    This provides full transparency on:
    - Routing mode (LOG_ONLY vs LOG_PLUS_KB)
    - Log summary context being included
    - Existing report sections if available
    - What KB articles will be included (if mode requires it)
    - What log context (errors, anomalies) will be included
    - The full prompt with and without sanitization
    - All PII that will be redacted
    """
    from backend.llm.sanitizer import preview_redactions, sanitize_text
    from backend.llm.question_router import classify_question, get_relevant_summary_context, get_relevant_report_sections
    from backend.llm.report_generator import ReportGenerator
    from backend.llm.prompts import SYSTEM_PROMPT_LOG_FOCUSED, SYSTEM_PROMPT_LOG_PLUS_KB
    
    # Check file exists
    file = db.query(LogFile).filter(LogFile.id == request.file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Step 1: Classify question and get relevant sections
    routing_mode, relevant_sections = classify_question(request.question)
    
    # Step 2: Build log summary context
    try:
        generator = ReportGenerator(db)
        summary_data = generator.build_performance_summary(request.file_id)
    except Exception as e:
        logger.warning(f"Failed to build performance summary: {e}")
        summary_data = {}
    
    log_summary_context = get_relevant_summary_context(request.question, summary_data, relevant_sections)
    
    # Step 3: Get existing report content if available
    existing_report = db.query(LLMReport).filter(
        LLMReport.file_id == request.file_id
    ).order_by(LLMReport.generated_at.desc()).first()
    report_content = existing_report.report_content if existing_report else None
    report_context = get_relevant_report_sections(request.question, report_content) if report_content else ""
    
    # Step 4: Conditionally query KB based on routing mode
    vector_store = get_vector_store()
    kb_articles = []
    kb_context = ""
    
    if routing_mode == "LOG_PLUS_KB":
        kb_results = vector_store.query_kb(request.question, n_results=5)
        
        # Filter out 0% matches and format KB articles
        for kb in kb_results:
            similarity = kb.get('similarity', 0)
            if similarity > 0.01:  # Filter out essentially 0% matches
                content = kb.get('content', '')[:1500]
                kb_articles.append(KBArticlePreview(
                    title=kb.get('title', 'Unknown'),
                    url=kb.get('url', ''),
                    similarity=similarity,
                    content_preview=content[:300] + ('...' if len(content) > 300 else '')
                ))
                kb_context += f"\n--- KB Article: {kb.get('title', 'Unknown')} ---\n"
                kb_context += content + "\n"
    
    # Step 5: Get file context (errors, anomalies)
    file_context = vector_store.get_file_context(request.file_id, max_items=5)
    
    log_errors = []
    errors_context = ""
    if file_context.get('errors'):
        errors_context = "\n--- Recent Errors from Log ---\n"
        for err in file_context['errors'][:3]:
            err_text = err[:500]
            log_errors.append(err_text)
            errors_context += err_text + "\n\n"
    
    log_anomalies = []
    anomalies_context = ""
    if file_context.get('anomalies'):
        anomalies_context = "\n--- Detected Anomalies ---\n"
        for anomaly in file_context['anomalies'][:2]:
            anomaly_text = anomaly[:400]
            log_anomalies.append(anomaly_text)
            anomalies_context += anomaly_text + "\n\n"
    
    # Step 6: Build context sections for detailed view
    context_sections = []
    
    # Add log summary section
    if log_summary_context:
        context_sections.append(ContextSection(
            type="log_summary",
            title="Log Analysis Summary",
            content=log_summary_context,
            sanitized_content=sanitize_text(log_summary_context)
        ))
    
    # Add report sections if available
    if report_context:
        context_sections.append(ContextSection(
            type="report",
            title="From Previous Analysis Report",
            content=report_context,
            sanitized_content=report_context  # Report is already sanitized
        ))
    
    # Add KB articles (only if routing requires it)
    for kb in kb_articles:
        context_sections.append(ContextSection(
            type="kb_article",
            title=f"KB: {kb.title}",
            content=kb.content_preview,
            sanitized_content=kb.content_preview  # KB articles are NOT sanitized
        ))
    
    for i, err in enumerate(log_errors):
        context_sections.append(ContextSection(
            type="log_error",
            title=f"Log Error #{i+1}",
            content=err,
            sanitized_content=sanitize_text(err)
        ))
    
    for i, anomaly in enumerate(log_anomalies):
        context_sections.append(ContextSection(
            type="log_anomaly",
            title=f"Anomaly #{i+1}",
            content=anomaly,
            sanitized_content=sanitize_text(anomaly)
        ))
    
    # Step 7: Select appropriate system prompt
    system_prompt = SYSTEM_PROMPT_LOG_FOCUSED if routing_mode == "LOG_ONLY" else SYSTEM_PROMPT_LOG_PLUS_KB
    
    # Step 8: Build full prompt (matching ask endpoint logic)
    user_prompt_parts = [f"User Question: {request.question}\n"]
    
    if log_summary_context:
        user_prompt_parts.append(f"\n{log_summary_context}")
    
    if report_context:
        user_prompt_parts.append(f"\n{report_context}")
    
    if kb_context:
        user_prompt_parts.append(f"\n## Relevant KB Articles\n{kb_context}")
    
    if errors_context:
        user_prompt_parts.append(f"\n{errors_context}")
    
    if anomalies_context:
        user_prompt_parts.append(f"\n{anomalies_context}")
    
    if routing_mode == "LOG_ONLY":
        user_prompt_parts.append("\nAnswer based on the log data provided above.")
    else:
        user_prompt_parts.append("\nProvide a helpful answer based on the log data and KB articles. Reference KB articles when relevant.")
    
    user_prompt = "\n".join(user_prompt_parts)
    full_prompt = f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_prompt}"
    
    # Step 9: Sanitize and get redactions
    sanitized_question = sanitize_text(request.question)
    sanitized_user_prompt = sanitize_text(user_prompt)
    sanitized_prompt = f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{sanitized_user_prompt}"
    
    # Get redaction details
    redaction_result = preview_redactions(user_prompt)
    
    # Build processing flow
    processing_flow = []
    
    # Step 1: Question classification
    processing_flow.append(ProcessingStep(
        step="Question Classification",
        status="completed",
        detail=f"Routed to {routing_mode} mode"
    ))
    
    # Step 2: Log summary retrieval
    processing_flow.append(ProcessingStep(
        step="Log Summary",
        status="completed" if log_summary_context else "skipped",
        detail=f"{len(relevant_sections)} relevant sections" if log_summary_context else "No summary available"
    ))
    
    # Step 3: Previous report check
    processing_flow.append(ProcessingStep(
        step="Previous Report",
        status="completed" if report_context else "skipped",
        detail="Included relevant sections" if report_context else "No previous report found"
    ))
    
    # Step 4: KB lookup
    if routing_mode == "LOG_PLUS_KB":
        processing_flow.append(ProcessingStep(
            step="KB Article Search",
            status="completed" if kb_articles else "warning",
            detail=f"Found {len(kb_articles)} relevant articles" if kb_articles else "No relevant KB articles found"
        ))
    else:
        processing_flow.append(ProcessingStep(
            step="KB Article Search",
            status="skipped",
            detail="Skipped (LOG_ONLY mode - question answerable from log data)"
        ))
    
    # Step 5: Error context
    processing_flow.append(ProcessingStep(
        step="Error Context",
        status="completed" if log_errors else "skipped",
        detail=f"Included {len(log_errors)} log errors" if log_errors else "No errors in context"
    ))
    
    # Step 6: Presidio PII check (always runs)
    redaction_count = len(redaction_result.get("redactions", []))
    processing_flow.append(ProcessingStep(
        step="Presidio PII Detection",
        status="completed",
        detail=f"Detected {redaction_count} PII items to redact" if redaction_count > 0 else "No sensitive information detected"
    ))
    
    # Build summary
    summary_parts = [f"Routing: {routing_mode}"]
    if log_summary_context:
        summary_parts.append(f"log summary ({len(relevant_sections)} sections)")
    if report_context:
        summary_parts.append("previous report")
    if kb_articles:
        summary_parts.append(f"{len(kb_articles)} KB article{'s' if len(kb_articles) > 1 else ''}")
    if log_errors:
        summary_parts.append(f"{len(log_errors)} error{'s' if len(log_errors) > 1 else ''}")
    if log_anomalies:
        summary_parts.append(f"{len(log_anomalies)} anomal{'ies' if len(log_anomalies) > 1 else 'y'}")
    
    context_summary = f"Context: {', '.join(summary_parts)}"
    redaction_summary = redaction_result["summary"]
    full_summary = f"{context_summary}. {redaction_summary}"
    
    return PromptPreviewResponse(
        question=request.question,
        sanitized_question=sanitized_question,
        routing_mode=routing_mode,
        relevant_sections=relevant_sections,
        log_summary_context=log_summary_context,
        report_context=report_context,
        kb_articles=kb_articles,
        log_errors=log_errors,
        log_anomalies=log_anomalies,
        context_sections=context_sections,
        full_prompt=full_prompt,
        sanitized_prompt=sanitized_prompt,
        redactions=[RedactionItem(**r) for r in redaction_result["redactions"]],
        summary=full_summary,
        processing_flow=processing_flow
    )


@router.post("/ask", response_model=AskResponse)
def ask_question(
    request: AskRequest,
    db: Session = Depends(get_db)
):
    """
    Ask a question about a log file with Zero-LLM-First intelligent routing.
    
    This endpoint implements a 3-tier routing system:
    1. LOCAL: Answer from SQLite data (0 tokens, instant)
    2. KB_FUSION: Combine local facts with KB articles (0 tokens)
    3. AI_REQUIRED: Only call LLM when truly needed (sanitize first!)
    
    The goal is to answer 80%+ of questions without using AI.
    """
    from backend.database import AIThread
    from backend.llm.question_router import classify_question, build_log_context
    from backend.llm.local_query_engine import AnswerMode, answer_locally, classify_intent
    from backend.llm.kb_fusion import fuse_answer
    from backend.llm.report_generator import ReportGenerator
    from backend.llm.prompts import SYSTEM_PROMPT_LOG_FOCUSED, SYSTEM_PROMPT_LOG_PLUS_KB
    from backend.llm.sanitizer import sanitize_text
    import json
    
    # Check file exists
    file = db.query(LogFile).filter(LogFile.id == request.file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Step 1: Classify the question using new 3-tier system
    answer_mode, intent = classify_intent(request.question)
    routing_mode, relevant_sections = classify_question(request.question)  # For context sections
    logger.info(f"Question classified: tier={answer_mode.value.upper()}, intent={intent.type}, entity={intent.entity}")
    
    # ================================================================
    # TIER 1: Try LOCAL answer first (0 tokens)
    # ================================================================
    if answer_mode in (AnswerMode.LOCAL, AnswerMode.KB_FUSION):
        local_result = answer_locally(request.question, request.file_id, db)
        
        if local_result and local_result.answer:
            logger.info(f"Question answered LOCALLY (0 tokens): {intent.type}")
            
            # Save thread with local source
            thread = AIThread(
                file_id=request.file_id,
                question=request.question,
                answer=local_result.answer,
                kb_articles=json.dumps([]),
                model_used="local",
                prompt_tokens=0,
                completion_tokens=0
            )
            db.add(thread)
            db.commit()
            db.refresh(thread)
            
            return AskResponse(
                thread_id=thread.id,
                answer=local_result.answer,
                kb_articles=[],
                model_used="local",
                prompt_tokens=0,
                completion_tokens=0,
                routing_mode="LOCAL",
                used_kb=False,
                context_sections=relevant_sections,
                source="local"
            )
    
    # ================================================================
    # TIER 2: Try KB FUSION (0 tokens)
    # ================================================================
    if answer_mode in (AnswerMode.KB_FUSION, AnswerMode.LOCAL):
        # Try to get local answer first for fusion
        local_result = answer_locally(request.question, request.file_id, db) if answer_mode == AnswerMode.KB_FUSION else None
        
        fusion_result = fuse_answer(
            question=request.question,
            file_id=request.file_id,
            db=db,
            local_answer=local_result
        )
        
        if fusion_result and fusion_result.answer:
            logger.info(f"Question answered via KB FUSION (0 tokens)")
            
            # Format KB articles for response
            kb_articles = fusion_result.kb_articles or []
            
            # Save thread with KB source
            thread = AIThread(
                file_id=request.file_id,
                question=request.question,
                answer=fusion_result.answer,
                kb_articles=json.dumps(kb_articles),
                model_used="kb_fusion",
                prompt_tokens=0,
                completion_tokens=0
            )
            db.add(thread)
            db.commit()
            db.refresh(thread)
            
            return AskResponse(
                thread_id=thread.id,
                answer=fusion_result.answer,
                kb_articles=kb_articles,
                model_used="kb_fusion",
                prompt_tokens=0,
                completion_tokens=0,
                routing_mode="KB_FUSION",
                used_kb=True,
                context_sections=relevant_sections,
                source="kb"
            )
    
    # ================================================================
    # TIER 3: Context-only Smart Search (no remote LLM)
    # ================================================================
    logger.info("Question requires deeper reasoning; returning context-only Smart Search answer.")

    # Build log summary context
    try:
        generator = ReportGenerator(db)
        summary_data = generator.build_performance_summary(request.file_id)
    except Exception as e:
        logger.warning(f"Failed to build performance summary: {e}")
        summary_data = {}

    # Get existing report content if available
    existing_report = db.query(LLMReport).filter(
        LLMReport.file_id == request.file_id
    ).order_by(LLMReport.generated_at.desc()).first()
    report_content = existing_report.report_content if existing_report else None

    # Get file context from vector store (errors, anomalies)
    vector_store = get_vector_store()
    file_context = vector_store.get_file_context(request.file_id, max_items=5)

    # Build complete log context using router
    _, log_context, _ = build_log_context(
        question=request.question,
        summary_data=summary_data,
        report_content=report_content,
        errors_context=file_context.get('errors', []),
        anomalies_context=file_context.get('anomalies', [])
    )

    kb_articles = []
    kb_context_snippets = []
    kb_results = vector_store.query_kb(request.question, n_results=5)
    for kb in kb_results:
        similarity = kb.get('similarity', 0)
        if similarity > 0.01:
            kb_articles.append({
                "title": kb.get('title', 'Unknown'),
                "url": kb.get('url', ''),
                "similarity": similarity
            })
            snippet = kb.get('content', '')[:300]
            kb_context_snippets.append(f"- {kb.get('title', 'KB Article')} ({int(similarity * 100)}% match): {snippet}")

    fallback_parts = [
        "Smart Search could not fully answer this without a remote model.",
        "Context gathered from logs, summaries, and KB:"
    ]
    if log_context:
        fallback_parts.append(log_context)
    if kb_context_snippets:
        fallback_parts.append("Relevant KB matches:\n" + "\n".join(kb_context_snippets))
    fallback_parts.append("For deeper reasoning, open the Insights report in Findings (Gemini with OpenRouter fallback).")
    answer = "\n\n".join(fallback_parts)

    # Save thread as context-only Smart Search (0 tokens)
    thread = AIThread(
        file_id=request.file_id,
        question=request.question,
        answer=answer,
        kb_articles=json.dumps(kb_articles),
        model_used="smart_search",
        prompt_tokens=0,
        completion_tokens=0
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)

    return AskResponse(
        thread_id=thread.id,
        answer=answer,
        kb_articles=kb_articles,
        model_used="smart_search",
        prompt_tokens=0,
        completion_tokens=0,
        routing_mode="KB_FUSION" if kb_articles else "LOCAL",
        used_kb=bool(kb_articles),
        context_sections=relevant_sections,
        source="report" if report_content else ("kb" if kb_articles else "local")
    )


@router.get("/threads/{file_id}", response_model=ThreadsListResponse)
def get_threads(
    file_id: int,
    db: Session = Depends(get_db)
):
    """Get all Q&A threads for a file."""
    from backend.database import AIThread
    import json
    
    # Check file exists
    file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    threads = db.query(AIThread).filter(
        AIThread.file_id == file_id
    ).order_by(AIThread.created_at.desc()).all()
    
    return ThreadsListResponse(
        file_id=file_id,
        threads=[
            ThreadResponse(
                id=t.id,
                question=t.question,
                answer=t.answer,
                kb_articles=json.loads(t.kb_articles) if t.kb_articles else [],
                thumbs_up=t.thumbs_up or False,
                created_at=t.created_at
            )
            for t in threads
        ]
    )


@router.post("/threads/{thread_id}/thumbs-up")
def thumbs_up_thread(
    thread_id: int,
    db: Session = Depends(get_db)
):
    """Mark a thread as helpful and optionally save to ChromaDB for future RAG."""
    from backend.database import AIThread
    
    thread = db.query(AIThread).filter(AIThread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    thread.thumbs_up = True
    
    # Save to ChromaDB for future retrieval
    if not thread.saved_to_chromadb:
        try:
            vector_store = get_vector_store()
            # Add to summaries collection as a "user_validated" answer
            vector_store.add_summary(
                file_id=thread.file_id,
                summary_data={
                    "type": "user_qa",
                    "question": thread.question,
                    "answer": thread.answer,
                    "source": "ai_assistant"
                },
                summary_type="user_qa"
            )
            thread.saved_to_chromadb = True
        except Exception as e:
            logger.warning(f"Failed to save to ChromaDB: {e}")
    
    db.commit()
    
    return {"success": True, "message": "Marked as helpful"}


@router.delete("/threads/{thread_id}")
def delete_thread(
    thread_id: int,
    db: Session = Depends(get_db)
):
    """Delete a Q&A thread (thumbs down action)."""
    from backend.database import AIThread
    
    thread = db.query(AIThread).filter(AIThread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    db.delete(thread)
    db.commit()
    
    return {"success": True, "message": "Thread deleted"}


# ============================================================
# Saved Findings Endpoints
# ============================================================

class SaveFindingRequest(BaseModel):
    """Request to save a finding."""
    file_id: int
    finding_type: str = "custom"  # "log_line", "qa_thread", "custom"
    title: Optional[str] = None
    content: str
    source_thread_id: Optional[int] = None
    line_number: Optional[int] = None
    metadata: Optional[dict] = None


class SavedFindingResponse(BaseModel):
    """Response for a saved finding."""
    id: int
    file_id: int
    finding_type: str
    title: Optional[str]
    content: str
    source_thread_id: Optional[int]
    line_number: Optional[int]
    created_at: datetime
    metadata: Optional[dict] = None


class SavedFindingsListResponse(BaseModel):
    """List of saved findings."""
    file_id: int
    findings: List[SavedFindingResponse]
    total_count: int


@router.post("/findings", response_model=SavedFindingResponse)
def save_finding(
    request: SaveFindingRequest,
    db: Session = Depends(get_db)
):
    """Save a finding (log line, Q/A thread, or custom note)."""
    from backend.database import SavedFinding
    import json
    
    # Check file exists
    file = db.query(LogFile).filter(LogFile.id == request.file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    finding = SavedFinding(
        file_id=request.file_id,
        finding_type=request.finding_type,
        title=request.title,
        content=request.content,
        source_thread_id=request.source_thread_id,
        line_number=request.line_number,
        metadata_json=json.dumps(request.metadata) if request.metadata else None
    )
    db.add(finding)
    db.commit()
    db.refresh(finding)
    
    return SavedFindingResponse(
        id=finding.id,
        file_id=finding.file_id,
        finding_type=finding.finding_type,
        title=finding.title,
        content=finding.content,
        source_thread_id=finding.source_thread_id,
        line_number=finding.line_number,
        created_at=finding.created_at,
        metadata=request.metadata
    )


@router.post("/findings/from-thread/{thread_id}", response_model=SavedFindingResponse)
def save_finding_from_thread(
    thread_id: int,
    db: Session = Depends(get_db)
):
    """Save a Q/A thread as a finding."""
    from backend.database import AIThread, SavedFinding
    import json
    
    thread = db.query(AIThread).filter(AIThread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    # Format content as Q/A
    content = f"**Question:** {thread.question}\n\n**Answer:** {thread.answer}"
    title = thread.question[:100] + ("..." if len(thread.question) > 100 else "")
    
    finding = SavedFinding(
        file_id=thread.file_id,
        finding_type="qa_thread",
        title=title,
        content=content,
        source_thread_id=thread_id,
        metadata_json=json.dumps({
            "model_used": thread.model_used,
            "kb_articles": thread.kb_articles
        })
    )
    db.add(finding)
    db.commit()
    db.refresh(finding)
    
    return SavedFindingResponse(
        id=finding.id,
        file_id=finding.file_id,
        finding_type=finding.finding_type,
        title=finding.title,
        content=finding.content,
        source_thread_id=finding.source_thread_id,
        line_number=finding.line_number,
        created_at=finding.created_at,
        metadata=json.loads(finding.metadata_json) if finding.metadata_json else None
    )


@router.get("/findings/{file_id}", response_model=SavedFindingsListResponse)
def get_findings(
    file_id: int,
    db: Session = Depends(get_db)
):
    """Get all saved findings for a file."""
    from backend.database import SavedFinding
    import json
    
    # Check file exists
    file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    findings = db.query(SavedFinding).filter(
        SavedFinding.file_id == file_id
    ).order_by(SavedFinding.created_at.desc()).all()
    
    return SavedFindingsListResponse(
        file_id=file_id,
        findings=[
            SavedFindingResponse(
                id=f.id,
                file_id=f.file_id,
                finding_type=f.finding_type,
                title=f.title,
                content=f.content,
                source_thread_id=f.source_thread_id,
                line_number=f.line_number,
                created_at=f.created_at,
                metadata=json.loads(f.metadata_json) if getattr(f, "metadata_json", None) else None
            )
            for f in findings
        ],
        total_count=len(findings)
    )


@router.delete("/findings/{finding_id}")
def delete_finding(
    finding_id: int,
    db: Session = Depends(get_db)
):
    """Delete a saved finding."""
    from backend.database import SavedFinding
    
    finding = db.query(SavedFinding).filter(SavedFinding.id == finding_id).first()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    
    db.delete(finding)
    db.commit()
    
    return {"success": True, "message": "Finding deleted"}


# ============================================================
# KB Sources Endpoints
# ============================================================

class KBSourceResponse(BaseModel):
    """Response for a KB source/article."""
    id: int
    url: str
    article_id: Optional[str]
    title: str
    source: str  # "kb_article" or "markdown"
    chunks_count: int
    indexed_at: Optional[datetime]
    status: str


class KBSourcesListResponse(BaseModel):
    """List of KB sources with pagination."""
    sources: List[KBSourceResponse]
    total_count: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 1
    stats: dict


class AddMarkdownRequest(BaseModel):
    """Request to add a custom markdown source."""
    title: str
    content: str
    tags: Optional[List[str]] = None
    metadata: Optional[dict] = None


@router.get("/kb/sources", response_model=KBSourcesListResponse)
def get_kb_sources(
    source_type: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db)
):
    """Get all KB sources (articles and markdown files) with pagination and search."""
    from backend.database import KBArticle
    
    query = db.query(KBArticle)
    
    if source_type:
        query = query.filter(KBArticle.source == source_type)
    if status:
        query = query.filter(KBArticle.status == status)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (KBArticle.title.ilike(search_term)) | 
            (KBArticle.tags.ilike(search_term))
        )
    
    # Get total count before pagination
    total_count = query.count()
    
    # Apply pagination
    offset = (page - 1) * page_size
    sources = query.order_by(KBArticle.indexed_at.desc()).offset(offset).limit(page_size).all()
    
    # Get stats
    total = db.query(KBArticle).count()
    kb_articles = db.query(KBArticle).filter(KBArticle.source == "kb_article").count()
    markdown = db.query(KBArticle).filter(KBArticle.source == "markdown").count()
    indexed = db.query(KBArticle).filter(KBArticle.status == "indexed").count()
    
    import math
    total_pages = math.ceil(total_count / page_size) if page_size > 0 else 1
    
    return KBSourcesListResponse(
        sources=[
            KBSourceResponse(
                id=s.id,
                url=s.url,
                article_id=s.article_id,
                title=s.title,
                source=s.source,
                chunks_count=s.chunks_count,
                indexed_at=s.indexed_at,
                status=s.status
            )
            for s in sources
        ],
        total_count=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        stats={
            "total": total,
            "kb_articles": kb_articles,
            "markdown": markdown,
            "indexed": indexed
        }
    )


@router.post("/kb/markdown")
def add_markdown_source(
    request: AddMarkdownRequest,
    db: Session = Depends(get_db)
):
    """
    Add a custom markdown document as a KB source.
    This embeds the content and stores it in the KB.
    """
    from backend.database import KBArticle
    import hashlib
    from datetime import datetime
    
    # Generate a unique URL/path for this custom document
    content_hash = hashlib.md5(request.content.encode()).hexdigest()[:12]
    unique_path = f"custom://markdown/{content_hash}"
    
    # Check if already exists
    existing = db.query(KBArticle).filter(KBArticle.url == unique_path).first()
    if existing:
        raise HTTPException(status_code=400, detail="Document with same content already exists")
    
    # Prepare content with frontmatter if tags provided
    full_content = request.content
    if request.tags:
        full_content = f"Tags: {', '.join(request.tags)}\n\n{request.content}"
    
    # Embed the markdown content
    try:
        vector_store = get_vector_store()
        
        # Get KB collection directly for embedding
        kb_collection = vector_store.client.get_or_create_collection(
            name="qlik_replicate_kb",
            metadata={"description": "Qlik Replicate Knowledge Base articles"}
        )
        
        # Chunk the content
        from backend.llm.sanitizer import sanitize_text
        
        # Simple chunking by paragraphs
        chunks = []
        paragraphs = full_content.split('\n\n')
        current_chunk = []
        current_length = 0
        chunk_size = 1500  # chars
        
        for para in paragraphs:
            if current_length + len(para) > chunk_size and current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = [para]
                current_length = len(para)
            else:
                current_chunk.append(para)
                current_length += len(para)
        
        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))
        
        # Embed chunks
        ids = []
        documents = []
        metadatas = []
        
        for i, chunk in enumerate(chunks):
            chunk_id = f"markdown_{content_hash}_{i}"
            ids.append(chunk_id)
            documents.append(f"{request.title}\n\n{chunk}")
            metadatas.append({
                "source": "markdown",
                "url": unique_path,
                "title": request.title,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "tags": ','.join(request.tags) if request.tags else '',
                "indexed_at": datetime.utcnow().isoformat()
            })
        
        # Add to ChromaDB
        kb_collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
        
        chunks_added = len(chunks)
        
    except Exception as e:
        logger.error(f"Failed to embed markdown: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to embed content: {str(e)}")
    
    # Save to database
    article = KBArticle(
        url=unique_path,
        title=request.title,
        source="markdown",
        content_hash=content_hash,
        content_length=len(request.content),
        chunks_count=chunks_added,
        status="indexed"
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    
    return {
        "success": True,
        "message": f"Added markdown document with {chunks_added} chunks",
        "id": article.id,
        "title": article.title,
        "chunks_count": chunks_added
    }


@router.delete("/kb/sources/{source_id}")
def delete_kb_source(
    source_id: int,
    db: Session = Depends(get_db)
):
    """Delete a KB source and its embeddings."""
    from backend.database import KBArticle
    
    source = db.query(KBArticle).filter(KBArticle.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    # Delete from ChromaDB
    try:
        vector_store = get_vector_store()
        kb_collection = vector_store.client.get_or_create_collection(name="qlik_replicate_kb")
        
        # Find and delete chunks for this URL
        existing = kb_collection.get(where={"url": source.url})
        if existing and existing['ids']:
            kb_collection.delete(ids=existing['ids'])
    except Exception as e:
        logger.warning(f"Failed to delete from ChromaDB: {e}")
    
    # Delete from database
    db.delete(source)
    db.commit()
    
    return {"success": True, "message": "Source deleted"}


# ============================================================
# Routing Configuration Endpoints
# ============================================================

class RoutingConfigResponse(BaseModel):
    """Current routing configuration."""
    log_only_patterns: List[str]
    kb_needed_patterns: List[str]


@router.get("/routing/config", response_model=RoutingConfigResponse)
def get_routing_config():
    """Get current routing patterns (for display in UI)."""
    from backend.llm.question_router import LOG_ONLY_PATTERNS, KB_NEEDED_PATTERNS
    
    return RoutingConfigResponse(
        log_only_patterns=LOG_ONLY_PATTERNS,
        kb_needed_patterns=KB_NEEDED_PATTERNS
    )


@router.post("/routing/test")
def test_routing(question: str):
    """Test how a question would be routed."""
    from backend.llm.question_router import classify_question
    
    mode, sections = classify_question(question)
    
    return {
        "question": question,
        "routing_mode": mode,
        "relevant_sections": sections,
        "will_query_kb": mode == "LOG_PLUS_KB"
    }


# ============================================================
# Routing Feedback Endpoints
# ============================================================

@router.post("/routing/feedback", response_model=RoutingFeedbackResponse)
def submit_routing_feedback(
    request: RoutingFeedbackRequest,
    db: Session = Depends(get_db)
):
    """
    Submit feedback on routing decision.
    
    This allows users to indicate what sources SHOULD have been used
    to answer the question, helping improve future routing decisions.
    """
    from backend.database import AIThread, RoutingFeedback
    
    # Get the thread to capture question and actual routing
    thread = db.query(AIThread).filter(AIThread.id == request.thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    # Determine actual source from model_used
    actual_source = "report" if thread.model_used not in ("local", "kb_fusion") else "local"
    if thread.model_used == "local":
        actual_source = "local"
    elif thread.model_used == "kb_fusion":
        actual_source = "kb"
    elif thread.model_used in ("smart_search", "report"):
        actual_source = "report"
    
    # Create feedback entry
    feedback = RoutingFeedback(
        thread_id=request.thread_id,
        file_id=thread.file_id,
        question=thread.question,
        actual_source=actual_source,
        actual_routing_mode=None,  # Could be extracted from thread metadata if stored
        should_use_local=request.should_use_local,
        should_use_kb=request.should_use_kb,
        should_use_ai=request.should_use_report,  # stored in existing column
        comment=request.comment,
        quality_rating=request.quality_rating
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    
    return RoutingFeedbackResponse(
        id=feedback.id,
        thread_id=feedback.thread_id,
        message="Feedback submitted successfully"
    )


@router.get("/routing/feedback", response_model=RoutingFeedbackListResponse)
def get_routing_feedback(
    file_id: Optional[int] = None,
    mismatch_only: bool = False,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Get routing feedback history.
    
    Args:
        file_id: Filter by specific file
        mismatch_only: Only show entries where actual != suggested
        limit: Maximum entries to return
    """
    from backend.database import RoutingFeedback
    
    query = db.query(RoutingFeedback)
    
    if file_id:
        query = query.filter(RoutingFeedback.file_id == file_id)
    
    feedback_items = query.order_by(RoutingFeedback.created_at.desc()).limit(limit).all()
    
    # Build response items with mismatch detection
    items = []
    for f in feedback_items:
        # Skip rows missing thread_id to avoid validation errors
        if f.thread_id is None:
            continue
        # Detect mismatch: actual source doesn't match what user suggested
        actual_is_local = f.actual_source == "local"
        actual_is_kb = f.actual_source == "kb"
        actual_is_report = f.actual_source == "report"
        
        # Mismatch if user suggested different sources than what was used
        mismatch = False
        if f.should_use_local and not actual_is_local:
            mismatch = True
        if f.should_use_kb and not actual_is_kb and not actual_is_report:
            mismatch = True
        if f.should_use_ai and not actual_is_report:
            mismatch = True
        # Mismatch if report was used but user thinks local/kb should suffice
        if actual_is_report and (f.should_use_local or f.should_use_kb) and not f.should_use_ai:
            mismatch = True
        
        if mismatch_only and not mismatch:
            continue
        
        items.append(RoutingFeedbackItem(
            id=f.id,
            thread_id=f.thread_id or 0,
            question=f.question,
            actual_source=f.actual_source,
            actual_routing_mode=f.actual_routing_mode,
            should_use_local=f.should_use_local,
            should_use_kb=f.should_use_kb,
            should_use_report=f.should_use_ai,
            comment=f.comment,
            quality_rating=f.quality_rating,
            created_at=f.created_at,
            mismatch=mismatch
        ))
    
    return RoutingFeedbackListResponse(
        total=len(items),
        items=items
    )


@router.delete("/routing/feedback/{feedback_id}")
def delete_routing_feedback(
    feedback_id: int,
    db: Session = Depends(get_db)
):
    """Delete a routing feedback entry."""
    from backend.database import RoutingFeedback
    
    feedback = db.query(RoutingFeedback).filter(RoutingFeedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    
    db.delete(feedback)
    db.commit()
    
    return {"success": True, "message": "Feedback deleted"}


@router.get("/routing/feedback/export")
def export_routing_feedback(
    db: Session = Depends(get_db)
):
    """Export all routing feedback as CSV for analysis."""
    from backend.database import RoutingFeedback
    import csv
    import io
    
    feedback_items = db.query(RoutingFeedback).order_by(RoutingFeedback.created_at.desc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "id", "thread_id", "question", "actual_source", "actual_routing_mode",
        "should_use_local", "should_use_kb", "should_use_report", 
        "comment", "quality_rating", "created_at"
    ])
    
    for f in feedback_items:
        writer.writerow([
            f.id, f.thread_id or 0, f.question, f.actual_source, f.actual_routing_mode,
            f.should_use_local, f.should_use_kb, f.should_use_ai,
            f.comment, f.quality_rating, f.created_at.isoformat()
        ])
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=routing_feedback.csv"}
    )
