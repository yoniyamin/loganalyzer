from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import shutil
import os
import uuid
from datetime import datetime

from backend.database import get_db, LogFile, LogStats, LogPerformance, LogError, LogIndex
from backend.core.indexer import process_log_file
from backend.core.reader import LogReader

router = APIRouter()

UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

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
    return db.query(LogFile).order_by(LogFile.upload_time.desc()).limit(10).all()

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
    db: Session = Depends(get_db)
):
    try:
        reader = LogReader(db, file_id)
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

@router.post("/files/{file_id}/reindex")
async def reindex_file(
    file_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Re-index an existing log file."""
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
    db.query(LogStats).filter(LogStats.file_id == file_id).delete()
    db.query(LogError).filter(LogError.file_id == file_id).delete()
    db.commit()
    
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
    
    return {"id": file_id, "filename": log_file.filename, "status": "indexing", "message": "Re-indexing started"}


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
                message_summary = msg_match.group(1).strip()[:80]  # First 80 chars
            else:
                message_summary = line_stripped[:80]
            
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
        'start_time': None,
        'end_time': None,
        'duration': None,
        'running_mode': None,
        'start_mode': None,
        'source_endpoint': None,
        'target_endpoint': None,
        'tables_count': 0,
        'tables': [],
        'log_levels_changed': [],
        'error_count': 0,
        'warning_count': 0,
        'fatal_error': None,
        'bulk_operations': 0,
        'cdc_events_count': 0,
        'full_load_completed': False,
        'cdc_started': False,
        'key_events': [],
        'log_properly_closed': False,  # Indicates if "Closing log file" was found
        'incomplete_log_warning': None  # Warning message if log appears incomplete
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
        
        # Task Server Log line
        if 'Task Server Log -' in line:
            task_match = re.search(r'Task Server Log - (\S+)\s+\(V([\d.]+)\s+(\S+)', line)
            if task_match:
                summary['task_name'] = task_match.group(1)
                summary['version'] = task_match.group(2)
                summary['server'] = task_match.group(3)
        
        # Running mode
        if "Task '" in line and "running" in line:
            mode_match = re.search(r"Task '([^']+)' running (.+?) in (.+?) mode", line)
            if mode_match:
                summary['task_name'] = mode_match.group(1)
                summary['running_mode'] = mode_match.group(2).strip()
                summary['start_mode'] = mode_match.group(3).strip()
        
        # Source endpoint
        if 'Source endpoint' in line and 'is using provider' in line:
            src_match = re.search(r"Source endpoint '([^']+)'", line)
            if src_match:
                summary['source_endpoint'] = src_match.group(1)
        
        # Target endpoint
        if 'Target endpoint' in line and 'is using provider' in line:
            tgt_match = re.search(r"Target endpoint '([^']+)'", line)
            if tgt_match:
                summary['target_endpoint'] = tgt_match.group(1)
        
        # Log level changes
        if 'log level' in line.lower() and 'changed' in line.lower():
            level_match = re.search(r"'(\w+)'.*changed from '(\w+)' to '(\w+)'", line)
            if level_match:
                summary['log_levels_changed'].append({
                    'component': level_match.group(1),
                    'from': level_match.group(2),
                    'to': level_match.group(3)
                })
        
        # Count errors and warnings
        if ']E:' in line:
            summary['error_count'] += 1
        if ']W:' in line:
            summary['warning_count'] += 1
        
        # Fatal error
        if 'fatal error' in line.lower() and not summary['fatal_error']:
            summary['fatal_error'] = line.strip()[:200]
        
        # Bulk operations
        if 'Bulk finished' in line:
            summary['bulk_operations'] += 1
        
        # Tables
        if 'get_capture_table_list' in line or ('TABLE_NAME' in line and 'TABLE_SCHEMA' in line):
            # Try to extract table names
            table_matches = re.findall(r"TABLE_NAME='([^']+)'", line)
            for t in table_matches:
                if t not in summary['tables']:
                    summary['tables'].append(t)
        
        # Key events
        if 'Full load completed' in line or 'Full Load completed' in line:
            summary['full_load_completed'] = True
            summary['key_events'].append({'line': line_num, 'event': 'Full Load Completed'})
        
        if 'Starting replication now' in line:
            summary['cdc_started'] = True
            summary['key_events'].append({'line': line_num, 'event': 'CDC Started'})
        
        if 'Transaction consistency reached' in line:
            summary['key_events'].append({'line': line_num, 'event': 'Transaction Consistency Reached'})
        
        if 'Task initialization completed' in line:
            summary['key_events'].append({'line': line_num, 'event': 'Task Initialization Completed'})
    
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
    
    return summary
