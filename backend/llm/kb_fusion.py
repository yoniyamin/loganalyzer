"""
KB Fusion Module - Merge Local Facts with Knowledge Base Articles

This module combines:
1. Local log analysis facts (from SQLite)
2. Relevant KB articles (from ChromaDB)

WITHOUT calling any AI model.

The fusion produces human-readable answers for questions like:
- "What does ORA-00054 mean?" → Local error count + KB explanation
- "Why am I getting lock errors?" → Local analysis + KB troubleshooting guide
"""

import re
import logging
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.database import LogError, LogFile
from backend.llm.vectorstore import get_vector_store
from backend.llm.humanizer import get_humanizer, Humanizer
from backend.llm.local_query_engine import LocalAnswer

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class KBArticle:
    """A knowledge base article."""
    title: str
    content: str
    url: str
    similarity: float


@dataclass
class FusedAnswer:
    """Result from KB fusion."""
    answer: str
    source: str = "kb"  # Always "kb" for fusion answers
    local_facts: Optional[str] = None
    kb_articles: List[Dict[str, Any]] = None
    confidence: str = "medium"
    tokens_used: int = 0  # Always 0 - no AI used


# =============================================================================
# Error Code Extraction
# =============================================================================

# Common error code patterns
ERROR_CODE_PATTERNS = [
    r"\b(ORA-\d+)\b",           # Oracle errors
    r"\b(SQL\d+)\b",            # SQL Server errors
    r"\b(ODBC-\d+)\b",          # ODBC errors
    r"\b(ATT-\d+)\b",           # Attunity/Qlik errors
    r"\b(DB2-\d+)\b",           # DB2 errors
    r"\b(PG\d+)\b",             # PostgreSQL errors
    r"\b(MySQL-\d+)\b",         # MySQL errors
    r"\b(error[:\s]+\d{3,})\b", # Generic error codes
]


def extract_error_codes(text: str) -> List[str]:
    """
    Extract error codes from text.
    
    Args:
        text: Text to search for error codes
        
    Returns:
        List of found error codes
    """
    codes = []
    for pattern in ERROR_CODE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        codes.extend(matches)
    return list(set(codes))


# =============================================================================
# KB Fusion Functions
# =============================================================================

def fuse_answer(
    question: str,
    file_id: int,
    db: Session,
    local_answer: Optional[LocalAnswer] = None
) -> Optional[FusedAnswer]:
    """
    Try to answer a question by fusing local facts with KB articles.
    
    This function:
    1. Extracts relevant entities from the question (error codes, etc.)
    2. Gathers local facts from the log
    3. Searches KB for relevant articles
    4. Combines them into a coherent answer
    
    Args:
        question: User's question
        file_id: Log file ID
        db: Database session
        local_answer: Optional pre-computed local answer
        
    Returns:
        FusedAnswer if KB has relevant content, None otherwise
    """
    vector_store = get_vector_store()
    humanizer = get_humanizer()
    
    # Extract error codes from question
    error_codes = extract_error_codes(question)
    
    # Build search query
    search_query = question
    if error_codes:
        search_query = f"{' '.join(error_codes)} {question}"
    
    # Search KB
    kb_results = vector_store.query_kb(search_query, n_results=3)
    
    # Filter out low-similarity results
    relevant_articles = [
        kb for kb in kb_results 
        if kb.get('similarity', 0) > 0.3  # Minimum 30% similarity
    ]
    
    if not relevant_articles:
        return None  # No relevant KB content
    
    # Build local facts section
    local_facts = ""
    if local_answer:
        local_facts = local_answer.answer
    elif error_codes:
        # Search for these error codes in the log
        local_facts = _get_error_facts(error_codes, file_id, db)
    
    # Format KB articles
    kb_articles_formatted = []
    for kb in relevant_articles:
        kb_articles_formatted.append({
            "title": kb.get('title', 'Unknown'),
            "content": kb.get('content', '')[:800],  # Limit content
            "url": kb.get('url', ''),
            "similarity": kb.get('similarity', 0)
        })
    
    # Build fused answer
    answer = _build_fused_response(
        question=question,
        local_facts=local_facts,
        kb_articles=kb_articles_formatted,
        humanizer=humanizer
    )
    
    return FusedAnswer(
        answer=answer,
        local_facts=local_facts,
        kb_articles=kb_articles_formatted,
        confidence="high" if relevant_articles[0].get('similarity', 0) > 0.6 else "medium"
    )


def _get_error_facts(
    error_codes: List[str],
    file_id: int,
    db: Session
) -> str:
    """Get local facts about specific error codes."""
    facts = []
    
    for code in error_codes:
        # Search for this error code in the log
        matching_errors = db.query(LogError).filter(
            LogError.file_id == file_id,
            LogError.text.ilike(f"%{code}%")
        ).all()
        
        if matching_errors:
            facts.append(f"**{code}** appears {len(matching_errors)} time(s) in the log")
            
            # Get sample error text
            sample = matching_errors[0].text[:200] if matching_errors[0].text else ""
            if sample:
                facts.append(f"Sample: `{sample}...`")
    
    if not facts:
        return "No matching errors found in the log."
    
    return "\n".join(facts)


def _build_fused_response(
    question: str,
    local_facts: str,
    kb_articles: List[Dict[str, Any]],
    humanizer: Humanizer
) -> str:
    """Build the fused response combining local facts and KB."""
    
    parts = []
    
    # Add local facts if available
    if local_facts:
        parts.append("## From Your Log\n")
        parts.append(local_facts)
        parts.append("")
    
    # Add KB articles
    if kb_articles:
        parts.append("## Related Knowledge Base Articles\n")
        for i, article in enumerate(kb_articles, 1):
            similarity_pct = int(article.get('similarity', 0) * 100)
            parts.append(f"### {article['title']} ({similarity_pct}% match)\n")
            
            # Clean and format content
            content = article['content'].strip()
            if len(content) > 600:
                content = content[:600] + "..."
            parts.append(content)
            
            if article.get('url'):
                parts.append(f"\n[Read full article]({article['url']})")
            parts.append("")
    
    return "\n".join(parts)


# =============================================================================
# Specialized Fusion Functions
# =============================================================================

def fuse_error_explanation(
    error_code: str,
    file_id: int,
    db: Session
) -> Optional[FusedAnswer]:
    """
    Get explanation for a specific error code.
    
    Combines:
    - How many times error appears in log
    - KB article explaining the error
    - Recommended solutions from KB
    """
    vector_store = get_vector_store()
    
    # Get local error count
    error_count = db.query(LogError).filter(
        LogError.file_id == file_id,
        LogError.text.ilike(f"%{error_code}%")
    ).count()
    
    # Search KB for this error
    kb_results = vector_store.query_kb(
        f"{error_code} error explanation solution",
        n_results=2
    )
    
    relevant_articles = [kb for kb in kb_results if kb.get('similarity', 0) > 0.25]
    
    if not relevant_articles:
        # No KB articles, return just local facts
        if error_count > 0:
            return FusedAnswer(
                answer=f"**{error_code}** appears {error_count} time(s) in the log.\n\n"
                       f"No KB articles found for this error code.",
                local_facts=f"Error count: {error_count}",
                kb_articles=[],
                confidence="low"
            )
        return None
    
    # Build response
    parts = [f"## Error: {error_code}\n"]
    
    if error_count > 0:
        parts.append(f"**Found {error_count} occurrence(s) in your log.**\n")
    
    for article in relevant_articles:
        parts.append(f"### {article.get('title', 'KB Article')}\n")
        content = article.get('content', '')[:600]
        parts.append(content)
        if article.get('url'):
            parts.append(f"\n[Read more]({article['url']})")
        parts.append("")
    
    return FusedAnswer(
        answer="\n".join(parts),
        local_facts=f"Error count: {error_count}",
        kb_articles=[{
            "title": kb.get('title', ''),
            "url": kb.get('url', ''),
            "similarity": kb.get('similarity', 0)
        } for kb in relevant_articles],
        confidence="high" if error_count > 0 and relevant_articles else "medium"
    )


def get_kb_suggestion(question: str) -> Optional[str]:
    """
    Get a KB suggestion without file context.
    
    Useful for general questions about Qlik Replicate.
    """
    vector_store = get_vector_store()
    
    kb_results = vector_store.query_kb(question, n_results=2)
    relevant = [kb for kb in kb_results if kb.get('similarity', 0) > 0.4]
    
    if not relevant:
        return None
    
    parts = ["## Related KB Articles\n"]
    for article in relevant:
        parts.append(f"### {article.get('title', 'Article')}\n")
        parts.append(article.get('content', '')[:500])
        if article.get('url'):
            parts.append(f"\n[Read more]({article['url']})")
        parts.append("")
    
    return "\n".join(parts)