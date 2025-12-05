#!/usr/bin/env python3
"""
Qlik Replicate KB Loader CLI

Main entrypoint for scraping KB articles and loading markdown files
into the ChromaDB knowledge base.

Usage:
    python kb_loader.py                     # Interactive mode
    python kb_loader.py --mode scrape       # Scrape KB articles from sitemaps
    python kb_loader.py --mode md --file path/to/doc.md  # Load single markdown
    python kb_loader.py --mode query --query "error message"  # Query the KB
    python kb_loader.py --stats             # Show KB statistics
"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from chroma_client import get_kb_client
from kb_discovery import discover_kb_articles, discover_all_kb_articles
from article_fetcher import fetch_and_parse_article, CRAWL_DELAY_SECONDS
from embedder import embed_article, query_kb
from md_loader import load_and_embed_markdown, preview_markdown
from db_client import (
    init_kb_tables,
    get_indexed_urls,
    add_or_update_article,
    mark_article_failed,
    get_stats as get_db_stats,
    get_all_articles,
    clear_all_articles,
)

console = Console()


def show_stats():
    """Display KB statistics."""
    client = get_kb_client()
    chroma_stats = client.get_stats()
    db_stats = get_db_stats()
    
    table = Table(title="KB Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Collection Name", chroma_stats["collection_name"])
    table.add_row("ChromaDB Chunks", str(chroma_stats["document_count"]))
    table.add_row("", "")
    table.add_row("[bold]Articles in Database[/bold]", "")
    table.add_row("  Total Articles", str(db_stats["total_articles"]))
    table.add_row("  KB Articles", str(db_stats["kb_articles"]))
    table.add_row("  Markdown Files", str(db_stats["markdown_files"]))
    table.add_row("  Indexed", str(db_stats["indexed"]))
    table.add_row("  Failed", str(db_stats["failed"]))
    table.add_row("", "")
    table.add_row("ChromaDB Path", chroma_stats["persist_directory"])
    
    console.print(table)


def run_scrape_mode(skip_existing: bool = True):
    """
    Run the KB scraping workflow.
    
    Parses articles from saved HTML file (kb_page.html) and fetches/embeds them.
    
    Args:
        skip_existing: If True, skip already indexed articles
    """
    # Initialize database tables
    init_kb_tables()
    
    console.print(Panel.fit(
        "[bold blue]Qlik Replicate KB Scraper[/bold blue]\n"
        "This will scrape KB articles from Qlik Community.",
        title="Scrape Mode"
    ))
    
    # Step 1: Discover articles
    console.print("\n[bold]Step 1: Discovering articles from KB listing...[/bold]")
    
    # Discover articles from saved HTML file
    # Both functions now work the same way (parse saved HTML)
    articles = discover_kb_articles()
    
    if not articles:
        console.print("[yellow]No articles found. Exiting.[/yellow]")
        return
    
    # Filter out already indexed
    if skip_existing:
        indexed_urls = get_indexed_urls()
        original_count = len(articles)
        articles = [a for a in articles if a["url"] not in indexed_urls]
        skipped = original_count - len(articles)
        if skipped > 0:
            console.print(f"[dim]Skipping {skipped} already indexed articles[/dim]")
    
    if not articles:
        console.print("[green]All articles already indexed. Nothing to do.[/green]")
        return
    
    # Estimate time
    est_seconds = len(articles) * (CRAWL_DELAY_SECONDS + 2)  # fetch + process + delay
    est_minutes = est_seconds / 60
    
    console.print(f"\n[bold]Found {len(articles)} articles to process[/bold]")
    console.print(f"[dim]Estimated time: {est_minutes:.1f} minutes[/dim]")
    
    # Confirmation
    if not Confirm.ask("\n[yellow]Proceed with scraping?[/yellow]"):
        console.print("[dim]Cancelled by user[/dim]")
        return
    
    # Step 2: Fetch and embed articles
    console.print("\n[bold]Step 2: Fetching and embedding articles...[/bold]")
    
    successful_count = 0
    failed_list = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        task = progress.add_task("Processing articles...", total=len(articles))
        
        for i, article_info in enumerate(articles):
            url = article_info["url"]
            discovered_title = article_info.get("title", "")
            discovered_id = article_info.get("article_id")
            progress.update(task, description=f"[{i+1}/{len(articles)}] Fetching...")
            
            # Fetch article content
            article = fetch_and_parse_article(url)
            
            if article:
                # Use discovered title/id as fallback
                title = article.get("title") or discovered_title or "Untitled"
                article_id = article.get("article_id") or discovered_id
                
                # Embed article
                chunks = embed_article(article)
                
                if chunks > 0:
                    # Save to database
                    add_or_update_article(
                        url=url,
                        title=title,
                        source="kb_article",
                        article_id=article_id,
                        content_hash=article.get("content_hash"),
                        content_length=article.get("content_length", 0),
                        chunks_count=chunks,
                        last_modified=None,
                        status="indexed"
                    )
                    successful_count += 1
                    progress.update(task, description=f"[{i+1}/{len(articles)}] Added {chunks} chunks")
                else:
                    mark_article_failed(url, "embedding_failed")
                    failed_list.append({"url": url, "reason": "embedding failed"})
            else:
                mark_article_failed(url, "fetch_failed")
                failed_list.append({"url": url, "reason": "fetch/parse failed"})
            
            progress.advance(task)
            
            # Polite delay
            if i < len(articles) - 1:
                time.sleep(CRAWL_DELAY_SECONDS)
    
    # Summary
    console.print("\n" + "="*50)
    console.print(f"[bold green]Completed![/bold green]")
    console.print(f"  Successful: {successful_count}")
    console.print(f"  Failed: {len(failed_list)}")
    
    if failed_list and len(failed_list) <= 10:
        console.print("\n[yellow]Failed articles:[/yellow]")
        for f in failed_list:
            console.print(f"  - {f['url']}: {f['reason']}")
    
    show_stats()


def run_markdown_mode(file_path: str, preview_only: bool = False):
    """
    Load a markdown file into the KB.
    
    Args:
        file_path: Path to markdown file
        preview_only: If True, only preview without embedding
    """
    # Initialize database tables
    init_kb_tables()
    
    console.print(Panel.fit(
        f"[bold blue]Loading Markdown File[/bold blue]\n{file_path}",
        title="Markdown Mode"
    ))
    
    path = Path(file_path)
    if not path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        return
    
    # Preview the file
    preview_markdown(file_path)
    
    if preview_only:
        return
    
    # Confirmation
    if not Confirm.ask("\n[yellow]Embed this file into the KB?[/yellow]"):
        console.print("[dim]Cancelled by user[/dim]")
        return
    
    # Embed
    chunks = load_and_embed_markdown(file_path)
    
    if chunks > 0:
        # Save to database
        add_or_update_article(
            url=str(path.absolute()),
            title=path.stem,
            source="markdown",
            content_hash=None,
            content_length=path.stat().st_size,
            chunks_count=chunks,
            status="indexed"
        )
        console.print(f"\n[bold green]Success! Added {chunks} chunks to KB[/bold green]")
    else:
        console.print("[red]Failed to embed file[/red]")
    
    show_stats()


def run_query_mode(query: str, n_results: int = 5):
    """
    Query the KB and display results.
    
    Args:
        query: Search query
        n_results: Number of results to show
    """
    console.print(Panel.fit(
        f"[bold blue]Querying KB[/bold blue]\n\"{query}\"",
        title="Query Mode"
    ))
    
    results = query_kb(query, n_results=n_results)
    
    if not results:
        console.print("[yellow]No results found[/yellow]")
        return
    
    console.print(f"\n[bold]Found {len(results)} results:[/bold]\n")
    
    for i, result in enumerate(results, 1):
        meta = result.get("metadata", {})
        distance = result.get("distance", 0)
        similarity = max(0, 1 - distance) * 100  # Convert distance to similarity %
        
        console.print(f"[bold cyan]Result {i}[/bold cyan] (similarity: {similarity:.1f}%)")
        console.print(f"  [bold]Title:[/bold] {meta.get('title', 'Unknown')}")
        console.print(f"  [bold]Source:[/bold] {meta.get('source', 'Unknown')}")
        console.print(f"  [bold]URL:[/bold] {meta.get('url', 'N/A')}")
        
        # Show content preview
        content = result.get("content", "")[:300]
        if len(result.get("content", "")) > 300:
            content += "..."
        console.print(f"  [dim]{content}[/dim]\n")


def run_interactive_mode():
    """Run interactive mode with menu."""
    # Initialize database tables
    init_kb_tables()
    
    console.print(Panel.fit(
        "[bold blue]Qlik Replicate KB Loader[/bold blue]\n"
        "Interactive mode - select an option below",
        title="KB Assistant"
    ))
    
    while True:
        console.print("\n[bold]Options:[/bold]")
        console.print("  1. Scrape KB articles from Qlik Community")
        console.print("  2. Load a markdown file")
        console.print("  3. Query the knowledge base")
        console.print("  4. Show statistics")
        console.print("  5. List indexed articles")
        console.print("  6. Clear KB (delete all)")
        console.print("  q. Quit")
        
        choice = Prompt.ask("\nSelect option", choices=["1", "2", "3", "4", "5", "6", "q"], default="q")
        
        if choice == "1":
            run_scrape_mode()
        
        elif choice == "2":
            file_path = Prompt.ask("Enter markdown file path")
            if file_path:
                run_markdown_mode(file_path)
        
        elif choice == "3":
            query = Prompt.ask("Enter search query")
            if query:
                run_query_mode(query)
        
        elif choice == "4":
            show_stats()
        
        elif choice == "5":
            # List indexed articles
            articles = get_all_articles(status="indexed")
            if not articles:
                console.print("[yellow]No articles indexed yet.[/yellow]")
            else:
                table = Table(title=f"Indexed Articles ({len(articles)})")
                table.add_column("ID", style="dim")
                table.add_column("Title", style="cyan", max_width=50)
                table.add_column("Source", style="green")
                table.add_column("Chunks", justify="right")
                table.add_column("Indexed At", style="dim")
                
                for article in articles[:50]:  # Show first 50
                    table.add_row(
                        article.article_id or "-",
                        article.title[:50] + "..." if len(article.title) > 50 else article.title,
                        article.source,
                        str(article.chunks_count),
                        article.indexed_at.strftime("%Y-%m-%d %H:%M") if article.indexed_at else "-"
                    )
                
                console.print(table)
                if len(articles) > 50:
                    console.print(f"[dim]...and {len(articles) - 50} more[/dim]")
        
        elif choice == "6":
            if Confirm.ask("[red]This will delete ALL documents from the KB. Are you sure?[/red]", default=False):
                # Clear ChromaDB
                client = get_kb_client()
                chroma_deleted = client.clear_collection()
                console.print(f"[green]Deleted {chroma_deleted} chunks from ChromaDB[/green]")
                
                # Clear database
                db_deleted = clear_all_articles()
                console.print(f"[green]Deleted {db_deleted} articles from database[/green]")
        
        elif choice == "q":
            console.print("[dim]Goodbye![/dim]")
            break


def main():
    """Main entry point."""
    # Initialize database on startup
    init_kb_tables()
    
    parser = argparse.ArgumentParser(
        description="Qlik Replicate KB Loader - Scrape and embed KB articles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python kb_loader.py                           # Interactive mode
  python kb_loader.py --mode scrape             # Scrape KB articles from saved HTML
  python kb_loader.py --mode md --file doc.md   # Load markdown file
  python kb_loader.py --mode query -q "error"   # Query the KB
  python kb_loader.py --stats                   # Show statistics
        """
    )
    
    parser.add_argument(
        "--mode", "-m",
        choices=["scrape", "md", "query"],
        help="Operation mode"
    )
    parser.add_argument(
        "--file", "-f",
        help="Markdown file path (for --mode md)"
    )
    parser.add_argument(
        "--query", "-q",
        help="Search query (for --mode query)"
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show KB statistics"
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Re-index already indexed articles (for --mode scrape)"
    )
    
    args = parser.parse_args()
    
    # Handle --stats flag
    if args.stats:
        show_stats()
        return
    
    # Handle mode-based operations
    if args.mode == "scrape":
        run_scrape_mode(skip_existing=not args.no_skip)
    
    elif args.mode == "md":
        if not args.file:
            console.print("[red]Error: --file required for markdown mode[/red]")
            sys.exit(1)
        run_markdown_mode(args.file)
    
    elif args.mode == "query":
        if not args.query:
            console.print("[red]Error: --query required for query mode[/red]")
            sys.exit(1)
        run_query_mode(args.query)
    
    else:
        # Interactive mode
        run_interactive_mode()


if __name__ == "__main__":
    main()
