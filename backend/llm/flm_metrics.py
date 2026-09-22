"""In-process FLM / openai_api reliability metrics (Phase 0b grader input)."""

from __future__ import annotations

import threading
from typing import Any, Dict

_lock = threading.Lock()
_requests = 0
_empty_responses = 0


def record_flm_completion(*, empty: bool) -> None:
    """Record one openai_api completion attempt when FLM reliability mode is on."""
    global _requests, _empty_responses
    with _lock:
        _requests += 1
        if empty:
            _empty_responses += 1


def get_flm_metrics() -> Dict[str, Any]:
    with _lock:
        requests = _requests
        empty = _empty_responses
    rate = round(empty / requests, 4) if requests else 0.0
    return {
        "requests": requests,
        "empty_responses": empty,
        "flm_empty_response_rate": rate,
    }


def reset_flm_metrics() -> None:
    """Clear counters (tests only)."""
    global _requests, _empty_responses
    with _lock:
        _requests = 0
        _empty_responses = 0
