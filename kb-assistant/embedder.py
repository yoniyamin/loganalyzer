"""
Embedder for KB articles.
Handles chunking and storing documents in ChromaDB.
Uses ChromaDB's default local embeddings (all-MiniLM-L6-v2).
"""
import hashlib
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from rich.console import Console

from config import CHUNK_SIZE, CHUNK_OVERLAP
from chroma_client import get_kb_client

console = Console()


def estimate_tokens(text: str) -> int:
    """
    Estimate token count (rough approximation: ~4 chars per token).
    
    Args:
        text: Text to estimate
        
    Returns:
        Estimated token count
    """
    return len(text) // 4


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP
) -> List[str]:
    """
    Split text into overlapping chunks.
    
    Args:
        text: Text to chunk
        chunk_size: Target tokens per chunk
        chunk_overlap: Overlap tokens between chunks
        
    Returns:
        List of text chunks
    """
    # Convert token targets to character counts (rough: 4 chars per token)
    char_chunk_size = chunk_size * 4
    char_overlap = chunk_overlap * 4
    
    # Split into sentences first for cleaner chunks
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    chunks = []
    current_chunk = []
    current_length = 0
    
    for sentence in sentences:
        sentence_length = len(sentence)
        
        # If adding this sentence exceeds chunk size, save current chunk
        if current_length + sentence_length > char_chunk_size and current_chunk:
            chunk_text = ' '.join(current_chunk)
            chunks.append(chunk_text)
            
            # Keep overlap from end of current chunk
            overlap_text = chunk_text[-char_overlap:] if len(chunk_text) > char_overlap else chunk_text
            current_chunk = [overlap_text]
            current_length = len(overlap_text)
        
        current_chunk.append(sentence)
        current_length += sentence_length + 1  # +1 for space
    
    # Add final chunk
    if current_chunk:
        chunks.append(' '.join(current_chunk))
    
    # Filter out very short chunks
    chunks = [c for c in chunks if len(c) > 100]
    
    return chunks


def generate_chunk_id(source: str, url: str, chunk_index: int) -> str:
    """
    Generate a unique ID for a chunk.
    
    Args:
        source: Source type (e.g., 'kb_article', 'markdown')
        url: Source URL or file path
        chunk_index: Index of chunk within document
        
    Returns:
        Unique chunk ID
    """
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"{source}_{url_hash}_{chunk_index}"


def embed_article(
    article: Dict[str, Any],
    source: str = "kb_article"
) -> int:
    """
    Chunk and embed a single article into ChromaDB.
    
    Args:
        article: Article dict with 'url', 'title', 'content', etc.
        source: Source type identifier
        
    Returns:
        Number of chunks added
    """
    client = get_kb_client()
    collection = client.get_collection()
    
    content = article.get("content", "")
    if not content:
        return 0
    
    # Prepend title to content for better context
    full_text = f"{article.get('title', 'Untitled')}\n\n{content}"
    
    # Chunk the text
    chunks = chunk_text(full_text)
    
    if not chunks:
        return 0
    
    # Prepare documents for ChromaDB
    ids = []
    documents = []
    metadatas = []
    
    for i, chunk in enumerate(chunks):
        chunk_id = generate_chunk_id(source, article["url"], i)
        
        ids.append(chunk_id)
        documents.append(chunk)
        metadatas.append({
            "source": source,
            "url": article["url"],
            "title": article.get("title", "Untitled"),
            "article_id": article.get("article_id", ""),
            "chunk_index": i,
            "total_chunks": len(chunks),
            "content_hash": article.get("content_hash", ""),
            "indexed_at": datetime.utcnow().isoformat(),
        })
    
    # Add to collection (ChromaDB handles embeddings automatically)
    try:
        # First try to delete existing chunks for this URL (for re-indexing)
        existing = collection.get(
            where={"url": article["url"]}
        )
        if existing and existing['ids']:
            collection.delete(ids=existing['ids'])
        
        # Add new chunks
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
        return len(chunks)
    except Exception as e:
        console.print(f"[red]Error embedding article: {e}[/red]")
        return 0


def embed_articles_batch(
    articles: List[Dict[str, Any]],
    source: str = "kb_article",
    progress_callback=None
) -> Dict[str, int]:
    """
    Embed multiple articles.
    
    Args:
        articles: List of article dicts
        source: Source type identifier
        progress_callback: Optional callback(current, total, chunks_added)
        
    Returns:
        Stats dict with total_articles, total_chunks, failed
    """
    stats = {
        "total_articles": len(articles),
        "total_chunks": 0,
        "successful": 0,
        "failed": 0
    }
    
    for i, article in enumerate(articles):
        chunks_added = embed_article(article, source)
        
        if chunks_added > 0:
            stats["successful"] += 1
            stats["total_chunks"] += chunks_added
        else:
            stats["failed"] += 1
        
        if progress_callback:
            progress_callback(i + 1, len(articles), chunks_added)
    
    return stats


def embed_markdown(
    content: str,
    file_path: str,
    title: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> int:
    """
    Embed a markdown document.
    
    Args:
        content: Markdown content
        file_path: Path to the markdown file
        title: Optional title (extracted from frontmatter or first heading)
        metadata: Optional additional metadata
        
    Returns:
        Number of chunks added
    """
    # Create article-like dict for embedding
    article = {
        "url": file_path,
        "title": title or "Untitled Document",
        "content": content,
        "content_hash": hashlib.md5(content.encode()).hexdigest()[:12],
    }
    
    if metadata:
        article.update(metadata)
    
    return embed_article(article, source="markdown")


def query_kb(
    query: str,
    n_results: int = 5,
    source_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Query the KB for similar content.
    
    Args:
        query: Query text
        n_results: Number of results to return
        source_filter: Optional filter by source type
        
    Returns:
        List of matching documents with metadata
    """
    client = get_kb_client()
    collection = client.get_collection()
    
    where_filter = {"source": source_filter} if source_filter else None
    
    try:
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where_filter
        )
        
        # Format results
        formatted = []
        if results and results['documents']:
            for i, doc in enumerate(results['documents'][0]):
                formatted.append({
                    "content": doc,
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                    "distance": results['distances'][0][i] if results.get('distances') else None
                })
        
        return formatted
    except Exception as e:
        console.print(f"[red]Error querying KB: {e}[/red]")
        return []


if __name__ == "__main__":
    # Test chunking
    test_text = """
    This is a test article about Qlik Replicate. Qlik Replicate is a data replication 
    and ingestion solution that enables real-time data movement across enterprise systems.
    
    It supports CDC (Change Data Capture) from various source databases including Oracle, 
    SQL Server, MySQL, and PostgreSQL. The captured changes are then applied to target 
    systems in near real-time.
    
    Common use cases include data warehouse loading, database migration, and creating 
    analytics-ready data lakes. The solution handles both initial full load and ongoing 
    change replication.
    """ * 10  # Repeat to create larger content
    
    chunks = chunk_text(test_text)
    console.print(f"[green]Created {len(chunks)} chunks from test text[/green]")
    for i, chunk in enumerate(chunks):
        console.print(f"  Chunk {i+1}: {len(chunk)} chars, ~{estimate_tokens(chunk)} tokens")
