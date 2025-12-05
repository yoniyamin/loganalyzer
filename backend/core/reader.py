import os
import re
import threading
from collections import OrderedDict
from sqlalchemy.orm import Session
from sqlalchemy import select
from backend.database import LogFile, LogIndex
from typing import List, Optional, Dict, Any, Tuple

# Global LRU cache for line data - shared across requests
# Key: (file_id, start_line, limit) -> lines list
# Max 50 cached chunks (about 5000 lines at 100 lines per chunk)
_line_cache: OrderedDict = OrderedDict()
_cache_lock = threading.Lock()
_CACHE_MAX_SIZE = 50

# Global file handle cache to avoid reopening files
# Key: file_path -> (file_handle, last_access_time)
_file_handles: Dict[str, Any] = {}
_handle_lock = threading.Lock()


def _get_cached_lines(file_id: int, start_line: int, limit: int) -> Optional[List[str]]:
    """Get lines from cache if available."""
    key = (file_id, start_line, limit)
    with _cache_lock:
        if key in _line_cache:
            # Move to end (most recently used)
            _line_cache.move_to_end(key)
            return _line_cache[key]
    return None


def _cache_lines(file_id: int, start_line: int, limit: int, lines: List[str]):
    """Cache lines with LRU eviction."""
    key = (file_id, start_line, limit)
    with _cache_lock:
        if key in _line_cache:
            _line_cache.move_to_end(key)
        else:
            _line_cache[key] = lines
            # Evict oldest if over capacity
            while len(_line_cache) > _CACHE_MAX_SIZE:
                _line_cache.popitem(last=False)


def clear_file_cache(file_id: int = None):
    """Clear cache for a specific file or all files."""
    with _cache_lock:
        if file_id is None:
            _line_cache.clear()
        else:
            keys_to_remove = [k for k in _line_cache if k[0] == file_id]
            for key in keys_to_remove:
                del _line_cache[key]


class LogReader:
    def __init__(self, db: Session, file_id: int):
        self.db = db
        self.file_id = file_id
        self.log_file = db.query(LogFile).filter(LogFile.id == file_id).first()
        if not self.log_file:
            raise ValueError(f"File ID {file_id} not found")
        self.file_path = self.log_file.file_path
        self._index_cache: Dict[int, Tuple[int, int]] = {}  # line_number -> (offset, cached_line)

    def _get_offset_for_line(self, line_number: int) -> Tuple[int, int]:
        """Find the closest byte offset for a given line number."""
        # Check local cache first
        if line_number in self._index_cache:
            return self._index_cache[line_number]
        
        # Find index entry <= line_number
        idx = self.db.query(LogIndex).filter(
            LogIndex.file_id == self.file_id,
            LogIndex.line_number <= line_number
        ).order_by(LogIndex.line_number.desc()).first()
        
        if idx:
            result = (idx.byte_offset, idx.line_number)
        else:
            result = (0, 0)
        
        # Cache the result
        self._index_cache[line_number] = result
        return result

    def read_lines(self, start_line: int, limit: int = 100) -> Dict[str, Any]:
        """Read a chunk of lines starting from start_line with caching."""
        if not os.path.exists(self.file_path):
            return {"lines": [], "start": start_line, "count": 0, "total": 0}

        # Ensure start_line is within bounds
        start_line = max(0, start_line)
        total = self.log_file.line_count or 0
        
        if start_line >= total:
            return {"lines": [], "start": start_line, "end": start_line, "total": total}

        # Check cache first
        cached = _get_cached_lines(self.file_id, start_line, limit)
        if cached is not None:
            return {
                "lines": cached,
                "start": start_line,
                "end": start_line + len(cached),
                "total": total
            }

        offset, current_line = self._get_offset_for_line(start_line)
        
        lines = []
        with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            
            # Skip lines if we landed before start_line (due to sparse index)
            while current_line < start_line:
                if not f.readline():
                    break
                current_line += 1
            
            # Read required lines - strip newlines server-side
            while len(lines) < limit:
                line = f.readline()
                if not line:
                    break
                lines.append(line.rstrip('\n\r'))
        
        # Cache the result
        _cache_lines(self.file_id, start_line, limit, lines)
                
        return {
            "lines": lines,
            "start": start_line,
            "end": start_line + len(lines),
            "total": total
        }

    def read_lines_centered(self, center_line: int, before: int = 50, after: int = 50) -> Dict[str, Any]:
        """
        Read lines centered around a specific line number.
        Returns lines both before and after the center line in a single call.
        More efficient for jumping to a specific location.
        """
        if not os.path.exists(self.file_path):
            return {"lines": [], "start": 0, "center": center_line, "end": 0, "total": 0}

        total = self.log_file.line_count or 0
        
        # Calculate actual start and limit
        start_line = max(0, center_line - before)
        end_line = min(total, center_line + after + 1)
        limit = end_line - start_line
        
        # Use the regular read_lines which has caching
        result = self.read_lines(start_line, limit)
        result["center"] = center_line
        
        return result

    def search(self, pattern: str, limit: int = 100, case_sensitive: bool = False) -> List[Dict[str, Any]]:
        """
        Stream search the file for regex matches.
        Optimized with early termination and pre-compiled regex.
        """
        file_path = self.log_file.file_path
        if not os.path.exists(file_path):
            return []

        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            regex = re.compile(pattern, flags)
        except re.error:
            return []

        matches = []
        line_idx = 0
        
        # Use larger buffer for better I/O performance
        with open(file_path, "r", encoding="utf-8", errors="replace", buffering=1024*1024) as f:
            for line in f:
                if regex.search(line):
                    matches.append({
                        "line": line_idx,
                        "text": line.rstrip('\n\r')
                    })
                    if len(matches) >= limit:
                        break
                line_idx += 1
                
        return matches


