"""JSON cache for the per-file adjacency graph.

Atomic write; fingerprinted via FileVersion; findings_epoch overlay only.
"""
import json
import os
import tempfile
import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.database import FileVersion
from backend.paths import _user_data_dir

logger = logging.getLogger(__name__)


def _graph_cache_dir() -> str:
    d = os.path.join(_user_data_dir(), "log_graph_cache")
    os.makedirs(d, exist_ok=True)
    return d


def _cache_path(file_id: int) -> str:
    return os.path.join(_graph_cache_dir(), f"graph_{file_id}.json")


def _fingerprint(fv: FileVersion) -> str:
    """Compute a cache fingerprint from FileVersion fields."""
    return f"{fv.schema_version}:{fv.extractor_version}:{fv.fts_version}:{fv.indexed_at}"


def load_cached_graph(db: Session, file_id: int):
    """Load adjacency graph from cache if fingerprint matches.

    Returns (AdjacencyGraph, True) on hit or (None, False) on miss.
    """
    from backend.core.graph import AdjacencyGraph

    path = _cache_path(file_id)
    if not os.path.exists(path):
        return None, False

    fv = db.query(FileVersion).filter(FileVersion.file_id == file_id).first()
    if not fv:
        return None, False

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Graph cache read error for file {file_id}: {e}")
        return None, False

    cached_fp = data.get("_fingerprint")
    current_fp = _fingerprint(fv)
    if cached_fp != current_fp:
        return None, False

    graph = AdjacencyGraph.from_dict(data)
    return graph, True


def save_graph_cache(db: Session, file_id: int, graph) -> bool:
    """Atomically write the adjacency graph to the cache file."""
    fv = db.query(FileVersion).filter(FileVersion.file_id == file_id).first()
    if not fv:
        return False

    data = graph.to_dict()
    data["_fingerprint"] = _fingerprint(fv)
    data["_file_id"] = file_id

    path = _cache_path(file_id)
    cache_dir = _graph_cache_dir()

    try:
        fd, tmp_path = tempfile.mkstemp(dir=cache_dir, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        # Atomic replace
        if os.path.exists(path):
            os.replace(tmp_path, path)
        else:
            os.rename(tmp_path, path)
        return True
    except OSError as e:
        logger.warning(f"Graph cache write error for file {file_id}: {e}")
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return False


def invalidate_cache(file_id: int):
    """Remove cache file for a file (called on reindex)."""
    path = _cache_path(file_id)
    if os.path.exists(path):
        try:
            os.unlink(path)
        except OSError:
            pass
