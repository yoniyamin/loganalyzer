from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime

from backend.paths import db_path

DB_PATH = db_path()
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class LogFile(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    file_path = Column(String, unique=True)
    upload_time = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="indexing") # indexing, ready, error
    size_bytes = Column(Integer, default=0)
    line_count = Column(Integer, default=0)
    error_message = Column(String, nullable=True)

    indexes = relationship("LogIndex", back_populates="file", cascade="all, delete-orphan")
    performance = relationship("LogPerformance", back_populates="file", cascade="all, delete-orphan")
    oracle_redo_reads = relationship("LogOracleRedoRead", back_populates="file", cascade="all, delete-orphan")
    oracle_redo_log_sessions = relationship("LogOracleRedoLogSession", back_populates="file", cascade="all, delete-orphan")
    stats = relationship("LogStats", back_populates="file", cascade="all, delete-orphan")
    errors = relationship("LogError", back_populates="file", cascade="all, delete-orphan")

class LogIndex(Base):
    __tablename__ = "log_index"

    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id"))
    line_number = Column(Integer)
    byte_offset = Column(Integer)
    timestamp = Column(DateTime, nullable=True, index=True)

    file = relationship("LogFile", back_populates="indexes")

class LogPerformance(Base):
    __tablename__ = "performance"

    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id"))
    line_number = Column(Integer, index=True)  # Store the line number for direct navigation
    timestamp = Column(DateTime, index=True)
    source_latency = Column(Float)
    target_latency = Column(Float)
    handling_latency = Column(Float)

    file = relationship("LogFile", back_populates="performance")


class LogOracleRedoRead(Base):
    """
    Oracle archived redo log read completions from [PERFORMANCE] trace (e.g. oradcdc_redo).
    Only persisted when read time exceeds 200 ms (see analysis thresholds).
    """
    __tablename__ = "oracle_redo_reads"

    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id"))
    line_number = Column(Integer, index=True)
    timestamp = Column(DateTime, nullable=True, index=True)
    thread_id = Column(String, nullable=True)
    bytes_read = Column(Integer, nullable=False)
    read_ms = Column(Float, nullable=False)
    source_location = Column(String, nullable=True)  # e.g. oradcdc_redo.c:1046

    file = relationship("LogFile", back_populates="oracle_redo_reads")


class LogOracleRedoLogSession(Base):
    """
    Time spent processing one archived redo log: paired 'Going to open Redo Log' → 'Close Redo log'
    with the same path (Oracle SOURCE_CAPTURE trace).
    """
    __tablename__ = "oracle_redo_log_sessions"

    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id"))
    thread_id = Column(String, nullable=True)
    redo_path = Column(Text, nullable=False)
    line_open = Column(Integer, index=True)
    line_close = Column(Integer, index=True)
    timestamp_open = Column(DateTime, nullable=True, index=True)
    timestamp_close = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=False)

    file = relationship("LogFile", back_populates="oracle_redo_log_sessions")


class LogStats(Base):
    __tablename__ = "stats"

    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id"))
    component = Column(String)
    thread_id = Column(String)
    message_count = Column(Integer, default=0)
    first_ts = Column(DateTime, nullable=True)
    last_ts = Column(DateTime, nullable=True)

    file = relationship("LogFile", back_populates="stats")

class LogError(Base):
    __tablename__ = "errors"
    
    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id"))
    line_number = Column(Integer)
    timestamp = Column(DateTime, nullable=True)
    component = Column(String, nullable=True)
    thread_id = Column(String, nullable=True)
    text = Column(Text)

    file = relationship("LogFile", back_populates="errors")


class LogBatch(Base):
    """Track batch events with closure reasons, duration, and size."""
    __tablename__ = "batches"
    
    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id"))
    line_number = Column(Integer, index=True)
    start_timestamp = Column(DateTime, nullable=True, index=True)
    end_timestamp = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    closure_reason = Column(String, nullable=True)  # PKi, PKu, PKd, MEM, TIM, TMO, SNG, RES, LOAD, Normal
    changes_count = Column(Integer, default=0)
    applies_count = Column(Integer, default=0)
    tables = Column(Text, nullable=True)  # JSON list of tables in this batch
    
    file = relationship("LogFile", backref="batches")


class LogSorterEvent(Base):
    """Track sorter events: throughput, memory, transactions."""
    __tablename__ = "sorter_events"
    
    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id"))
    line_number = Column(Integer, index=True)
    timestamp = Column(DateTime, nullable=True, index=True)
    event_type = Column(String)  # throughput, memory_warning, transaction, reload, disconnect
    value = Column(Float, nullable=True)  # for numeric values like throughput
    details = Column(Text, nullable=True)  # JSON for additional context
    
    file = relationship("LogFile", backref="sorter_events")


class LogFileOperation(Base):
    """Track file operations (CSV upload, compression) for cloud targets."""
    __tablename__ = "file_operations"
    
    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id"))
    line_number = Column(Integer, index=True)
    timestamp = Column(DateTime, nullable=True, index=True)
    file_name = Column(String)
    file_size_bytes = Column(Integer, nullable=True)
    compress_time_seconds = Column(Float, nullable=True)
    upload_time_seconds = Column(Float, nullable=True)
    total_time_seconds = Column(Float, nullable=True)
    throughput_kbps = Column(Float, nullable=True)
    tables = Column(Text, nullable=True)  # JSON list of tables in this file
    
    file = relationship("LogFile", backref="file_operations")


class LogApplyEvent(Base):
    """Track apply events per table: MERGE vs standard, timing."""
    __tablename__ = "apply_events"
    
    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id"))
    line_number = Column(Integer, index=True)
    timestamp = Column(DateTime, nullable=True, index=True)
    table_name = Column(String, index=True)
    apply_method = Column(String)  # MERGE, INSERT, UPDATE, DELETE, ONE_BY_ONE
    operation_count = Column(Integer, default=0)
    duration_seconds = Column(Float, nullable=True)
    batch_id = Column(Integer, nullable=True)  # Link to batch if applicable
    
    file = relationship("LogFile", backref="apply_events")


class LogTableStats(Base):
    """Aggregated stats per table for performance analysis."""
    __tablename__ = "table_stats"
    
    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id"))
    table_name = Column(String, index=True)
    total_inserts = Column(Integer, default=0)
    total_updates = Column(Integer, default=0)
    total_deletes = Column(Integer, default=0)
    total_merges = Column(Integer, default=0)
    total_apply_time_seconds = Column(Float, default=0.0)
    avg_apply_time_seconds = Column(Float, nullable=True)
    max_apply_time_seconds = Column(Float, nullable=True)
    one_by_one_count = Column(Integer, default=0)
    has_pk = Column(Boolean, nullable=True)  # None=unknown, True/False
    error_count = Column(Integer, default=0)
    
    file = relationship("LogFile", backref="table_stats")


class LogTaskConfig(Base):
    """Store extracted task configuration values."""
    __tablename__ = "task_config"
    
    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id"), unique=True)
    bulk_timeout_ms = Column(Integer, nullable=True)
    bulk_timeout_min_ms = Column(Integer, nullable=True)
    bulk_max_file_size_kb = Column(Integer, nullable=True)
    parallel_apply_threads = Column(Integer, nullable=True)
    stream_buffer_size = Column(Integer, nullable=True)
    stream_buffers_number = Column(Integer, nullable=True)
    stop_on_memory_limit = Column(Boolean, nullable=True)
    target_type = Column(String, nullable=True)  # Databricks, BigQuery, etc.
    source_type = Column(String, nullable=True)
    apply_mode = Column(String, nullable=True)  # bulk, transactional
    merge_enabled = Column(Boolean, nullable=True)
    
    file = relationship("LogFile", backref="task_config")


class UserSettings(Base):
    """Store user settings like color schemes."""
    __tablename__ = "user_settings"
    
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, index=True)  # e.g., 'color_scheme', 'custom_themes'
    value = Column(Text)  # JSON string
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LLMConfig(Base):
    """Store LLM configuration (API keys and preferences)."""
    __tablename__ = "llm_config"
    
    id = Column(Integer, primary_key=True)
    # Provider selection: "gemini" (default) or "openrouter"
    provider = Column(String, default="gemini")
    # Gemini API key (AI Studio)
    gemini_api_key_encrypted = Column(String, nullable=True)
    # OpenRouter API key (legacy field renamed for clarity)
    api_key_encrypted = Column(String, nullable=True)  # OpenRouter key
    # Tavily API key for external search
    tavily_api_key_encrypted = Column(String, nullable=True)
    # Default model (provider-specific)
    default_model = Column(String, default="gemini-2.5-flash")
    # LM Studio local server base URL
    lmstudio_base_url = Column(String, nullable=True)
    # LM Studio generation parameters (overrides client defaults when set)
    lmstudio_temperature = Column(Float, nullable=True)   # default 0.3
    lmstudio_max_tokens = Column(Integer, nullable=True)  # default 1500
    # Web search enabled for report generation
    web_search_enabled = Column(Boolean, default=False)
    # Redact log-derived prompt content before Gemini/OpenRouter (ignored for LM Studio)
    sanitize_log_for_cloud_llm = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LLMReport(Base):
    """Store generated LLM analysis reports."""
    __tablename__ = "llm_reports"
    
    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id"))
    model_used = Column(String)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    report_content = Column(Text)  # Markdown formatted report
    generated_at = Column(DateTime, default=datetime.utcnow)
    
    file = relationship("LogFile", backref="llm_reports")


class KBArticle(Base):
    """Track indexed KB articles from Qlik Community and custom markdown files."""
    __tablename__ = "kb_articles"
    
    id = Column(Integer, primary_key=True)
    url = Column(String, unique=True, index=True)  # URL or file path
    article_id = Column(String, nullable=True, index=True)  # Qlik article ID (e.g., "1714978")
    title = Column(String)
    source = Column(String, default="kb_article")  # "kb_article" or "markdown"
    content_hash = Column(String, index=True)  # For detecting content changes
    content_length = Column(Integer, default=0)
    chunks_count = Column(Integer, default=0)  # Number of chunks in ChromaDB
    indexed_at = Column(DateTime, default=datetime.utcnow)
    last_modified = Column(DateTime, nullable=True)  # From sitemap lastmod
    status = Column(String, default="indexed")  # indexed, failed, outdated


class AIThread(Base):
    """Store AI Q&A threads for the AI Assistant feature."""
    __tablename__ = "ai_threads"
    
    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id"), index=True)
    question = Column(Text)
    answer = Column(Text)
    kb_articles = Column(Text, nullable=True)  # JSON list of KB article references
    model_used = Column(String, nullable=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    thumbs_up = Column(Boolean, default=False)  # User marked as helpful
    saved_to_chromadb = Column(Boolean, default=False)  # Saved for future RAG
    created_at = Column(DateTime, default=datetime.utcnow)
    
    file = relationship("LogFile", backref="ai_threads")


class SavedFinding(Base):
    """Store saved findings from log analysis, including Q/A threads."""
    __tablename__ = "saved_findings"
    
    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id"), index=True)
    finding_type = Column(String, default="log_line")  # "log_line", "qa_thread", "custom"
    title = Column(String, nullable=True)  # Optional title/summary
    content = Column(Text)  # The finding content
    source_thread_id = Column(Integer, nullable=True)  # Reference to AIThread if from Q/A
    line_number = Column(Integer, nullable=True)  # If from log line
    metadata_json = Column(Text, nullable=True)  # JSON for extra metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    file = relationship("LogFile", backref="saved_findings")


class RoutingFeedback(Base):
    """Store user feedback on routing decisions to improve future routing."""
    __tablename__ = "routing_feedback"
    
    id = Column(Integer, primary_key=True)
    thread_id = Column(Integer, ForeignKey("ai_threads.id"), index=True)
    file_id = Column(Integer, ForeignKey("files.id"), index=True)
    question = Column(Text)  # Copy of the question for easier querying
    
    # What the system actually used
    actual_source = Column(String)  # "local", "kb", "ai", "needs_confirmation"
    actual_routing_mode = Column(String, nullable=True)  # "LOCAL", "KB_FUSION", "AI_REQUIRED"
    
    # What the user thinks should have been used (checkboxes)
    should_use_local = Column(Boolean, default=False)
    should_use_kb = Column(Boolean, default=False)
    should_use_ai = Column(Boolean, default=False)
    
    # User's explanation
    comment = Column(Text, nullable=True)
    
    # Rating: was the answer helpful? (1-5 scale or null if not rated)
    quality_rating = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    thread = relationship("AIThread", backref="routing_feedback")
    file = relationship("LogFile", backref="routing_feedback")


def init_db():
    """Initialize the database and run migrations."""
    Base.metadata.create_all(bind=engine)
    
    # Run migrations for LLMConfig table
    _migrate_llm_config()


def _migrate_llm_config():
    """Add new columns to llm_config table if they don't exist."""
    import sqlite3
    
    # Get the database path from the engine
    db_path = str(engine.url).replace('sqlite:///', '')
    if not db_path or db_path == ':memory:':
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if llm_config table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='llm_config'")
        if not cursor.fetchone():
            conn.close()
            return
        
        # Get existing columns
        cursor.execute("PRAGMA table_info(llm_config)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Add missing columns
        if 'provider' not in columns:
            cursor.execute("ALTER TABLE llm_config ADD COLUMN provider TEXT DEFAULT 'gemini'")
            print("Migration: Added 'provider' column to llm_config")
        
        if 'gemini_api_key_encrypted' not in columns:
            cursor.execute("ALTER TABLE llm_config ADD COLUMN gemini_api_key_encrypted TEXT")
            print("Migration: Added 'gemini_api_key_encrypted' column to llm_config")
        
        if 'web_search_enabled' not in columns:
            cursor.execute("ALTER TABLE llm_config ADD COLUMN web_search_enabled INTEGER DEFAULT 0")
            print("Migration: Added 'web_search_enabled' column to llm_config")

        if 'lmstudio_base_url' not in columns:
            cursor.execute("ALTER TABLE llm_config ADD COLUMN lmstudio_base_url TEXT")
            print("Migration: Added 'lmstudio_base_url' column to llm_config")

        if 'lmstudio_temperature' not in columns:
            cursor.execute("ALTER TABLE llm_config ADD COLUMN lmstudio_temperature REAL")
            print("Migration: Added 'lmstudio_temperature' column to llm_config")

        if 'lmstudio_max_tokens' not in columns:
            cursor.execute("ALTER TABLE llm_config ADD COLUMN lmstudio_max_tokens INTEGER")
            print("Migration: Added 'lmstudio_max_tokens' column to llm_config")

        if 'sanitize_log_for_cloud_llm' not in columns:
            cursor.execute("ALTER TABLE llm_config ADD COLUMN sanitize_log_for_cloud_llm INTEGER DEFAULT 1")
            print("Migration: Added 'sanitize_log_for_cloud_llm' column to llm_config")

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Migration warning: {e}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


