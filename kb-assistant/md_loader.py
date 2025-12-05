"""
Markdown file loader for KB enrichment.
Supports YAML frontmatter for metadata.
"""
import os
from pathlib import Path
from typing import Dict, Any, Optional, List

import frontmatter
from rich.console import Console

from embedder import embed_markdown

console = Console()


def load_markdown_file(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Load a markdown file with optional frontmatter.
    
    Args:
        file_path: Path to the markdown file
        
    Returns:
        Dict with 'content', 'title', 'metadata', or None if failed
    """
    path = Path(file_path)
    
    if not path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        return None
    
    if not path.suffix.lower() in ['.md', '.markdown']:
        console.print(f"[yellow]Warning: File does not have .md extension: {file_path}[/yellow]")
    
    try:
        # Load with frontmatter support
        post = frontmatter.load(path)
        
        content = post.content
        metadata = dict(post.metadata) if post.metadata else {}
        
        # Extract title from frontmatter or first heading
        title = metadata.pop('title', None)
        
        if not title:
            # Try to extract from first heading
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('# '):
                    title = line[2:].strip()
                    break
        
        if not title:
            title = path.stem  # Use filename as fallback
        
        return {
            "content": content,
            "title": title,
            "metadata": metadata,
            "file_path": str(path.absolute()),
            "file_name": path.name,
        }
    
    except Exception as e:
        console.print(f"[red]Error loading {file_path}: {e}[/red]")
        return None


def load_and_embed_markdown(file_path: str) -> int:
    """
    Load a markdown file and embed it into the KB.
    
    Args:
        file_path: Path to the markdown file
        
    Returns:
        Number of chunks added (0 if failed)
    """
    doc = load_markdown_file(file_path)
    
    if not doc:
        return 0
    
    chunks_added = embed_markdown(
        content=doc["content"],
        file_path=doc["file_path"],
        title=doc["title"],
        metadata=doc.get("metadata")
    )
    
    if chunks_added > 0:
        console.print(f"[green]Embedded {chunks_added} chunks from: {doc['file_name']}[/green]")
    else:
        console.print(f"[yellow]No chunks created from: {doc['file_name']}[/yellow]")
    
    return chunks_added


def load_markdown_directory(
    directory: str,
    recursive: bool = True,
    progress_callback=None
) -> Dict[str, int]:
    """
    Load all markdown files from a directory.
    
    Args:
        directory: Directory path
        recursive: If True, search subdirectories
        progress_callback: Optional callback(current, total, file_name)
        
    Returns:
        Stats dict with files_processed, chunks_added, failed
    """
    path = Path(directory)
    
    if not path.exists():
        console.print(f"[red]Directory not found: {directory}[/red]")
        return {"files_processed": 0, "chunks_added": 0, "failed": 0}
    
    # Find markdown files
    if recursive:
        md_files = list(path.rglob("*.md")) + list(path.rglob("*.markdown"))
    else:
        md_files = list(path.glob("*.md")) + list(path.glob("*.markdown"))
    
    stats = {
        "files_processed": 0,
        "chunks_added": 0,
        "failed": 0
    }
    
    for i, md_file in enumerate(md_files):
        chunks = load_and_embed_markdown(str(md_file))
        
        if chunks > 0:
            stats["files_processed"] += 1
            stats["chunks_added"] += chunks
        else:
            stats["failed"] += 1
        
        if progress_callback:
            progress_callback(i + 1, len(md_files), md_file.name)
    
    return stats


def preview_markdown(file_path: str, max_chars: int = 500) -> None:
    """
    Preview a markdown file's content and metadata.
    
    Args:
        file_path: Path to the markdown file
        max_chars: Maximum characters to show in preview
    """
    doc = load_markdown_file(file_path)
    
    if not doc:
        return
    
    console.print(f"\n[bold]File:[/bold] {doc['file_name']}")
    console.print(f"[bold]Title:[/bold] {doc['title']}")
    
    if doc.get('metadata'):
        console.print(f"[bold]Metadata:[/bold]")
        for key, value in doc['metadata'].items():
            console.print(f"  {key}: {value}")
    
    content_preview = doc['content'][:max_chars]
    if len(doc['content']) > max_chars:
        content_preview += "..."
    
    console.print(f"\n[bold]Content preview:[/bold]\n{content_preview}")
    console.print(f"\n[dim]Total length: {len(doc['content'])} characters[/dim]")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        console.print(f"[bold]Loading markdown file: {file_path}[/bold]\n")
        preview_markdown(file_path)
    else:
        console.print("[yellow]Usage: python md_loader.py <path_to_markdown_file>[/yellow]")
        console.print("\n[dim]Example frontmatter:[/dim]")
        console.print("""
---
title: My Knowledge Article
tags: [replicate, troubleshooting]
author: John Doe
---

# Article Content

Your markdown content here...
""")
