from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "log_analyzer.db")
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

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


