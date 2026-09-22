"""Shared fixtures for the log_analyzer test suite.

Provides:
- Isolated temporary SQLite database (no production DB contamination)
- Sample log file generation
- FastAPI TestClient wired to the temp DB
"""
import os
import sys
import tempfile
import shutil
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event as sa_event, text as sa_text
from sqlalchemy.orm import sessionmaker

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import Base, LogFile, LogError, LogBatch, LogLineMeta, FileVersion


@pytest.fixture()
def tmp_db(tmp_path):
    """Create an isolated SQLite database with all tables + FTS5."""
    db_file = tmp_path / "test.db"
    url = f"sqlite:///{db_file}"
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @sa_event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        conn.execute(sa_text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS log_lines_fts USING fts5(
                body,
                file_id UNINDEXED,
                line_number UNINDEXED,
                tokenize='unicode61'
            )
        """))
        conn.commit()

    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def sample_log_file(tmp_path):
    """Generate a realistic sample log file with errors, batches, config lines."""
    log_path = tmp_path / "sample_reptask.log"
    base_ts = datetime(2025, 6, 15, 10, 0, 0)
    lines = []

    def ts(offset_seconds):
        return (base_ts + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%dT%H:%M:%S")

    # Config lines (must match patterns.py regexes exactly)
    # Format: ThreadID: Timestamp [Component]Severity: Message (no word between timestamp and bracket)
    lines.append(f"00001234: {ts(0)} [SOURCE_CAPTURE  ]I:  Source endpoint 'Oracle' is using provider\n")
    lines.append(f"00001234: {ts(1)} [TARGET_APPLY    ]I:  Target endpoint 'Microsoft SQL Server' is using provider\n")
    lines.append(f"00001234: {ts(2)} [TARGET_APPLY    ]I:  Set Bulk Timeout = 30000 milliseconds\n")
    lines.append(f"00001234: {ts(3)} [TARGET_APPLY    ]I:  Set Bulk Timeout Min = 5000 milliseconds\n")
    lines.append(f"00001234: {ts(4)} [TARGET_APPLY    ]I:  Bulk max file size: 32 MB, 32768 KB\n")
    lines.append(f"00001234: {ts(5)} [TARGET_APPLY    ]I:  Parallel bulk apply enabled with maximum 4 apply threads\n")

    # Normal operation
    for i in range(10):
        lines.append(f"00001234: {ts(10 + i)} [SORTER          ]I:  Transaction 10{i:02d} committed\n")

    # Batch cycle (must match BATCH_START_RE, APPLY_SEQ_RANGE_RE, START/FINISHED_APPLYING_RE)
    lines.append(f"00001234: {ts(30)} [TARGET_APPLY    ]T:  Going to start applying bulk changes\n")
    lines.append(f"00001234: {ts(31)} [TARGET_APPLY    ]T:  Start applying 'INSERT (5)' changes for table 'dbo'.'orders'\n")
    lines.append(f"00001234: {ts(32)} [TARGET_APPLY    ]T:  Going to run INSERT statement for table 'dbo'.'orders' from seq 1 to seq 5\n")
    lines.append(f"00001234: {ts(33)} [TARGET_APPLY    ]T:  Finished applying of 5 'INSERT (5)' events for table 'dbo'.'orders'\n")
    lines.append(f"00001234: {ts(35)} [TARGET_APPLY    ]T:  Bulk finished.\n")

    # Warning line (indexed via LogLineMeta severity=W and LogError)
    lines.append(f"00001234: {ts(38)} [SORTER          ]W:  Memory consumption approaching configured limit\n")

    # Error lines (same component for co-occurrence)
    lines.append(f"00001234: {ts(40)} [TARGET_APPLY    ]E:  Failed to execute statement. SqlState: HY000 NativeError: 1205 Message: Lock wait timeout exceeded\n")
    lines.append(f"00001234: {ts(41)} [TARGET_APPLY    ]E:  RetCode: SQL_ERROR  SqlState: HY000 NativeError: 1205\n")
    lines.append(f"  Continuation: Lock wait timeout on table 'dbo'.'orders'\n")
    lines.append(f"00001234: {ts(43)} [TARGET_APPLY    ]E:  ORA-00054: resource busy and acquire with NOWAIT specified\n")

    # Another error on different component
    lines.append(f"00005678: {ts(50)} [SOURCE_CAPTURE  ]E:  Failed to read redo log. ORA-00054: resource busy\n")

    # Performance line
    lines.append(f"00001234: {ts(60)} [PERFORMANCE     ]I:  Source latency 1.234 seconds, Target latency 0.456 seconds, Handling latency 0.789 seconds\n")

    # More normal lines for FTS variety
    for i in range(20):
        lines.append(f"00001234: {ts(70 + i)} [SORTER          ]I:  Processing change {i} for table 'dbo'.'customers'\n")

    log_path.write_text("".join(lines), encoding="utf-8")
    return log_path


@pytest.fixture()
def indexed_file(tmp_db, sample_log_file):
    """Register a log file in the DB and run the indexer on it.

    Returns (db_session, file_id, log_path).
    """
    db = tmp_db

    log_file = LogFile(
        filename=sample_log_file.name,
        file_path=str(sample_log_file),
        status="indexing",
    )
    db.add(log_file)
    db.commit()
    db.refresh(log_file)

    from backend.core.indexer import process_log_file
    process_log_file(db, log_file.id)

    return db, log_file.id, sample_log_file


@pytest.fixture()
def sparse_indexed_file(tmp_db, tmp_path):
    """Minimal log: informational lines only — triggers preflight needs_focus."""
    log_path = tmp_path / "sparse.log"
    base_ts = datetime(2025, 6, 15, 12, 0, 0)

    def ts(offset_seconds):
        return (base_ts + timedelta(seconds=offset_seconds)).strftime("%Y-%m-%dT%H:%M:%S")

    lines = [
        f"00001234: {ts(0)} [TASK_MANAGER    ]I:  Task started\n",
        f"00001234: {ts(1)} [SORTER          ]I:  Sorter initialized\n",
        f"00001234: {ts(2)} [COMMUNICATION   ]I:  Connected to source\n",
    ]
    log_path.write_text("".join(lines), encoding="utf-8")

    db = tmp_db
    log_file = LogFile(
        filename=log_path.name,
        file_path=str(log_path),
        status="indexing",
    )
    db.add(log_file)
    db.commit()
    db.refresh(log_file)

    from backend.core.indexer import process_log_file
    process_log_file(db, log_file.id)
    return db, log_file.id, log_path


@pytest.fixture()
def test_client(tmp_db, sample_log_file):
    """FastAPI TestClient wired to use the temp database session."""
    from fastapi.testclient import TestClient
    from backend.api.endpoints import router, get_db
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)

    def _override_db():
        try:
            yield tmp_db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_db

    log_file = LogFile(
        filename=sample_log_file.name,
        file_path=str(sample_log_file),
        status="indexing",
    )
    tmp_db.add(log_file)
    tmp_db.commit()
    tmp_db.refresh(log_file)

    from backend.core.indexer import process_log_file
    process_log_file(tmp_db, log_file.id)

    client = TestClient(app)
    client.file_id = log_file.id
    return client
