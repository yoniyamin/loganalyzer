"""
LLM API Endpoints

Provides REST API endpoints for LLM configuration and report generation.
Mounted at /api/llm/
"""

import base64
import io
import re
import logging
import traceback
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database import get_db, LLMConfig, LLMReport, LogFile
from backend.llm.client import get_llm_client, set_api_key, DEFAULT_MODEL
from backend.llm.gemini_client import get_gemini_client, set_gemini_api_key, DEFAULT_GEMINI_MODEL, GEMINI_MODELS
from backend.llm.report_generator import ReportGenerator
from backend.llm.vectorstore import get_vector_store

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
    config = db.query(LLMConfig).first()
    
    if not config:
        return ConfigResponse(
            is_configured=False,
            provider=PROVIDER_GEMINI,
            default_model=DEFAULT_GEMINI_MODEL,
            gemini_configured=False,
            openrouter_configured=False
        )
    
    # Check which providers are configured
    gemini_configured = bool(config.gemini_api_key_encrypted)
    openrouter_configured = bool(config.api_key_encrypted)
    
    # Get API key previews
    gemini_preview = None
    openrouter_preview = None
    
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
        web_search_enabled=config.web_search_enabled or False,
        updated_at=config.updated_at
    )


@router.post("/config", response_model=ConfigResponse)
def save_config(request: ConfigRequest, db: Session = Depends(get_db)):
    """Save LLM configuration (API keys and preferences)."""
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
    
    gemini_preview = None
    openrouter_preview = None
    
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
    
    return ConfigResponse(
        is_configured=True,
        provider=config.provider,
        default_model=config.default_model,
        gemini_configured=gemini_configured,
        openrouter_configured=openrouter_configured,
        gemini_api_key_preview=gemini_preview,
        openrouter_api_key_preview=openrouter_preview,
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

@router.get("/report/{file_id}", response_model=ReportResponse)
def get_report(file_id: int, db: Session = Depends(get_db)):
    """Get cached report for a file if it exists."""
    # Check file exists
    file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check for cached report
    report = db.query(LLMReport).filter(
        LLMReport.file_id == file_id
    ).order_by(LLMReport.generated_at.desc()).first()
    
    if not report:
        raise HTTPException(status_code=404, detail="No report found for this file")
    
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


@router.get("/report/{file_id}")
def get_report(
    file_id: int,
    db: Session = Depends(get_db)
):
    """Get existing report for a file (without generating)."""
    # Check file exists
    file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Get cached report
    existing = db.query(LLMReport).filter(
        LLMReport.file_id == file_id
    ).order_by(LLMReport.generated_at.desc()).first()
    
    if not existing:
        return {"exists": False, "file_id": file_id}
    
    return {
        "exists": True,
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

