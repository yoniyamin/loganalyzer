"""
Database client for KB article tracking.
Uses the main log_analyzer SQLite database.
"""
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DATABASE_URL

# Create engine for kb-assistant use
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class KBArticle(Base):
    """Track indexed KB articles from Qlik Community and custom markdown files."""
    __tablename__ = "kb_articles"
    
    id = Column(Integer, primary_key=True)
    url = Column(String, unique=True, index=True)
    article_id = Column(String, nullable=True, index=True)
    title = Column(String)
    source = Column(String, default="kb_article")
    content_hash = Column(String, index=True)
    content_length = Column(Integer, default=0)
    chunks_count = Column(Integer, default=0)
    indexed_at = Column(DateTime, default=datetime.utcnow)
    last_modified = Column(DateTime, nullable=True)
    status = Column(String, default="indexed")


def init_kb_tables():
    """Create KB tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


def get_session():
    """Get a database session."""
    return SessionLocal()


def get_indexed_urls() -> set:
    """Get set of already indexed article URLs."""
    session = get_session()
    try:
        articles = session.query(KBArticle.url).filter(
            KBArticle.status == "indexed"
        ).all()
        return {a.url for a in articles}
    finally:
        session.close()


def get_article_by_url(url: str) -> Optional[KBArticle]:
    """Get an article by URL."""
    session = get_session()
    try:
        return session.query(KBArticle).filter(KBArticle.url == url).first()
    finally:
        session.close()


def add_or_update_article(
    url: str,
    title: str,
    source: str = "kb_article",
    article_id: Optional[str] = None,
    content_hash: Optional[str] = None,
    content_length: int = 0,
    chunks_count: int = 0,
    last_modified: Optional[datetime] = None,
    status: str = "indexed"
) -> KBArticle:
    """
    Add a new article or update existing one.
    
    Returns:
        The created or updated KBArticle
    """
    session = get_session()
    try:
        existing = session.query(KBArticle).filter(KBArticle.url == url).first()
        
        if existing:
            existing.title = title
            existing.source = source
            existing.article_id = article_id
            existing.content_hash = content_hash
            existing.content_length = content_length
            existing.chunks_count = chunks_count
            existing.indexed_at = datetime.utcnow()
            existing.last_modified = last_modified
            existing.status = status
            session.commit()
            session.refresh(existing)
            return existing
        else:
            article = KBArticle(
                url=url,
                title=title,
                source=source,
                article_id=article_id,
                content_hash=content_hash,
                content_length=content_length,
                chunks_count=chunks_count,
                last_modified=last_modified,
                status=status
            )
            session.add(article)
            session.commit()
            session.refresh(article)
            return article
    finally:
        session.close()


def mark_article_failed(url: str, reason: str = "failed") -> None:
    """Mark an article as failed."""
    session = get_session()
    try:
        article = session.query(KBArticle).filter(KBArticle.url == url).first()
        if article:
            article.status = reason
            session.commit()
    finally:
        session.close()


def get_all_articles(
    source: Optional[str] = None,
    status: Optional[str] = None
) -> List[KBArticle]:
    """Get all articles, optionally filtered by source and status."""
    session = get_session()
    try:
        query = session.query(KBArticle)
        if source:
            query = query.filter(KBArticle.source == source)
        if status:
            query = query.filter(KBArticle.status == status)
        return query.order_by(KBArticle.indexed_at.desc()).all()
    finally:
        session.close()


def get_stats() -> Dict[str, Any]:
    """Get KB article statistics."""
    session = get_session()
    try:
        total = session.query(KBArticle).count()
        indexed = session.query(KBArticle).filter(KBArticle.status == "indexed").count()
        failed = session.query(KBArticle).filter(KBArticle.status == "failed").count()
        kb_articles = session.query(KBArticle).filter(KBArticle.source == "kb_article").count()
        markdown = session.query(KBArticle).filter(KBArticle.source == "markdown").count()
        
        total_chunks = session.query(KBArticle.chunks_count).all()
        chunks_sum = sum(c[0] or 0 for c in total_chunks)
        
        return {
            "total_articles": total,
            "indexed": indexed,
            "failed": failed,
            "kb_articles": kb_articles,
            "markdown_files": markdown,
            "total_chunks": chunks_sum
        }
    finally:
        session.close()


def delete_article(url: str) -> bool:
    """Delete an article by URL."""
    session = get_session()
    try:
        article = session.query(KBArticle).filter(KBArticle.url == url).first()
        if article:
            session.delete(article)
            session.commit()
            return True
        return False
    finally:
        session.close()


def clear_all_articles() -> int:
    """Delete all articles. Returns count of deleted articles."""
    session = get_session()
    try:
        count = session.query(KBArticle).count()
        session.query(KBArticle).delete()
        session.commit()
        return count
    finally:
        session.close()
