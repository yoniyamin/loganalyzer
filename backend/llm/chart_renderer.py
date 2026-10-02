"""
Server-side latency chart renderer using Plotly + Kaleido.

Generates a PNG image of the latency-over-time graph so it can be
included in multimodal LLM prompts for vision-capable models.
"""

import base64
import logging
import os
from typing import Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

try:
    import plotly.graph_objects as go
    from plotly.io import to_image as _plotly_to_image
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    logger.debug("plotly/kaleido not installed; chart rendering disabled")


_kaleido_checked: Optional[bool] = None
_kaleido_working: Optional[bool] = None
_kaleido_failure_logged: bool = False
_chart_cache: dict = {}  # file_id -> base64 string


def chart_export_disabled() -> bool:
    """Env kill-switch (desktop.py sets this for pywebview builds)."""
    return os.environ.get("LOG_ANALYZER_DISABLE_CHART_EXPORT", "").strip().lower() in (
        "1", "true", "yes",
    )


def is_available() -> bool:
    """Check whether Plotly + Kaleido can render (cached after first success/failure)."""
    global _kaleido_checked
    if chart_export_disabled():
        return False
    if not PLOTLY_AVAILABLE:
        return False
    if _kaleido_working is False:
        return False
    if _kaleido_checked is not None:
        return _kaleido_checked
    _kaleido_checked = True
    return True


def _mark_kaleido_failed() -> None:
    global _kaleido_working
    _kaleido_working = False


def render_latency_chart(
    db: Session,
    file_id: int,
    width: int = 1200,
    height: int = 600,
) -> Optional[bytes]:
    """
    Render the latency-over-time chart for a file as a PNG image.

    Args:
        db: SQLAlchemy session
        file_id: ID of the log file
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        PNG image bytes, or None if rendering fails or no data
    """
    if not is_available():
        return None

    from backend.database import LogPerformance

    records = (
        db.query(LogPerformance)
        .filter(LogPerformance.file_id == file_id)
        .order_by(LogPerformance.timestamp)
        .all()
    )

    if not records or len(records) < 2:
        logger.info(f"Not enough performance data for file {file_id} to render chart")
        return None

    timestamps = [r.timestamp for r in records]
    source = [r.source_latency or 0.0 for r in records]
    target = [r.target_latency or 0.0 for r in records]
    handling = [r.handling_latency or 0.0 for r in records]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=timestamps, y=source,
        mode='lines+markers', name='Source Latency',
        line=dict(color='#f59e0b'), marker=dict(size=3),
    ))
    fig.add_trace(go.Scatter(
        x=timestamps, y=target,
        mode='lines+markers', name='Target Latency',
        line=dict(color='#3b82f6'), marker=dict(size=3),
    ))
    fig.add_trace(go.Scatter(
        x=timestamps, y=handling,
        mode='lines+markers', name='Handling Latency',
        line=dict(color='#10b981'), marker=dict(size=3),
    ))

    fig.update_layout(
        title='Latency Over Time',
        xaxis_title='Timestamp',
        yaxis_title='Latency (seconds)',
        margin=dict(t=40, r=20, b=60, l=60),
        hovermode='closest',
        template='plotly_white',
    )

    try:
        img_bytes = _plotly_to_image(fig, format="png", width=width, height=height)
        global _kaleido_working
        _kaleido_working = True
        logger.info(f"Rendered latency chart for file {file_id}: {len(img_bytes)} bytes")
        return img_bytes
    except Exception as e:
        _mark_kaleido_failed()
        global _kaleido_failure_logged
        if not _kaleido_failure_logged:
            _kaleido_failure_logged = True
            logger.warning(
                "Optional latency chart PNG export disabled for this session "
                "(Plotly/Kaleido headless Chrome failed). Reports still work; "
                "set LOG_ANALYZER_DISABLE_CHART_EXPORT=0 to retry. Detail: %s",
                e,
            )
        return None


def render_latency_chart_base64(
    db: Session,
    file_id: int,
    width: int = 1200,
    height: int = 600,
) -> Optional[str]:
    """
    Render the chart and return as a base64-encoded string.
    Results are cached per file_id to avoid repeated kaleido launches.

    Returns:
        Base64-encoded PNG string, or None
    """
    if not is_available():
        return None

    if file_id in _chart_cache:
        return _chart_cache[file_id]

    img_bytes = render_latency_chart(db, file_id, width, height)
    if img_bytes:
        b64 = base64.b64encode(img_bytes).decode('utf-8')
        _chart_cache[file_id] = b64
        return b64

    _chart_cache[file_id] = None
    return None


def invalidate_chart_cache(file_id: Optional[int] = None):
    """Clear cached chart(s). Call when performance data changes."""
    if file_id is not None:
        _chart_cache.pop(file_id, None)
    else:
        _chart_cache.clear()
