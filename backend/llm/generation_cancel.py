"""Cooperative cancellation for long-running LLM work keyed by file_id and operation kind."""

from __future__ import annotations

import threading
from typing import Dict, Optional, Set

import httpx


class GenerationCancelled(Exception):
    """Raised when the user cancels an in-flight LLM operation."""


_lock = threading.Lock()
_cancelled: Dict[str, bool] = {}
_active_clients: Dict[str, httpx.Client] = {}
_running: Set[str] = set()


def scope_key(file_id: int, kind: str = "report") -> str:
    return f"{kind}:{file_id}"


def begin(file_id: int, *, kind: str = "report") -> None:
    """Reset cancellation state for a new generation run."""
    key = scope_key(file_id, kind)
    with _lock:
        _running.add(key)
        _cancelled[key] = False
        old = _active_clients.pop(key, None)
    if old is not None:
        try:
            old.close()
        except Exception:
            pass


def request_cancel(file_id: int, *, kind: str = "report") -> None:
    """Mark work cancelled and abort any in-flight provider HTTP request."""
    key = scope_key(file_id, kind)
    with _lock:
        _cancelled[key] = True
        client = _active_clients.get(key)
    if client is not None:
        try:
            client.close()
        except Exception:
            pass


def request_cancel_all(file_id: int) -> None:
    """Cancel report generation and compile-email for a file."""
    request_cancel(file_id, kind="report")
    request_cancel(file_id, kind="compile")


def is_running(file_id: int, *, kind: str = "report") -> bool:
    with _lock:
        return scope_key(file_id, kind) in _running


def is_cancelled(file_id: int, *, kind: str = "report") -> bool:
    with _lock:
        return _cancelled.get(scope_key(file_id, kind), False)


def check_cancelled(file_id: int, *, kind: str = "report") -> None:
    if is_cancelled(file_id, kind=kind):
        raise GenerationCancelled(f"{kind} cancelled by user")


def register_client(file_id: int, client: httpx.Client, *, kind: str = "report") -> None:
    with _lock:
        _active_clients[scope_key(file_id, kind)] = client


def unregister_client(file_id: int, client: httpx.Client, *, kind: str = "report") -> None:
    key = scope_key(file_id, kind)
    with _lock:
        if _active_clients.get(key) is client:
            _active_clients.pop(key, None)


def clear(file_id: int, *, kind: str = "report") -> None:
    key = scope_key(file_id, kind)
    with _lock:
        _cancelled.pop(key, None)
        _active_clients.pop(key, None)
        _running.discard(key)


def maybe_raise_cancelled(
    file_id: Optional[int],
    exc: Exception,
    *,
    kind: str = "report",
) -> None:
    """Re-raise as GenerationCancelled when the user requested cancellation."""
    if file_id is not None and is_cancelled(file_id, kind=kind):
        raise GenerationCancelled(f"{kind} cancelled by user") from exc
