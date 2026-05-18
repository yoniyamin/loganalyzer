from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import shutil
import os
import uuid
from datetime import datetime

from backend.database import get_db, LogFile, LogStats, LogPerformance, LogError, LogIndex, LogOracleRedoRead, LogOracleRedoLogSession, UserSettings
from backend.core.indexer import process_log_file
from backend.core.reader import LogReader
from backend.paths import upload_dir

router = APIRouter()

UPLOAD_DIR = upload_dir()

class FilePathRequest(BaseModel):
    path: str

@router.post("/files/local")
async def register_local_file(
    background_tasks: BackgroundTasks,
    request: FilePathRequest,
    db: Session = Depends(get_db)
):
    """Register a local file path for analysis without uploading."""
    file_path = request.path.strip()
    
    # Remove quotes if user pasted path with quotes
    if file_path.startswith('"') and file_path.endswith('"'):
        file_path = file_path[1:-1]
        
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found at path: {file_path}")
    
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=400, detail="Path is not a file")

    filename = os.path.basename(file_path)
    
    # Check if file already exists in database
    existing_file = db.query(LogFile).filter(LogFile.file_path == file_path).first()
    
    if existing_file:
        # File already exists - re-index it
        # Clear existing indexes and stats
        db.query(LogIndex).filter(LogIndex.file_id == existing_file.id).delete()
        db.query(LogPerformance).filter(LogPerformance.file_id == existing_file.id).delete()
        db.query(LogStats).filter(LogStats.file_id == existing_file.id).delete()
        db.query(LogError).filter(LogError.file_id == existing_file.id).delete()
        
        # Update status
        existing_file.status = "indexing"
        existing_file.line_count = 0
        existing_file.upload_time = datetime.utcnow()
        db.commit()
        
        # Trigger re-indexing
        background_tasks.add_task(process_log_file, db, existing_file.id)
        
        return {"id": existing_file.id, "filename": existing_file.filename, "status": "indexing"}
    
    # Create new DB Entry
    log_file = LogFile(
        filename=filename,
        file_path=file_path,
        status="indexing",
        upload_time=datetime.utcnow()
    )
    db.add(log_file)
    db.commit()
    db.refresh(log_file)
    
    # Trigger Indexing
    background_tasks.add_task(process_log_file, db, log_file.id)
    
    return {"id": log_file.id, "filename": log_file.filename, "status": "indexing"}

@router.post("/upload")
async def upload_log(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # Save file
    file_ext = os.path.splitext(file.filename)[1]
    safe_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Create DB Entry
    log_file = LogFile(
        filename=file.filename,
        file_path=file_path,
        status="indexing",
        upload_time=datetime.utcnow()
    )
    db.add(log_file)
    db.commit()
    db.refresh(log_file)
    
    # Trigger Indexing
    background_tasks.add_task(process_log_file, db, log_file.id)
    
    return {"id": log_file.id, "filename": log_file.filename, "status": "indexing"}

@router.get("/files")
def list_files(db: Session = Depends(get_db)):
    files = db.query(LogFile).order_by(LogFile.upload_time.desc()).limit(20).all()
    file_ids = [f.id for f in files]
    range_map = {}
    if file_ids:
        rows = (
            db.query(
                LogIndex.file_id,
                func.min(LogIndex.timestamp).label("tmin"),
                func.max(LogIndex.timestamp).label("tmax"),
            )
            .filter(LogIndex.file_id.in_(file_ids), LogIndex.timestamp.isnot(None))
            .group_by(LogIndex.file_id)
            .all()
        )
        range_map = {r.file_id: (r.tmin, r.tmax) for r in rows}

    out = []
    for f in files:
        tmin, tmax = range_map.get(f.id, (None, None))
        out.append(
            {
                "id": f.id,
                "filename": f.filename,
                "file_path": f.file_path,
                "status": f.status,
                "line_count": f.line_count,
                "size_bytes": f.size_bytes,
                "upload_time": f.upload_time.isoformat() if f.upload_time else None,
                "indexed_at": f.upload_time.isoformat() if f.upload_time else None,
                "log_time_start": tmin.isoformat() if tmin else None,
                "log_time_end": tmax.isoformat() if tmax else None,
                "error": f.error_message,
            }
        )
    return out

@router.get("/files/{file_id}")
def get_file_status(file_id: int, db: Session = Depends(get_db)):
    f = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    return {
        "id": f.id,
        "filename": f.filename,
        "status": f.status,
        "line_count": f.line_count,
        "size_bytes": f.size_bytes,
        "error": f.error_message
    }

@router.get("/files/{file_id}/summary")
def get_file_summary(file_id: int, db: Session = Depends(get_db)):
    f = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")

    stats = db.query(LogStats).filter(LogStats.file_id == file_id).all()
    
    # Latency Stats
    perfs = db.query(LogPerformance).filter(LogPerformance.file_id == file_id).all()
    perf_summary = {}
    if perfs:
        sources = [p.source_latency for p in perfs]
        targets = [p.target_latency for p in perfs]
        handlings = [p.handling_latency for p in perfs]
        perf_summary = {
            "count": len(perfs),
            "source": {
                "min": min(sources), "max": max(sources), "avg": sum(sources)/len(sources)
            },
            "target": {
                "min": min(targets), "max": max(targets), "avg": sum(targets)/len(targets)
            },
            "handling": {
                "min": min(handlings), "max": max(handlings), "avg": sum(handlings)/len(handlings)
            }
        }

    return {
        "filename": f.filename,
        "file_size": f.size_bytes,
        "line_count": f.line_count,
        "components": [
            {
                "name": s.component,
                "thread": s.thread_id,
                "count": s.message_count,
                "first_ts": s.first_ts,
                "last_ts": s.last_ts
            } for s in stats
        ],
        "performance": perf_summary
    }

@router.get("/files/{file_id}/lines")
def get_lines(
    file_id: int, 
    start: int = 0, 
    limit: int = 100, 
    center: Optional[int] = None,
    before: int = 50,
    after: int = 50,
    db: Session = Depends(get_db)
):
    """
    Get log lines. Two modes:
    1. Sequential: start + limit (default)
    2. Centered: center + before + after (for jumping to a specific line)
    """
    try:
        reader = LogReader(db, file_id)
        if center is not None:
            return reader.read_lines_centered(center, before, after)
        return reader.read_lines(start, limit)
    except ValueError:
        raise HTTPException(status_code=404, detail="File not found")

@router.get("/files/{file_id}/search")
def search_lines(
    file_id: int,
    q: str,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    try:
        reader = LogReader(db, file_id)
        return reader.search(q, limit)
    except ValueError:
        raise HTTPException(status_code=404, detail="File not found")

@router.get("/files/{file_id}/performance")
def get_performance_data(file_id: int, db: Session = Depends(get_db)):
    """Get detailed performance data points for graphing."""
    f = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    
    perfs = db.query(LogPerformance).filter(LogPerformance.file_id == file_id).order_by(LogPerformance.timestamp).all()
    
    return [
        {
            "timestamp": p.timestamp.isoformat() if p.timestamp else None,
            "line_number": p.line_number,  # Now we have the actual line number!
            "source_latency": p.source_latency,
            "target_latency": p.target_latency,
            "handling_latency": p.handling_latency
        } for p in perfs
    ]

@router.get("/files/{file_id}/task-properties")
def get_task_properties(file_id: int, db: Session = Depends(get_db)):
    """Extract task properties from the log file."""
    import re
    
    f = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    
    if not os.path.exists(f.file_path):
        raise HTTPException(status_code=404, detail="File not found at path")
    
    properties = {
        "task_info": None,
        "loggers": [],
        "run_mode": None,
        "is_rollover": False
    }
    
    try:
        # Read first 1000 lines to get task properties
        with open(f.file_path, "r", encoding="utf-8", errors="replace") as file:
            for i, line in enumerate(file):
                if i > 1000:  # Only check first 1000 lines
                    break
                
                # Check for log rollover (at_logger.c:1775)
                if "(at_logger.c:1775)" in line and "rolled over" in line:
                    properties["is_rollover"] = True
                
                # Extract task server info (at_logger.c:2770)
                if "(at_logger.c:2770)" in line and "Task Server Log" in line:
                    # More flexible parsing - extract task name first
                    task_name_match = re.search(r'Task Server Log - (\S+)', line)
                    if task_name_match:
                        task_name = task_name_match.group(1)
                        
                        # Extract version (V followed by numbers and dots)
                        version_match = re.search(r'V([\d.]+)', line)
                        version = version_match.group(1) if version_match else "Unknown"
                        
                        # Extract host (word after version, before OS info)
                        host_match = re.search(r'V[\d.]+\s+(\S+)', line)
                        host = host_match.group(1) if host_match else "Unknown"
                        
                        # Extract PID
                        pid_match = re.search(r'PID:\s+(\d+)', line)
                        pid = pid_match.group(1) if pid_match else "Unknown"
                        
                        # Extract OS info (between host and Revision or PID)
                        os_match = re.search(r'V[\d.]+\s+\S+\s+(.+?)(?:,\s+Revision:|,\s+PID:)', line)
                        os_info = os_match.group(1).strip() if os_match else "Unknown"
                        
                        # Extract start time
                        start_time_match = re.search(r'started at (.+?)(?:\s+\(at_logger\.c:2770\))?$', line)
                        start_time = start_time_match.group(1).strip() if start_time_match else "Unknown"
                        
                        properties["task_info"] = {
                            "task_name": task_name,
                            "version": version,
                            "host": host,
                            "os_info": os_info,
                            "pid": pid,
                            "start_time": start_time
                        }
                
                # Extract logger level changes (at_logger.c:3018)
                if "(at_logger.c:3018)" in line and "log level" in line:
                    # Parse: The log level for 'TARGET_APPLY' has been changed from 'INFO' to 'TRACE'.
                    match = re.search(
                        r"log level for '([^']+)' has been changed from '([^']+)' to '([^']+)'",
                        line
                    )
                    if match:
                        properties["loggers"].append({
                            "component": match.group(1),
                            "from_level": match.group(2),
                            "to_level": match.group(3)
                        })
                
                # Extract run mode (replicationtask.c:1868)
                if "(replicationtask.c:1868)" in line and "running" in line:
                    # Parse: Task 'P1JRNC_DATABRICKS_1_B' running full load and CDC in fresh start mode
                    match = re.search(
                        r"Task '([^']+)' running (.+?) in (.+?) mode",
                        line
                    )
                    if match:
                        properties["run_mode"] = {
                            "task_name": match.group(1),
                            "running_mode": match.group(2),
                            "start_mode": match.group(3)
                        }
        
        return properties
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract properties: {str(e)}")

@router.get("/files/{file_id}/bulk-map")
def get_bulk_map_messages(file_id: int, limit: int = 500, db: Session = Depends(get_db)):
    """Get bulk map messages from the log file with gap to 'Finished applying' message."""
    import re
    from datetime import datetime
    
    try:
        f = db.query(LogFile).filter(LogFile.id == file_id).first()
        if not f or not os.path.exists(f.file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Read the entire log file
        bulk_map_messages = []
        finished_applying_messages = []
        
        with open(f.file_path, 'r', encoding='utf-8', errors='replace') as file:
            for line_num, line in enumerate(file, 1):
                # Find bulk_map messages
                if 'bulk_map:' in line and 'seq' in line:
                    bulk_map_messages.append({
                        'line': line_num,
                        'text': line.strip()
                    })
                
                # Find Finished applying messages
                if 'Finished applying' in line and 'events for table' in line:
                    finished_applying_messages.append({
                        'line': line_num,
                        'text': line.strip()
                    })
                
                # Stop if we have enough bulk_map messages
                if len(bulk_map_messages) >= limit:
                    break
        
        # Now match bulk_map messages with their corresponding Finished applying messages
        for bulk_msg in bulk_map_messages:
            # Extract table name from bulk_map message
            # Format: bulk_map: seq X:Y OPERATION 'SCHEMA'.'TABLE' (id=Z)
            table_match = re.search(r"(?:INSERT|UPDATE|DELETE|MERGE)\s+'([^']+)'\.+'([^']+)'", bulk_msg['text'])
            bulk_timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', bulk_msg['text'])
            
            if table_match and bulk_timestamp_match:
                schema = table_match.group(1)
                table = table_match.group(2)
                full_table = f"{schema}.{table}"
                bulk_timestamp = datetime.fromisoformat(bulk_timestamp_match.group(1))
                
                # Find the next Finished applying message for this table after this bulk_map
                finished_msg = None
                finished_timestamp = None
                
                for fin_msg in finished_applying_messages:
                    # Check if this finished message is for the same table
                    if f"'{schema}'.'{table}'" in fin_msg['text'] or f"'{schema}'.'{table.upper()}'" in fin_msg['text'] or f"'{schema}'.'{table.lower()}'" in fin_msg['text']:
                        # Check if it comes after the bulk_map message
                        if fin_msg['line'] > bulk_msg['line']:
                            fin_timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', fin_msg['text'])
                            if fin_timestamp_match:
                                finished_timestamp = datetime.fromisoformat(fin_timestamp_match.group(1))
                                finished_msg = fin_msg
                                break
                
                # Calculate gap if we found a matching finished message
                if finished_msg and finished_timestamp:
                    gap_seconds = (finished_timestamp - bulk_timestamp).total_seconds()
                    bulk_msg['gap_to_finish'] = gap_seconds
                    bulk_msg['finish_line'] = finished_msg['line']
                else:
                    bulk_msg['gap_to_finish'] = None
                    bulk_msg['finish_line'] = None
        
        # Calculate insights for bulk map efficiency
        insights = []
        stats = {}
        
        if bulk_map_messages:
            # Parse row counts and operations from messages
            table_stats = {}  # table -> {single_record: 0, total: 0, row_counts: [], gaps: []}
            
            for msg in bulk_map_messages:
                # Extract sequence range: seq 1:63 or seq 1:1
                seq_match = re.search(r'seq\s+(\d+):(\d+)', msg['text'])
                table_match = re.search(r"(?:INSERT|UPDATE|DELETE|MERGE|UNKNOWN)\s+'([^']+)'\.+'([^']+)'", msg['text'])
                
                if seq_match and table_match:
                    seq_start = int(seq_match.group(1))
                    seq_end = int(seq_match.group(2))
                    row_count = seq_end - seq_start + 1
                    table_name = f"{table_match.group(1)}.{table_match.group(2)}"
                    
                    if table_name not in table_stats:
                        table_stats[table_name] = {
                            "single_record": 0,
                            "total": 0,
                            "row_counts": [],
                            "gaps": []
                        }
                    
                    table_stats[table_name]["total"] += 1
                    table_stats[table_name]["row_counts"].append(row_count)
                    
                    if msg.get('gap_to_finish') is not None:
                        table_stats[table_name]["gaps"].append(msg['gap_to_finish'])
                    
                    if row_count == 1:
                        table_stats[table_name]["single_record"] += 1
            
            # Compute overall stats
            total_ops = sum(ts["total"] for ts in table_stats.values())
            total_single = sum(ts["single_record"] for ts in table_stats.values())
            all_row_counts = [rc for ts in table_stats.values() for rc in ts["row_counts"]]
            all_gaps = [g for ts in table_stats.values() for g in ts["gaps"]]
            
            avg_batch_size = sum(all_row_counts) / len(all_row_counts) if all_row_counts else 0
            avg_gap = sum(all_gaps) / len(all_gaps) if all_gaps else 0
            
            stats = {
                "total_operations": total_ops,
                "single_record_operations": total_single,
                "single_record_percent": round(total_single * 100 / total_ops, 1) if total_ops > 0 else 0,
                "avg_batch_size": round(avg_batch_size, 1),
                "max_batch_size": max(all_row_counts) if all_row_counts else 0,
                "avg_gap_seconds": round(avg_gap, 2),
                "tables_count": len(table_stats),
                "per_table": {
                    name: {
                        "total_ops": ts["total"],
                        "single_record_ops": ts["single_record"],
                        "single_record_percent": round(ts["single_record"] * 100 / ts["total"], 1) if ts["total"] > 0 else 0,
                        "avg_batch_size": round(sum(ts["row_counts"]) / len(ts["row_counts"]), 1) if ts["row_counts"] else 0,
                        "avg_gap": round(sum(ts["gaps"]) / len(ts["gaps"]), 2) if ts["gaps"] else None
                    }
                    for name, ts in sorted(table_stats.items())
                }
            }
            
            # INSIGHT 1: High percentage of single-record operations
            if total_single > 0 and total_ops > 0:
                single_pct = total_single * 100 / total_ops
                if single_pct > 20:
                    # Find which tables have the most single-record ops
                    worst_tables = sorted(
                        [(name, ts["single_record"], ts["total"]) for name, ts in table_stats.items() if ts["single_record"] > 0],
                        key=lambda x: x[1],
                        reverse=True
                    )[:3]
                    
                    insights.append({
                        "type": "single_record_inefficiency",
                        "severity": "warning" if single_pct > 40 else "info",
                        "title": "Single-Record Operations Detected",
                        "message": f"{total_single} of {total_ops} operations ({single_pct:.0f}%) are single-record (1:1) batches. This is inefficient compared to multi-record batches.",
                        "recommendation": "Single-record operations often indicate frequent small transactions or primary key conflicts forcing one-by-one processing. Review transaction batching settings.",
                        "details": {
                            "single_record_count": total_single,
                            "total_operations": total_ops,
                            "worst_tables": [{"table": t[0], "single": t[1], "total": t[2]} for t in worst_tables]
                        }
                    })
            
            # INSIGHT 2: Small average batch sizes
            if avg_batch_size < 10 and total_ops > 5:
                insights.append({
                    "type": "small_batch_size",
                    "severity": "info",
                    "title": "Small Average Batch Size",
                    "message": f"Average batch size is only {avg_batch_size:.1f} records. Larger batches would improve throughput.",
                    "recommendation": "Consider adjusting batch size settings or reviewing why batches are being closed early (timeouts, memory, PK conflicts).",
                    "details": {
                        "avg_batch_size": round(avg_batch_size, 1),
                        "max_batch_size": max(all_row_counts) if all_row_counts else 0
                    }
                })
            
            # INSIGHT 3: High variance in apply times
            if len(all_gaps) >= 3:
                gap_std = (sum((g - avg_gap) ** 2 for g in all_gaps) / len(all_gaps)) ** 0.5
                if gap_std > avg_gap * 0.5 and avg_gap > 1:  # High variance
                    slow_ops = [g for g in all_gaps if g > avg_gap + gap_std]
                    insights.append({
                        "type": "apply_time_variance",
                        "severity": "info",
                        "title": "Variable Apply Times",
                        "message": f"Apply times vary significantly (avg: {avg_gap:.1f}s, std: {gap_std:.1f}s). {len(slow_ops)} operations took longer than expected.",
                        "recommendation": "Check for table locks, network issues, or target database load during slow operations.",
                        "details": {
                            "avg_gap": round(avg_gap, 2),
                            "std_gap": round(gap_std, 2),
                            "slow_operation_count": len(slow_ops)
                        }
                    })
        
        return {
            "messages": bulk_map_messages[:limit],
            "stats": stats,
            "insights": insights
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")

@router.get("/files/{file_id}/bulk-activity")
def get_bulk_activity_analysis(file_id: int, db: Session = Depends(get_db)):
    """Analyze bulk apply activity similar to apply_summary.pl script."""
    import re
    from collections import defaultdict
    
    f = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    
    if not os.path.exists(f.file_path):
        raise HTTPException(status_code=404, detail="File not found at path")
    
    analysis = {
        "batches": [],
        "one_by_one": [],
        "per_table_stats": {},
        "file_operations": [],  # New: track file compression/upload operations
        "bulk_finish_reasons": {},  # New: track finish reason counts
        "summary": {
            "total_batches": 0,
            "total_changes": 0,
            "total_applies": 0,
            "one_by_one_switches": 0,
            "one_by_one_events": 0,
            "no_bulk_total": 0,
            "no_pk_total": 0,
            "file_operations_count": 0,
            "file_compress_time_total": 0,
            "file_upload_time_total": 0
        }
    }
    
    try:
        batch_data = {
            "changes": 0,
            "applies": 0,
            "start_time": None,
            "tables": set(),
            "finish_reason": None
        }
        
        one_by_one_active = False
        one_by_one_start = None
        one_by_one_table = None
        one_by_one_failed = 0
        
        per_table = defaultdict(lambda: {"INSERT": 0, "UPDATE": 0, "DELETE": 0, "TOTAL": 0})
        no_bulk_tables = defaultdict(int)
        no_pk_tables = defaultdict(int)
        
        # Track file operations by file name
        file_op_tracking = {}  # file_name -> {compress_start, compress_end, upload_end, tables, file_size}
        current_file_tables = set()  # Track which tables are in current file operation
        current_file_name = None  # Track the current file being processed
        
        lines = []
        try:
            with open(f.file_path, "r", encoding="utf-8", errors="replace") as file:
                for line_num, line in enumerate(file):
                    if line_num > 500000:  # Limit analysis to first 500k lines for performance
                        break
                    lines.append(line)
        except Exception as read_error:
            raise HTTPException(status_code=500, detail=f"Failed to read file: {str(read_error)}")
        
        try:
            for idx, line in enumerate(lines):
                try:
                    # Extract timestamp
                    ts_match = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', line)
                    timestamp = ts_match.group(1) if ts_match else None
                    
                    # Skip non-TARGET_APPLY lines for most analysis
                    is_target_apply = 'TARGET_APPLY' in line
                    
                    # Detect apply sequences: "Going to run [insert|update|delete] statement, from seq X to seq Y"
                    # OR "Finished applying of N 'OPERATION' events for table 'SCHEMA'.'TABLE'"
                    if is_target_apply:
                        # Pattern 1: "Going to run insert statement, from seq 1 to seq 39"
                        if 'Going to run' in line and 'from seq' in line:
                            seq_match = re.search(r'from seq (\d+) to seq (\d+)', line)
                            verb_match = re.search(r'run (\w+) statement', line)
                            
                            if seq_match:
                                try:
                                    from_seq = int(seq_match.group(1))
                                    to_seq = int(seq_match.group(2))
                                    changes = to_seq - from_seq + 1
                                    
                                    batch_data["changes"] += changes
                                    batch_data["applies"] += 1
                                    
                                    if not batch_data["start_time"] and timestamp:
                                        batch_data["start_time"] = timestamp
                                    
                                    # Look backward a few lines for "Start applying" to get table and verb
                                    verb = 'INSERT'  # default
                                    table = 'UNKNOWN.TABLE'
                                    
                                    # Search previous 5 lines for context
                                    for prev_idx in range(max(0, idx - 5), idx):
                                        prev_line = lines[prev_idx]
                                        if 'Start applying' in prev_line:
                                            table_match = re.search(r"for table '([^']+)'\.?'([^']+)'", prev_line)
                                            op_match = re.search(r"'([A-Z]+) \(\d+\)'", prev_line)
                                            if table_match:
                                                table = f"{table_match.group(1)}.{table_match.group(2)}"
                                            if op_match:
                                                op_type = op_match.group(1)
                                                verb = 'MERGE' if op_type == 'UNKNOWN' else op_type
                                            break
                                    
                                    batch_data["tables"].add(table)
                                    per_table[table][verb] += changes
                                    per_table[table]["TOTAL"] += changes
                                except (ValueError, IndexError) as seq_error:
                                    continue
                        
                        # Pattern 2: "Finished applying of 39 'INSERT (1)' events for table"
                        elif 'Finished applying of' in line and 'events for table' in line:
                            finished_match = re.search(r"Finished applying of (\d+) '([A-Z]+) \(\d+\)' events for table '([^']+)'\.?'([^']+)'", line)
                            if finished_match:
                                try:
                                    changes = int(finished_match.group(1))
                                    op_type = finished_match.group(2)
                                    table = f"{finished_match.group(3)}.{finished_match.group(4)}"
                                    verb = 'MERGE' if op_type == 'UNKNOWN' else op_type
                                    
                                    # This is an alternative/additional data point
                                    batch_data["tables"].add(table)
                                    # Don't double-count if we already counted from "Going to run"
                                except (ValueError, IndexError) as finish_error:
                                    continue
                        
                        # Detect batch finish - only count when "Bulk finished." appears (actual batch close)
                        if 'Bulk finished.' in line:
                            # Only process if we have data to record
                            if batch_data["changes"] > 0:
                                # Determine the finish reason
                                reason = batch_data["finish_reason"] if batch_data["finish_reason"] else "Normal"
                                
                                analysis["batches"].append({
                                    "start_time": batch_data["start_time"],
                                    "end_time": timestamp,
                                    "changes": batch_data["changes"],
                                    "applies": batch_data["applies"],
                                    "tables": list(batch_data["tables"]),
                                    "finish_reason": reason
                                })
                                analysis["summary"]["total_batches"] += 1
                                analysis["summary"]["total_changes"] += batch_data["changes"]
                                analysis["summary"]["total_applies"] += batch_data["applies"]
                                
                                # Track finish reason counts ONLY when batch is actually recorded
                                reason_key = reason.split(' - ')[0] if ' - ' in reason else reason
                                analysis["bulk_finish_reasons"][reason_key] = analysis["bulk_finish_reasons"].get(reason_key, 0) + 1
                            
                            # Reset batch data
                            batch_data = {
                                "changes": 0,
                                "applies": 0,
                                "start_time": None,
                                "tables": set(),
                                "finish_reason": None
                            }
                        
                        # Detect finish reason lines (these set the reason, but don't close the batch yet)
                        elif 'Finish bulk because' in line or 'Finish Bulk because' in line:
                            reason = "Normal"
                            if 'memory' in line.lower():
                                reason = "MEM - Memory limit"
                            elif 'stream timeout' in line.lower():
                                reason = "TIM - Stream timeout"
                            elif 'bulk timeout' in line.lower():
                                reason = "TMO - Bulk timeout"
                            elif 'resume at the same' in line.lower():
                                reason = "RES - Resume"
                            batch_data["finish_reason"] = reason
                        
                        # Track PK conflict finish reasons
                        elif 'same bulk' in line and ('same PK' in line or 'changes PK' in line):
                            if 'INSERT' in line:
                                batch_data["finish_reason"] = "PKi - PK insert conflict"
                            elif 'Update' in line and 'updated' in line:
                                batch_data["finish_reason"] = "PKu - PK update conflict"
                            elif 'deleted' in line:
                                batch_data["finish_reason"] = "PKd - PK delete conflict"
                        
                        # Finished applying bulk changes for tables with PK
                        elif 'Finished applying bulk changes' in line and 'tables with PK' in line:
                            batch_data["finish_reason"] = "SNG - Single table"
                        
                        # Track bulk_map operations to know which table is being processed
                        if 'bulk_map:' in line:
                            # Extract table from bulk_map line: bulk_map: seq 1:6 UPDATE 'FICCOR'.'MAEART' (id=5)
                            bulk_map_match = re.search(r"bulk_map:.*?'([^']+)'\.+'([^']+)'", line)
                            if bulk_map_match:
                                table_key = f"{bulk_map_match.group(1)}.{bulk_map_match.group(2)}"
                                current_file_tables.add(table_key)
                        
                        # Track file operations (for file-based targets like Databricks)
                        # Track by FILE NAME, not by table (multiple tables can share one file)
                        # Order: "Going to send file" -> "going to compress file" -> "file compressed" -> "uploaded successfully"
                        if 'going to compress file' in line.lower() and 'CDC' in line:
                            # Extract file name: going to compress file 'C:\...\CDC00000001.csv' to '...'
                            file_match = re.search(r'\\(CDC[0-9A-Fa-f]+\.csv)', line)
                            if file_match:
                                current_file_name = file_match.group(1)
                                if current_file_name not in file_op_tracking:
                                    file_op_tracking[current_file_name] = {
                                        'compress_start': timestamp,
                                        'tables': list(current_file_tables)
                                    }
                        
                        elif 'file compressed' in line.lower() and current_file_name:
                            # Compression finished
                            if current_file_name in file_op_tracking:
                                file_op_tracking[current_file_name]['compress_end'] = timestamp
                        
                        elif 'was uploaded successfully' in line.lower() and 'CDC' in line:
                            # Extract file name and size: File C:\...\CDC00000001.csv.gz of size 2822 was uploaded
                            file_match = re.search(r'\\(CDC[0-9A-Fa-f]+\.csv)', line)
                            size_match = re.search(r'of size (\d+)', line)
                            
                            if file_match:
                                file_name = file_match.group(1)
                                file_size = int(size_match.group(1)) if size_match else 0
                                
                                # Create entry if it doesn't exist (fallback)
                                if file_name not in file_op_tracking:
                                    file_op_tracking[file_name] = {
                                        'compress_start': timestamp,
                                        'tables': list(current_file_tables)
                                    }
                                
                                file_op_tracking[file_name]['upload_end'] = timestamp
                                file_op_tracking[file_name]['file_size'] = file_size
                                
                                # Calculate durations
                                try:
                                    from datetime import datetime
                                    compress_start_dt = datetime.fromisoformat(file_op_tracking[file_name]['compress_start'])
                                    upload_end_dt = datetime.fromisoformat(file_op_tracking[file_name]['upload_end'])
                                    
                                    # Calculate times
                                    if 'compress_end' in file_op_tracking[file_name]:
                                        compress_end_dt = datetime.fromisoformat(file_op_tracking[file_name]['compress_end'])
                                        compress_time = abs((compress_end_dt - compress_start_dt).total_seconds())
                                        upload_time = abs((upload_end_dt - compress_end_dt).total_seconds())
                                    else:
                                        # Estimate if compress_end not available
                                        total = abs((upload_end_dt - compress_start_dt).total_seconds())
                                        compress_time = total * 0.1  # Compression is usually quick
                                        upload_time = total * 0.9  # Upload takes most time
                                    
                                    total_time = abs((upload_end_dt - compress_start_dt).total_seconds())
                                    
                                    # Format file size
                                    if file_size < 1024:
                                        size_str = f"{file_size} B"
                                    elif file_size < 1024 * 1024:
                                        size_str = f"{file_size / 1024:.1f} KB"
                                    else:
                                        size_str = f"{file_size / (1024 * 1024):.2f} MB"
                                    
                                    # Get tables for this file
                                    tables_list = file_op_tracking[file_name].get('tables', list(current_file_tables))
                                    tables_str = ', '.join(tables_list) if tables_list else 'N/A'
                                    
                                    # Calculate throughput (KB/s)
                                    throughput_kbps = (file_size / 1024) / upload_time if upload_time > 0 else 0
                                    
                                    analysis["file_operations"].append({
                                        "file_name": file_name,
                                        "tables": tables_str,
                                        "table_count": len(tables_list),
                                        "file_size": file_size,
                                        "file_size_str": size_str,
                                        "compress_start": file_op_tracking[file_name]['compress_start'],
                                        "compress_end": file_op_tracking[file_name].get('compress_end', ''),
                                        "upload_end": timestamp,
                                        "compress_time": round(compress_time, 2),
                                        "upload_time": round(upload_time, 2),
                                        "total_time": round(total_time, 2),
                                        "throughput_kbps": round(throughput_kbps, 2)
                                    })
                                    
                                    analysis["summary"]["file_operations_count"] += 1
                                    analysis["summary"]["file_compress_time_total"] += compress_time
                                    analysis["summary"]["file_upload_time_total"] += upload_time
                                except Exception as file_error:
                                    pass  # Skip if timestamp parsing fails
                                
                                # Clean up this file from tracking
                                if file_name in file_op_tracking:
                                    del file_op_tracking[file_name]
                                
                                # Reset for next file
                                current_file_name = None
                                current_file_tables.clear()
                        
                        # Detect one-by-one mode
                        if 'one-by-one' in line.lower():
                            if 'Applying' in line:
                                # Start of one-by-one
                                table_match = re.search(r"for table '([^']+)'\.?'([^']+)'", line)
                                if table_match and len(table_match.groups()) >= 2:
                                    one_by_one_table = f"{table_match.group(1)}.{table_match.group(2)}"
                                    one_by_one_active = True
                                    one_by_one_start = timestamp
                                    one_by_one_failed = 0
                            elif 'back to bulk' in line.lower():
                                # End of one-by-one
                                if one_by_one_active:
                                    analysis["one_by_one"].append({
                                        "table": one_by_one_table,
                                        "start_time": one_by_one_start,
                                        "end_time": timestamp,
                                        "failed_executions": one_by_one_failed
                                    })
                                    analysis["summary"]["one_by_one_switches"] += 1
                                    one_by_one_active = False
                        
                        # Count failed executions during one-by-one
                        if one_by_one_active and 'Failed to execute' in line:
                            one_by_one_failed += 1
                        
                        # Detect no bulk / no PK issues
                        if 'Apply no Bulk' in line:
                            table_match = re.search(r'table\s+(\d+)', line)
                            if table_match:
                                no_bulk_tables[table_match.group(1)] += 1
                                analysis["summary"]["no_bulk_total"] += 1
                        
                        if 'no PK for table' in line:
                            table_match = re.search(r'table\s+(\d+)', line)
                            if table_match:
                                no_pk_tables[table_match.group(1)] += 1
                                analysis["summary"]["no_pk_total"] += 1
                
                except Exception as line_error:
                    # Skip problematic lines and continue
                    continue
        
        except Exception as parse_error:
            raise HTTPException(status_code=500, detail=f"Failed parsing lines: {str(parse_error)}")
        
        # Convert per_table stats to list
        analysis["per_table_stats"] = [
            {
                "table": table,
                "insert": stats["INSERT"],
                "update": stats["UPDATE"],
                "delete": stats["DELETE"],
                "total": stats["TOTAL"]
            }
            for table, stats in sorted(per_table.items(), key=lambda x: x[1]["TOTAL"], reverse=True)
        ]
        
        # Generate file operations insights for performance bottleneck detection
        file_ops = analysis["file_operations"]
        if len(file_ops) >= 2:
            insights = []
            
            # Sort by file size to analyze
            sorted_by_size = sorted(file_ops, key=lambda x: x["file_size"])
            sorted_by_time = sorted(file_ops, key=lambda x: x["upload_time"])
            
            # Calculate statistics
            sizes = [op["file_size"] for op in file_ops]
            upload_times = [op["upload_time"] for op in file_ops]
            throughputs = [op["throughput_kbps"] for op in file_ops]
            
            min_size = min(sizes)
            max_size = max(sizes)
            avg_size = sum(sizes) / len(sizes)
            min_time = min(upload_times)
            max_time = max(upload_times)
            avg_time = sum(upload_times) / len(upload_times)
            avg_throughput = sum(throughputs) / len(throughputs) if throughputs else 0
            
            # Store stats for frontend
            analysis["file_ops_stats"] = {
                "min_size": min_size,
                "max_size": max_size,
                "avg_size": avg_size,
                "min_time": round(min_time, 2),
                "max_time": round(max_time, 2),
                "avg_time": round(avg_time, 2),
                "avg_throughput_kbps": round(avg_throughput, 2),
                "total_files": len(file_ops),
                "total_data_bytes": sum(sizes),
                "total_upload_time": round(sum(upload_times), 2)
            }
            
            # INSIGHT 1: Detect latency-bound uploads (small files taking long time)
            # If size ratio is high but time ratio is low, it's latency-bound
            size_ratio = max_size / min_size if min_size > 0 else 1
            
            # Find smallest and largest files
            smallest = sorted_by_size[0]
            largest = sorted_by_size[-1]
            
            # Check if small files take similar time as large files
            if size_ratio > 10:  # Significant size difference
                time_ratio = largest["upload_time"] / smallest["upload_time"] if smallest["upload_time"] > 0 else 1
                
                if time_ratio < 2:  # But upload times are similar
                    insights.append({
                        "type": "latency_bottleneck",
                        "severity": "warning",
                        "title": "Fixed Latency Overhead Detected",
                        "message": f"A {largest['file_size_str']} file and a {smallest['file_size_str']} file both took ~{smallest['upload_time']:.1f}s to upload. The upload time is dominated by network latency, not data transfer.",
                        "recommendation": "Consider batching more changes into fewer, larger files to reduce the impact of fixed latency overhead.",
                        "details": {
                            "smallest_file": smallest["file_name"],
                            "smallest_size": smallest["file_size_str"],
                            "smallest_time": smallest["upload_time"],
                            "largest_file": largest["file_name"],
                            "largest_size": largest["file_size_str"],
                            "largest_time": largest["upload_time"],
                            "size_ratio": round(size_ratio, 1),
                            "time_ratio": round(time_ratio, 2)
                        }
                    })
            
            # INSIGHT 2: Detect inefficient small file operations
            small_files = [op for op in file_ops if op["file_size"] < 10 * 1024]  # < 10KB
            if len(small_files) > len(file_ops) * 0.3:  # More than 30% are small
                total_small_time = sum(op["upload_time"] for op in small_files)
                insights.append({
                    "type": "many_small_files",
                    "severity": "info",
                    "title": "Many Small File Uploads",
                    "message": f"{len(small_files)} of {len(file_ops)} files ({len(small_files)*100//len(file_ops)}%) are under 10KB, consuming {total_small_time:.1f}s of upload time.",
                    "recommendation": "Small frequent batches may indicate aggressive batching settings. Consider increasing batch intervals or size thresholds.",
                    "details": {
                        "small_file_count": len(small_files),
                        "small_file_time": round(total_small_time, 2)
                    }
                })
            
            # INSIGHT 3: Calculate estimated fixed overhead
            # Use regression-like approach: if time doesn't scale with size, there's overhead
            if len(file_ops) >= 3 and size_ratio > 5:
                # Estimate fixed overhead as minimum upload time
                estimated_overhead = min_time
                
                # Calculate what throughput would be without overhead
                effective_throughputs = []
                for op in file_ops:
                    effective_time = op["upload_time"] - estimated_overhead
                    if effective_time > 0.1:  # At least 100ms of actual transfer
                        eff_throughput = (op["file_size"] / 1024) / effective_time
                        effective_throughputs.append(eff_throughput)
                
                if effective_throughputs:
                    avg_effective_throughput = sum(effective_throughputs) / len(effective_throughputs)
                    if avg_effective_throughput > avg_throughput * 1.5:  # Significant improvement
                        insights.append({
                            "type": "overhead_analysis",
                            "severity": "info",
                            "title": "Network Overhead Analysis",
                            "message": f"Estimated ~{estimated_overhead:.1f}s fixed overhead per upload (connection setup, auth, etc). Effective throughput when overhead is excluded: {avg_effective_throughput:.0f} KB/s vs observed {avg_throughput:.0f} KB/s.",
                            "recommendation": "Fixed overhead suggests optimizing connection reuse or reducing upload frequency would help.",
                            "details": {
                                "estimated_overhead_seconds": round(estimated_overhead, 2),
                                "observed_throughput_kbps": round(avg_throughput, 2),
                                "effective_throughput_kbps": round(avg_effective_throughput, 2)
                            }
                        })
            
            # INSIGHT 4: Throughput anomalies
            if len(throughputs) >= 3:
                throughput_std = (sum((t - avg_throughput) ** 2 for t in throughputs) / len(throughputs)) ** 0.5
                low_throughput_ops = [op for op in file_ops if op["throughput_kbps"] < avg_throughput - throughput_std and op["file_size"] > 50 * 1024]
                
                if low_throughput_ops:
                    insights.append({
                        "type": "throughput_anomaly",
                        "severity": "warning",
                        "title": "Throughput Anomalies Detected",
                        "message": f"{len(low_throughput_ops)} file(s) had significantly lower throughput than average. This may indicate network issues during those uploads.",
                        "recommendation": "Check network stability during the flagged upload times.",
                        "details": {
                            "affected_files": [op["file_name"] for op in low_throughput_ops],
                            "avg_throughput_kbps": round(avg_throughput, 2)
                        }
                    })
            
            analysis["file_ops_insights"] = insights
        
        return analysis
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze bulk activity: {str(e)}")

class ReindexRequest(BaseModel):
    """Request to re-index a file with optional re-embedding."""
    reembed: bool = False


@router.post("/files/{file_id}/reindex")
async def reindex_file(
    file_id: int,
    background_tasks: BackgroundTasks,
    request: Optional[ReindexRequest] = None,
    db: Session = Depends(get_db)
):
    """Re-index an existing log file, optionally re-embedding for AI analysis."""
    from backend.database import SessionLocal
    
    log_file = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not log_file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Check if file still exists
    if not os.path.exists(log_file.file_path):
        raise HTTPException(status_code=404, detail=f"File not found at path: {log_file.file_path}")
    
    # Clear existing indexes and stats
    db.query(LogIndex).filter(LogIndex.file_id == file_id).delete()
    db.query(LogPerformance).filter(LogPerformance.file_id == file_id).delete()
    db.query(LogOracleRedoRead).filter(LogOracleRedoRead.file_id == file_id).delete()
    db.query(LogOracleRedoLogSession).filter(LogOracleRedoLogSession.file_id == file_id).delete()
    db.query(LogStats).filter(LogStats.file_id == file_id).delete()
    db.query(LogError).filter(LogError.file_id == file_id).delete()
    db.commit()
    
    # If re-embedding requested, clear existing embeddings
    reembed = request.reembed if request else False
    embeddings_deleted = 0
    if reembed:
        try:
            from backend.llm.vectorstore import get_vector_store
            vector_store = get_vector_store()
            embeddings_deleted = vector_store.delete_file_embeddings(file_id)
        except Exception as e:
            # Log but don't fail - embeddings will be regenerated anyway
            import logging
            logging.getLogger(__name__).warning(f"Failed to clear embeddings for file {file_id}: {e}")
    
    # Set status to indexing
    log_file.status = "indexing"
    log_file.line_count = 0
    db.commit()
    
    # Trigger re-indexing in background with new session
    def reindex_task():
        new_db = SessionLocal()
        try:
            process_log_file(new_db, file_id)
        finally:
            new_db.close()
    
    background_tasks.add_task(reindex_task)
    
    message = "Re-indexing started"
    if reembed:
        message += f" (cleared {embeddings_deleted} embeddings for re-embedding)"
    
    return {"id": file_id, "filename": log_file.filename, "status": "indexing", "message": message}


@router.get("/files/{file_id}/issues")
def get_issues_with_context(
    file_id: int,
    context_lines: int = 5,
    db: Session = Depends(get_db)
):
    """
    Get all warnings and errors from the log file with context lines.
    Groups by error type/message for easier analysis.
    Includes timeline information for visualization.
    """
    import re
    from datetime import datetime
    
    f = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        # Read all lines from the file
        with open(f.file_path, 'r', encoding='utf-8', errors='replace') as log:
            all_lines = log.readlines()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")
    
    total_lines = len(all_lines)
    
    # Pattern to match warnings and errors
    # Matches: ]W: or ]E: (standard warnings/errors)
    # Also matches: SQL_ERROR, SqlState patterns
    issue_pattern = re.compile(
        r'\](E|W):|'  # Standard [COMPONENT]E: or ]W:
        r'SQL_ERROR\s+SqlState:\s*(\w+)\s+NativeError:\s*(\d+)|'  # SQL errors with code
        r'fatal\s+error|'  # Fatal errors
        r'Failed to execute|'  # Execution failures
        r'RetCode:\s*SQL_ERROR',  # ODBC errors
        re.IGNORECASE
    )
    
    # Timestamp pattern - matches various log timestamp formats
    timestamp_pattern = re.compile(
        r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?::\d+)?)'
    )
    
    # Find all issues and group them
    issues_by_type = {}
    
    # Track timeline info (all issues with their positions)
    timeline_events = []
    log_start_time = None
    log_end_time = None
    
    # Find first and last timestamps for the timeline
    for line in all_lines[:10]:  # Check first 10 lines
        ts_match = timestamp_pattern.search(line)
        if ts_match:
            log_start_time = ts_match.group(1)
            break
    
    for line in reversed(all_lines[-20:]):  # Check last 20 lines
        ts_match = timestamp_pattern.search(line)
        if ts_match:
            log_end_time = ts_match.group(1)
            break
    
    for line_num, line in enumerate(all_lines):
        match = issue_pattern.search(line)
        if match:
            # Determine issue type and extract error code if present
            line_stripped = line.strip()
            
            # Extract timestamp from the line
            ts_match = timestamp_pattern.search(line)
            timestamp = ts_match.group(1) if ts_match else None
            
            # Extract the component (e.g., TARGET_APPLY, SOURCE_CAPTURE)
            component_match = re.search(r'\[(\w+)\s*\]', line)
            component = component_match.group(1) if component_match else "UNKNOWN"
            
            # Determine severity
            if ']E:' in line:
                severity = 'error'
            elif ']W:' in line:
                severity = 'warning'
            elif 'fatal' in line.lower():
                severity = 'fatal'
            else:
                severity = 'error'  # SQL_ERROR etc
            
            # Extract SQL error code if present
            sql_match = re.search(r'SqlState:\s*(\w+)\s+NativeError:\s*(\d+)', line)
            error_code = None
            if sql_match:
                error_code = f"SqlState:{sql_match.group(1)} NativeError:{sql_match.group(2)}"
            
            # Create a simplified key for grouping (first part of message)
            # Extract the actual message part after the component
            msg_match = re.search(r'\][EWT]:\s*(.+?)(?:\s+\([^)]+\.\w+:\d+\))?$', line)
            if msg_match:
                message_summary = msg_match.group(1).strip()[:200]  # First 200 chars for full error message
            else:
                message_summary = line_stripped[:200]
            
            # Create a group key
            group_key = f"{severity}:{component}:{message_summary}"
            
            if group_key not in issues_by_type:
                issues_by_type[group_key] = {
                    'severity': severity,
                    'component': component,
                    'message_summary': message_summary,
                    'error_code': error_code,
                    'occurrences': []
                }
            
            # Get context lines
            start_idx = max(0, line_num - context_lines)
            end_idx = min(len(all_lines), line_num + context_lines + 1)
            
            context = {
                'line_number': line_num,
                'timestamp': timestamp,
                'text': line_stripped,
                'before': [{'line': i, 'text': all_lines[i].strip()} for i in range(start_idx, line_num)],
                'after': [{'line': i, 'text': all_lines[i].strip()} for i in range(line_num + 1, end_idx)]
            }
            
            issues_by_type[group_key]['occurrences'].append(context)
            
            # Add to timeline
            timeline_events.append({
                'line_number': line_num,
                'position': (line_num / total_lines) * 100 if total_lines > 0 else 0,
                'severity': severity,
                'timestamp': timestamp
            })
    
    # Convert to list and sort by severity then by count
    severity_order = {'fatal': 0, 'error': 1, 'warning': 2}
    issues_list = list(issues_by_type.values())
    issues_list.sort(key=lambda x: (severity_order.get(x['severity'], 3), -len(x['occurrences'])))
    
    # Calculate summary
    summary = {
        'total_issues': sum(len(i['occurrences']) for i in issues_list),
        'unique_issues': len(issues_list),
        'fatal_count': sum(len(i['occurrences']) for i in issues_list if i['severity'] == 'fatal'),
        'error_count': sum(len(i['occurrences']) for i in issues_list if i['severity'] == 'error'),
        'warning_count': sum(len(i['occurrences']) for i in issues_list if i['severity'] == 'warning')
    }
    
    # Timeline info
    timeline = {
        'start_time': log_start_time,
        'end_time': log_end_time,
        'total_lines': total_lines,
        'events': timeline_events
    }
    
    return {
        'summary': summary,
        'timeline': timeline,
        'issues': issues_list
    }


@router.get("/files/{file_id}/log-summary")
def get_log_summary(file_id: int, db: Session = Depends(get_db)):
    """
    Generate a textual summary of the log file without AI.
    Extracts key information about the task execution.
    """
    import re
    from datetime import datetime
    
    f = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        with open(f.file_path, 'r', encoding='utf-8', errors='replace') as log:
            all_lines = log.readlines()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")
    
    summary = {
        'task_name': None,
        'version': None,
        'server': None,
        'host': None,
        'os_info': None,
        'pid': None,
        'start_time': None,
        'end_time': None,
        'duration': None,
        'running_mode': None,
        'start_mode': None,
        'source_endpoint': None,
        'source_type': None,  # Database type (Oracle, SQL Server, etc.)
        'target_endpoint': None,
        'target_type': None,  # Target type (Snowflake, Databricks, etc.)
        'license_info': None,
        'tables_count': 0,
        'tables': [],
        'log_levels_changed': [],
        'error_count': 0,
        'warning_count': 0,
        'fatal_error': None,
        'sample_errors': [],  # First few errors with context
        'sample_warnings': [],  # First few warnings with context
        'bulk_operations': 0,
        'cdc_events_count': 0,
        'full_load_completed': False,
        'cdc_started': False,
        'key_events': [],
        'log_properly_closed': False,
        'incomplete_log_warning': None,
        'is_rollover': False,
        # Configuration details
        'config': {
            'bulk_timeout_ms': None,
            'parallel_apply_threads': None,
            'merge_enabled': False
        },
        # ODBC/Driver info
        'odbc_drivers': [],
        # Connection issues
        'connection_events': [],
        # Performance indicators
        'one_by_one_tables': [],  # Tables that went to one-by-one mode
    }
    
    first_timestamp = None
    last_timestamp = None
    
    for line_num, line in enumerate(all_lines):
        # Extract timestamp
        ts_match = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', line)
        if ts_match:
            try:
                ts = datetime.fromisoformat(ts_match.group(1))
                if first_timestamp is None:
                    first_timestamp = ts
                last_timestamp = ts
            except:
                pass
        
        # Task Server Log line - extract comprehensive task info
        if 'Task Server Log -' in line:
            task_match = re.search(r'Task Server Log - (\S+)\s+\(V([\d.]+)\s+(\S+)', line)
            if task_match:
                summary['task_name'] = task_match.group(1)
                summary['version'] = task_match.group(2)
                summary['host'] = task_match.group(3)
                summary['server'] = task_match.group(3)
                
                # Extract OS info
                os_match = re.search(r'V[\d.]+\s+\S+\s+(.+?)(?:,\s+Revision:|,\s+PID:)', line)
                if os_match:
                    summary['os_info'] = os_match.group(1).strip()
                
                # Extract PID
                pid_match = re.search(r'PID:\s+(\d+)', line)
                if pid_match:
                    summary['pid'] = pid_match.group(1)
        
        # License information
        if 'Licensed to' in line and not summary['license_info']:
            license_match = re.search(r'Licensed to\s+([^,]+),?\s*(.*?)(?:\s*\(|,\s*sources:)', line)
            if license_match:
                license_holder = license_match.group(1).strip()
                license_type = license_match.group(2).strip() if license_match.group(2) else ''
                summary['license_info'] = f"{license_holder} - {license_type}" if license_type else license_holder
        
        # Check for log rollover
        if '(at_logger.c:1775)' in line and 'rolled over' in line:
            summary['is_rollover'] = True
        
        # Running mode
        if "Task '" in line and "running" in line:
            mode_match = re.search(r"Task '([^']+)' running (.+?) in (.+?) mode", line)
            if mode_match:
                summary['task_name'] = mode_match.group(1)
                summary['running_mode'] = mode_match.group(2).strip()
                summary['start_mode'] = mode_match.group(3).strip()
        
        # Source endpoint - enhanced to capture provider type
        if 'Source endpoint' in line and 'is using provider' in line:
            src_match = re.search(r"Source endpoint '([^']+)'", line)
            if src_match:
                summary['source_endpoint'] = src_match.group(1)
            # Extract provider/database type
            provider_match = re.search(r"using provider\s*\(['\"]([^'\"]+)['\"]", line)
            if provider_match:
                summary['source_type'] = provider_match.group(1)
        
        # Target endpoint - enhanced to capture provider type
        if 'Target endpoint' in line and 'is using provider' in line:
            tgt_match = re.search(r"Target endpoint '([^']+)'", line)
            if tgt_match:
                summary['target_endpoint'] = tgt_match.group(1)
            # Extract provider/database type
            provider_match = re.search(r"using provider\s*\(['\"]([^'\"]+)['\"]", line)
            if provider_match:
                summary['target_type'] = provider_match.group(1)
        
        # Log level changes
        if 'log level' in line.lower() and 'changed' in line.lower():
            level_match = re.search(r"'(\w+)'.*changed from '(\w+)' to '(\w+)'", line)
            if level_match:
                summary['log_levels_changed'].append({
                    'component': level_match.group(1),
                    'from': level_match.group(2),
                    'to': level_match.group(3)
                })
        
        # Count errors and warnings - also capture samples with context
        if ']E:' in line:
            summary['error_count'] += 1
            # Capture first 5 errors with more context
            if len(summary['sample_errors']) < 5:
                # Extract the error message (remove timestamp and component prefix)
                error_text = re.sub(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\s+\[\w+\s*\]E:\s*', '', line.strip())
                if error_text:
                    summary['sample_errors'].append({
                        'line_number': line_num + 1,
                        'text': error_text[:300]  # Limit length
                    })
        
        if ']W:' in line:
            summary['warning_count'] += 1
            # Capture first 3 warnings with context
            if len(summary['sample_warnings']) < 3:
                warning_text = re.sub(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\s+\[\w+\s*\]W:\s*', '', line.strip())
                if warning_text:
                    summary['sample_warnings'].append({
                        'line_number': line_num + 1,
                        'text': warning_text[:300]
                    })
        
        # Fatal error
        if 'fatal error' in line.lower() and not summary['fatal_error']:
            summary['fatal_error'] = line.strip()[:200]
        
        # Configuration extraction
        if 'Set Bulk Timeout' in line and 'Min' not in line:
            timeout_match = re.search(r'Set Bulk Timeout to (\d+)', line)
            if timeout_match:
                summary['config']['bulk_timeout_ms'] = int(timeout_match.group(1))
        
        if 'Parallel bulk apply' in line:
            threads_match = re.search(r'Parallel bulk apply \((\d+) threads\)', line)
            if threads_match:
                summary['config']['parallel_apply_threads'] = int(threads_match.group(1))
        
        if 'Going to execute MERGE' in line or 'Merge table statement' in line:
            summary['config']['merge_enabled'] = True
        
        # ODBC driver detection
        if 'ODBC' in line and 'driver' in line.lower():
            driver_match = re.search(r"(?:driver|Driver)[:\s]+([^\n;,]{10,80})", line)
            if driver_match:
                driver_name = driver_match.group(1).strip()
                if driver_name and driver_name not in summary['odbc_drivers']:
                    summary['odbc_drivers'].append(driver_name)
        
        # One-by-one mode detection (performance issue indicator)
        if 'one-by-one' in line.lower() and 'Applying' in line:
            table_match = re.search(r"for table '([^']+)'\.?'([^']+)'", line)
            if table_match:
                table_name = f"{table_match.group(1)}.{table_match.group(2)}"
                if table_name not in summary['one_by_one_tables']:
                    summary['one_by_one_tables'].append(table_name)
        
        # Connection events (reconnects, disconnects)
        if any(x in line.lower() for x in ['reconnect', 'disconnect', 'connection lost', 'connection closed']):
            if 'SOURCE' in line or 'TARGET' in line:
                component = 'source' if 'SOURCE' in line else 'target'
                event_type = 'reconnect' if 'reconnect' in line.lower() else 'disconnect'
                summary['connection_events'].append({
                    'line_number': line_num + 1,
                    'component': component,
                    'type': event_type,
                    'text': line.strip()[:200]
                })
        
        # Bulk operations
        if 'Bulk finished' in line:
            summary['bulk_operations'] += 1
        
        # Tables - extract from multiple sources
        if 'get_capture_table_list' in line or ('TABLE_NAME' in line and 'TABLE_SCHEMA' in line):
            # Try to extract table names
            table_matches = re.findall(r"TABLE_NAME='([^']+)'", line)
            for t in table_matches:
                if t not in summary['tables']:
                    summary['tables'].append(t)
        
        # Also extract from "Start applying" messages
        if 'Start applying' in line or 'Finished applying' in line:
            table_match = re.search(r"for table '([^']+)'\.?'([^']+)'", line)
            if table_match:
                table_name = f"{table_match.group(1)}.{table_match.group(2)}"
                if table_name not in summary['tables']:
                    summary['tables'].append(table_name)
        
        # Key events - expanded for better context
        if 'Full load completed' in line or 'Full Load completed' in line:
            summary['full_load_completed'] = True
            summary['key_events'].append({
                'line': line_num + 1,
                'event': 'Full Load Completed',
                'timestamp': ts_match.group(1) if ts_match else None
            })
        
        if 'Starting replication now' in line or 'Change Data Capture' in line and 'started' in line.lower():
            summary['cdc_started'] = True
            summary['key_events'].append({
                'line': line_num + 1,
                'event': 'CDC Started',
                'timestamp': ts_match.group(1) if ts_match else None
            })
        
        if 'Transaction consistency reached' in line:
            summary['key_events'].append({
                'line': line_num + 1,
                'event': 'Transaction Consistency Reached',
                'timestamp': ts_match.group(1) if ts_match else None
            })
        
        if 'Task initialization completed' in line:
            summary['key_events'].append({
                'line': line_num + 1,
                'event': 'Task Initialization Completed',
                'timestamp': ts_match.group(1) if ts_match else None
            })
        
        # Additional key events
        if 'Stop reason' in line and ']I:' in line:
            reason_match = re.search(r'Stop reason: (.+?)(?:\s+\(|$)', line)
            if reason_match:
                summary['key_events'].append({
                    'line': line_num + 1,
                    'event': f"Task Stopped: {reason_match.group(1).strip()}",
                    'timestamp': ts_match.group(1) if ts_match else None
                })
        
        if 'Task is stopped' in line or 'Task stopped' in line:
            summary['key_events'].append({
                'line': line_num + 1,
                'event': 'Task Stopped',
                'timestamp': ts_match.group(1) if ts_match else None
            })
    
    summary['tables_count'] = len(summary['tables'])
    summary['start_time'] = first_timestamp.isoformat() if first_timestamp else None
    summary['end_time'] = last_timestamp.isoformat() if last_timestamp else None
    
    if first_timestamp and last_timestamp:
        duration = last_timestamp - first_timestamp
        summary['duration'] = str(duration)
    
    # Check for proper log closure - look in last 20 lines
    for line in reversed(all_lines[-20:]):
        if 'Closing log file' in line:
            summary['log_properly_closed'] = True
            break
    
    # Generate warning if log appears incomplete
    if not summary['log_properly_closed']:
        summary['incomplete_log_warning'] = 'Log file may be incomplete or the process was aborted abnormally. No "Closing log file" message found at the end.'
    
    # Oracle trace: only surface high-level flags for the summary view.
    # Full per-session / per-read detail is in the Performance Cockpit.
    from backend.core.analysis import summarize_oracle_redo_log_sessions, analyze_oracle_redo_read_variance
    oracle_rows = db.query(LogOracleRedoRead).filter(LogOracleRedoRead.file_id == file_id).all()
    oracle_reads = [
        {
            "timestamp": r.timestamp,
            "line_number": r.line_number,
            "thread_id": r.thread_id,
            "bytes_read": r.bytes_read,
            "read_ms": r.read_ms,
            "source_location": r.source_location,
        }
        for r in oracle_rows
    ]
    full_read_analysis = analyze_oracle_redo_read_variance(oracle_reads)
    summary["oracle_redo_read_analysis"] = {
        "has_red_flags": full_read_analysis.get("has_red_flags", False),
        "total_events_over_floor": full_read_analysis.get("total_events_over_floor", 0),
        "high_variance_group_count": len(full_read_analysis.get("high_variance_groups", [])),
    }

    session_rows = db.query(LogOracleRedoLogSession).filter(LogOracleRedoLogSession.file_id == file_id).all()
    oracle_sessions = [
        {
            "thread_id": s.thread_id,
            "redo_path": s.redo_path,
            "line_open": s.line_open,
            "line_close": s.line_close,
            "timestamp_open": s.timestamp_open,
            "timestamp_close": s.timestamp_close,
            "duration_seconds": s.duration_seconds,
        }
        for s in session_rows
    ]
    full_session_analysis = summarize_oracle_redo_log_sessions(oracle_sessions)
    summary["oracle_redo_log_processing"] = {
        "session_count": full_session_analysis.get("session_count", 0),
        "duration_seconds_stats": full_session_analysis.get("duration_seconds_stats"),
    }
    
    return summary


@router.get("/files/{file_id}/performance-cockpit")
def get_performance_cockpit(file_id: int, db: Session = Depends(get_db)):
    """
    Get comprehensive performance analysis including:
    - Latency breakdown with bottleneck identification
    - Spike and plateau detection
    - Batch behavior analysis
    - Pain tables ranking
    - File operations summary
    - Actionable recommendations
    """
    import re
    import json
    from datetime import datetime
    from collections import defaultdict
    from backend.core.analysis import PerformanceCockpit, LatencyAnalyzer
    from backend.core.patterns import (
        classify_batch_closure_reason, extract_table_name, extract_timestamp,
        BATCH_START_RE, BATCH_END_RE, APPLY_SEQ_RANGE_RE, FINISHED_APPLYING_RE,
        MERGE_STATEMENT_RE, FILE_UPLOAD_SUCCESS_RE, CSV_FILE_NAME_RE,
        FILE_COMPRESS_START_RE, BULK_TIMEOUT_RE, BULK_TIMEOUT_MIN_RE,
        BULK_MAX_FILE_SIZE_RE, PARALLEL_APPLY_RE, SOURCE_ENDPOINT_RE,
        TARGET_ENDPOINT_RE, NO_PK_RE, START_APPLYING_RE,
        SORTER_MEMORY_WARNING_RE, TARGET_DISCONNECT_EVENT_RE,
        SOURCE_RECONNECT_RE, NETWORK_ERROR_RE, RESOURCE_LIMIT_RE,
        parse_oracle_archived_redo_read, parse_oracle_redo_log_open, parse_oracle_redo_log_close,
        LINE_FULL_RE,
    )
    
    f = db.query(LogFile).filter(LogFile.id == file_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    
    if not os.path.exists(f.file_path):
        raise HTTPException(status_code=404, detail="File not found at path")
    
    try:
        # Get performance data from database
        perfs = db.query(LogPerformance).filter(LogPerformance.file_id == file_id).order_by(LogPerformance.timestamp).all()
        performance_data = [
            {
                "timestamp": p.timestamp,
                "line_number": p.line_number,
                "source_latency": p.source_latency,
                "target_latency": p.target_latency,
                "handling_latency": p.handling_latency
            }
            for p in perfs
        ]
        
        # Get errors from database
        errors = db.query(LogError).filter(LogError.file_id == file_id).all()
        error_data = [
            {
                "line_number": e.line_number,
                "timestamp": e.timestamp,
                "component": e.component,
                "text": e.text
            }
            for e in errors
        ]
        
        # Parse log file for additional metrics
        batches = []
        table_stats = defaultdict(lambda: {
            "total_inserts": 0, "total_updates": 0, "total_deletes": 0,
            "total_merges": 0, "total_apply_time_seconds": 0,
            "apply_count": 0, "max_apply_time_seconds": 0,
            "one_by_one_count": 0, "has_pk": None, "error_count": 0
        })
        file_operations = []
        config = {}
        
        # Batch tracking state
        current_batch = None
        batch_start_time = None
        batch_changes = 0
        batch_applies = 0
        batch_tables = set()
        batch_closure_reason = None
        
        # File operation tracking
        file_op_tracking = {}
        current_file_tables = set()
        
        # Apply timing tracking
        apply_start_times = {}  # table -> start_time
        
        # Sorter/CDC Pipeline event tracking
        sorter_events = []
        source_events = []
        oracle_redo_reads = []
        pending_redo_log_opens = {}
        oracle_redo_log_sessions = []
        
        with open(f.file_path, "r", encoding="utf-8", errors="replace") as file:
            for line_num, line in enumerate(file):
                if line_num > 500000:  # Limit for performance
                    break
                
                timestamp = extract_timestamp(line)
                
                parsed_redo = parse_oracle_archived_redo_read(line)
                if parsed_redo and parsed_redo["read_ms"] > 200.0:
                    tm = re.match(r"^\s*(\d+):", line)
                    redo_thread = tm.group(1) if tm else None
                    oracle_redo_reads.append({
                        "line_number": line_num,
                        "timestamp": timestamp,
                        "thread_id": redo_thread,
                        "bytes_read": parsed_redo["bytes_read"],
                        "read_ms": parsed_redo["read_ms"],
                        "source_location": parsed_redo.get("source_location"),
                    })
                
                line_m = LINE_FULL_RE.match(line)
                cap_thread = line_m.group(1) if line_m else None
                if "SOURCE_CAPTURE" in line:
                    o = parse_oracle_redo_log_open(line)
                    if o and timestamp:
                        tid = o.get("thread_id_in_message") or cap_thread or None
                        pending_redo_log_opens[o["redo_path"]] = {
                            "line_number": line_num,
                            "timestamp": timestamp,
                            "thread_id": tid,
                        }
                    cpath = parse_oracle_redo_log_close(line)
                    if cpath and timestamp:
                        if cpath in pending_redo_log_opens:
                            open_info = pending_redo_log_opens.pop(cpath)
                            t0, t1 = open_info["timestamp"], timestamp
                            tid = open_info.get("thread_id") or cap_thread
                            if t0 and t1:
                                dur = (t1 - t0).total_seconds()
                                if dur >= 0:
                                    oracle_redo_log_sessions.append({
                                        "thread_id": str(tid) if tid not in (None, "") else None,
                                        "redo_path": cpath,
                                        "line_open": open_info["line_number"],
                                        "line_close": line_num,
                                        "timestamp_open": t0,
                                        "timestamp_close": t1,
                                        "duration_seconds": dur,
                                    })
                
                # === CONFIG EXTRACTION ===
                if 'Set Bulk Timeout' in line and 'Min' not in line:
                    match = BULK_TIMEOUT_RE.search(line)
                    if match:
                        config['bulk_timeout_ms'] = int(match.group(1))
                
                if 'Set Bulk Timeout Min' in line:
                    match = BULK_TIMEOUT_MIN_RE.search(line)
                    if match:
                        config['bulk_timeout_min_ms'] = int(match.group(1))
                
                if 'Bulk max file size' in line:
                    match = BULK_MAX_FILE_SIZE_RE.search(line)
                    if match:
                        config['bulk_max_file_size_kb'] = int(match.group(2))
                
                if 'Parallel bulk apply' in line:
                    match = PARALLEL_APPLY_RE.search(line)
                    if match:
                        config['parallel_apply_threads'] = int(match.group(1))
                
                if 'Source endpoint' in line and 'provider' in line:
                    match = SOURCE_ENDPOINT_RE.search(line)
                    if match:
                        config['source_type'] = match.group(1)
                
                if 'Target endpoint' in line and 'provider' in line:
                    match = TARGET_ENDPOINT_RE.search(line)
                    if match:
                        config['target_type'] = match.group(1)
                
                # === MERGE MODE DETECTION ===
                if 'Going to execute MERGE' in line or 'Merge table statement MERGE' in line:
                    config['merge_enabled'] = True
                    config['apply_mode'] = 'merge'
                
                # === BATCH TRACKING ===
                if 'TARGET_APPLY' in line:
                    # Batch start
                    if BATCH_START_RE.search(line):
                        batch_start_time = timestamp
                        batch_changes = 0
                        batch_applies = 0
                        batch_tables = set()
                        batch_closure_reason = None
                    
                    # Track closure reasons
                    if 'Finish Bulk' in line or 'Finish bulk' in line:
                        batch_closure_reason = classify_batch_closure_reason(line)
                    
                    # PK conflict patterns
                    if 'same bulk' in line and ('same PK' in line or 'changes PK' in line):
                        batch_closure_reason = classify_batch_closure_reason(line)
                    
                    # Apply sequence (count changes)
                    seq_match = APPLY_SEQ_RANGE_RE.search(line)
                    if seq_match:
                        from_seq = int(seq_match.group(2))
                        to_seq = int(seq_match.group(3))
                        batch_changes += to_seq - from_seq + 1
                        batch_applies += 1
                    
                    # Start applying for table (track timing)
                    start_match = START_APPLYING_RE.search(line)
                    if start_match and timestamp:
                        table_name = f"{start_match.group(3)}.{start_match.group(4)}"
                        apply_start_times[table_name] = timestamp
                        batch_tables.add(table_name)
                        
                        op_type = start_match.group(1)
                        if op_type == 'UNKNOWN':
                            table_stats[table_name]["total_merges"] += int(start_match.group(2))
                        elif op_type == 'INSERT':
                            table_stats[table_name]["total_inserts"] += int(start_match.group(2))
                        elif op_type == 'UPDATE':
                            table_stats[table_name]["total_updates"] += int(start_match.group(2))
                        elif op_type == 'DELETE':
                            table_stats[table_name]["total_deletes"] += int(start_match.group(2))
                    
                    # Finished applying (calculate duration)
                    finish_match = FINISHED_APPLYING_RE.search(line)
                    if finish_match and timestamp:
                        table_name = f"{finish_match.group(3)}.{finish_match.group(4)}"
                        if table_name in apply_start_times:
                            duration = (timestamp - apply_start_times[table_name]).total_seconds()
                            table_stats[table_name]["total_apply_time_seconds"] += duration
                            table_stats[table_name]["apply_count"] += 1
                            if duration > table_stats[table_name]["max_apply_time_seconds"]:
                                table_stats[table_name]["max_apply_time_seconds"] = duration
                            del apply_start_times[table_name]
                    
                    # Batch end
                    if 'Bulk finished.' in line:
                        if batch_start_time and timestamp:
                            duration = (timestamp - batch_start_time).total_seconds()
                            batches.append({
                                "line_number": line_num,
                                "start_timestamp": batch_start_time,
                                "end_timestamp": timestamp,
                                "duration_seconds": duration,
                                "closure_reason": batch_closure_reason or "Normal",
                                "changes_count": batch_changes,
                                "applies_count": batch_applies,
                                "tables": list(batch_tables)
                            })
                        batch_start_time = None
                    
                    # One-by-one detection
                    if 'one-by-one' in line.lower() and 'Applying' in line:
                        table_name = extract_table_name(line)
                        if table_name:
                            table_stats[table_name]["one_by_one_count"] += 1
                    
                    # No PK detection
                    if NO_PK_RE.search(line):
                        table_name = extract_table_name(line)
                        if table_name:
                            table_stats[table_name]["has_pk"] = False
                    
                    # === FILE OPERATIONS ===
                    # Compression start
                    if 'going to compress file' in line.lower():
                        file_match = CSV_FILE_NAME_RE.search(line)
                        if file_match and timestamp:
                            file_name = file_match.group(1)
                            file_op_tracking[file_name] = {
                                'compress_start': timestamp,
                                'tables': list(current_file_tables)
                            }
                    
                    # Upload success
                    upload_match = FILE_UPLOAD_SUCCESS_RE.search(line)
                    if upload_match and timestamp:
                        file_path = upload_match.group(1)
                        file_size = int(upload_match.group(2))
                        file_match = CSV_FILE_NAME_RE.search(file_path)
                        
                        if file_match:
                            file_name = file_match.group(1)
                            if file_name in file_op_tracking:
                                start = file_op_tracking[file_name]['compress_start']
                                total_time = (timestamp - start).total_seconds()
                                throughput = (file_size / 1024) / total_time if total_time > 0 else 0
                                
                                file_operations.append({
                                    "line_number": line_num,
                                    "timestamp": timestamp,
                                    "file_name": file_name,
                                    "file_size_bytes": file_size,
                                    "total_time_seconds": total_time,
                                    "throughput_kbps": throughput,
                                    "tables": file_op_tracking[file_name].get('tables', [])
                                })
                                del file_op_tracking[file_name]
                    
                    # Track tables for file operations
                    if 'bulk_map:' in line:
                        table_name = extract_table_name(line)
                        if table_name:
                            current_file_tables.add(table_name)
                
                # === SORTER/CDC PIPELINE EVENTS ===
                if 'SORTER' in line:
                    # Memory warnings
                    if SORTER_MEMORY_WARNING_RE.search(line):
                        sorter_events.append({
                            'event_type': 'memory_warning',
                            'line_number': line_num,
                            'timestamp': timestamp,
                            'text': line[:200]
                        })
                    # Overflow events
                    if 'overflow' in line.lower() or 'buffer full' in line.lower():
                        sorter_events.append({
                            'event_type': 'overflow',
                            'line_number': line_num,
                            'timestamp': timestamp,
                            'text': line[:200]
                        })
                
                # Target disconnection events
                if TARGET_DISCONNECT_EVENT_RE.search(line):
                    sorter_events.append({
                        'event_type': 'target_disconnect',
                        'line_number': line_num,
                        'timestamp': timestamp,
                        'text': line[:200]
                    })
                
                # === SOURCE EVENTS ===
                if 'SOURCE_CAPTURE' in line or 'SOURCE_UNLOAD' in line:
                    # Reconnection events
                    if SOURCE_RECONNECT_RE.search(line):
                        source_events.append({
                            'event_type': 'reconnect',
                            'line_number': line_num,
                            'timestamp': timestamp,
                            'text': line[:200]
                        })
                    # Network errors
                    if NETWORK_ERROR_RE.search(line):
                        source_events.append({
                            'event_type': 'network_error',
                            'line_number': line_num,
                            'timestamp': timestamp,
                            'text': line[:200]
                        })
                    # Resource limits
                    if RESOURCE_LIMIT_RE.search(line):
                        source_events.append({
                            'event_type': 'resource_limit',
                            'line_number': line_num,
                            'timestamp': timestamp,
                            'text': line[:200]
                        })
        
        # Calculate average apply times
        for table_name, stats in table_stats.items():
            if stats["apply_count"] > 0:
                stats["avg_apply_time_seconds"] = stats["total_apply_time_seconds"] / stats["apply_count"]
        
        # Convert table_stats to list format
        table_stats_list = [
            {"table_name": name, **stats}
            for name, stats in table_stats.items()
        ]
        
        # Auto-detect merge_enabled based on table stats if not already set
        if 'merge_enabled' not in config:
            total_merges = sum(stats.get('total_merges', 0) for stats in table_stats_list)
            if total_merges > 0:
                config['merge_enabled'] = True
                config['apply_mode'] = 'merge'
        
        # Generate cockpit summary
        cockpit = PerformanceCockpit(
            performance_data=performance_data,
            batches=batches,
            table_stats=table_stats_list,
            file_operations=file_operations,
            errors=error_data,
            config=config,
            sorter_events=sorter_events,
            source_events=source_events,
            oracle_redo_reads=oracle_redo_reads,
            oracle_redo_log_sessions=oracle_redo_log_sessions,
        )
        
        return cockpit.generate_summary()
    
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"Failed to generate performance cockpit: {str(e)}\n{traceback.format_exc()}")


# ============== User Settings Endpoints ==============

class SettingsRequest(BaseModel):
    key: str
    value: dict  # JSON object

@router.get("/settings/{key}")
async def get_setting(key: str, db: Session = Depends(get_db)):
    """Get a user setting by key."""
    import json
    setting = db.query(UserSettings).filter(UserSettings.key == key).first()
    if not setting:
        return {"key": key, "value": None}
    try:
        return {"key": key, "value": json.loads(setting.value)}
    except:
        return {"key": key, "value": setting.value}

@router.post("/settings")
async def save_setting(request: SettingsRequest, db: Session = Depends(get_db)):
    """Save a user setting."""
    import json
    
    existing = db.query(UserSettings).filter(UserSettings.key == request.key).first()
    value_str = json.dumps(request.value)
    
    if existing:
        existing.value = value_str
        existing.updated_at = datetime.utcnow()
    else:
        new_setting = UserSettings(key=request.key, value=value_str)
        db.add(new_setting)
    
    db.commit()
    return {"status": "ok", "key": request.key}

@router.get("/settings")
async def get_all_settings(db: Session = Depends(get_db)):
    """Get all user settings."""
    import json
    settings = db.query(UserSettings).all()
    result = {}
    for s in settings:
        try:
            result[s.key] = json.loads(s.value)
        except:
            result[s.key] = s.value
    return result
