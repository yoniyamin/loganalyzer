import os
import re
from sqlalchemy.orm import Session
from sqlalchemy import select
from backend.database import LogFile, LogIndex
from typing import List, Optional, Dict, Any

class LogReader:
    def __init__(self, db: Session, file_id: int):
        self.db = db
        self.file_id = file_id
        self.log_file = db.query(LogFile).filter(LogFile.id == file_id).first()
        if not self.log_file:
            raise ValueError(f"File ID {file_id} not found")
        self.file_path = self.log_file.file_path

    def _get_offset_for_line(self, line_number: int) -> int:
        """Find the closest byte offset for a given line number."""
        # Find index entry <= line_number
        idx = self.db.query(LogIndex).filter(
            LogIndex.file_id == self.file_id,
            LogIndex.line_number <= line_number
        ).order_by(LogIndex.line_number.desc()).first()
        
        if idx:
            return idx.byte_offset, idx.line_number
        return 0, 0

    def read_lines(self, start_line: int, limit: int = 100) -> Dict[str, Any]:
        """Read a chunk of lines starting from start_line."""
        if not os.path.exists(self.file_path):
            return {"lines": [], "start": start_line, "count": 0}

        offset, current_line = self._get_offset_for_line(start_line)
        
        lines = []
        with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            
            # Skip lines if we landed before start_line (due to sparse index)
            while current_line < start_line:
                if not f.readline():
                    break
                current_line += 1
            
            # Read required lines
            while len(lines) < limit:
                line = f.readline()
                if not line:
                    break
                lines.append(line)
                
        return {
            "lines": lines,
            "start": start_line,
            "end": start_line + len(lines),
            "total": self.log_file.line_count
        }

    def search(self, pattern: str, limit: int = 100, case_sensitive: bool = False) -> List[Dict[str, Any]]:
        """
        Stream search the file for regex matches.
        Note: This can be slow for huge files. 
        TODO: Optimize with grep or indexed search.
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
        
        # Optimization: Start searching from last known position? No, search is usually global.
        # Limit to first N matches to avoid hanging?
        
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if regex.search(line):
                    matches.append({
                        "line": line_idx,
                        "text": line.strip()
                    })
                    if len(matches) >= limit:
                        break
                line_idx += 1
                
        return matches


