"""
Centralized path resolution for frozen (PyInstaller) and development modes.

In development: all paths resolve relative to the project root.
When frozen:
  - Read-only assets (static/, chroma_kb/, data/) stay alongside the .exe.
  - Writable user data (DB, uploads, chroma_db/) goes to %LOCALAPPDATA%.
"""

import os
import sys

APP_NAME = "ReplicateLogAnalyzer"

_FROZEN = getattr(sys, "frozen", False)


def _project_root() -> str:
    """Root of the source tree (dev) or the PyInstaller bundle dir (frozen)."""
    if _FROZEN:
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _user_data_dir() -> str:
    """Per-user writable directory for runtime data."""
    if _FROZEN:
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        return os.path.join(base, APP_NAME)
    return _project_root()


# ── Read-only assets (shipped with the app) ─────────────────────────

def static_dir() -> str:
    return os.path.join(_project_root(), "static")


def chroma_kb_dir() -> str:
    """Shipped KB + release notes vector store (read-only at runtime)."""
    return os.path.join(_project_root(), "chroma_kb")


def release_notes_cache_path() -> str:
    return os.path.join(_project_root(), "data", "release_notes_cache.json")


# ── Writable user data ──────────────────────────────────────────────

def db_path() -> str:
    d = _user_data_dir()
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "log_analyzer.db")


def chroma_db_dir() -> str:
    """User-local vector store for log embeddings (writable)."""
    d = os.path.join(_user_data_dir(), "chroma_db")
    os.makedirs(d, exist_ok=True)
    return d


def upload_dir() -> str:
    d = os.path.join(_user_data_dir(), "uploads")
    os.makedirs(d, exist_ok=True)
    return d
