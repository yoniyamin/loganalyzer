#!/usr/bin/env python3
"""
Qlik Replicate KB Loader CLI

Main entrypoint for scraping KB articles and loading markdown files
into the ChromaDB knowledge base.

Features:
- Threaded scraping (producer) and embedding (consumer) for better performance
- Detailed logging to file and console
- Per-article status tracking in SQLite
- Real-time progress indicators

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
import logging
import threading
import queue
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.logging import RichHandler

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

# Setup logging
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"kb_loader_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Configure file logging
file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
))

# Configure root logger
logger = logging.getLogger('kb_loader')
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)

# Also log to console (INFO level)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
logger.addHandler(console_handler)

console = Console()


# Threading configuration
QUEUE_SIZE = 50  # Max articles in queue
NUM_EMBED_WORKERS = 1  # Number of embedding workers (1 is usually enough)


class ScraperStats:
    """Thread-safe statistics tracker."""
    def __init__(self):
        self.lock = threading.Lock()
        self.fetched = 0
        self.fetch_failed = 0
        self.embedded = 0
        self.embed_failed = 0
        self.total_chunks = 0
    
    def add_fetch_success(self):
        with self.lock:
            self.fetched += 1
    
    def add_fetch_failure(self):
        with self.lock:
            self.fetch_failed += 1
    
    def add_embed_success(self, chunks: int):
        with self.lock:
            self.embedded += 1
            self.total_chunks += chunks
    
    def add_embed_failure(self):
        with self.lock:
            self.embed_failed += 1
    
    def get_stats(self):
        with self.lock:
            return {
                'fetched': self.fetched,
                'fetch_failed': self.fetch_failed,
                'embedded': self.embedded,
                'embed_failed': self.embed_failed,
                'total_chunks': self.total_chunks
            }


def fetch_worker(
    articles: list,
    article_queue: queue.Queue,
    stats: ScraperStats,
    stop_event: threading.Event
):
    """
    Worker thread that fetches articles and puts them in a queue.
    
    Args:
        articles: List of article info dicts (url, title, article_id)
        article_queue: Queue to put fetched articles
        stats: Shared statistics object
        stop_event: Event to signal stop
    """
    for i, article_info in enumerate(articles):
        if stop_event.is_set():
            logger.info("Fetch worker stopped by signal")
            break
        
        url = article_info["url"]
        discovered_title = article_info.get("title", "")
        discovered_id = article_info.get("article_id")
        
        logger.info(f"[{i+1}/{len(articles)}] Fetching: {url}")
        
        try:
            article = fetch_and_parse_article(url)
            
            if article:
                # Add discovered metadata as fallback
                article['discovered_title'] = discovered_title
                article['discovered_id'] = discovered_id
                article['url'] = url  # Ensure URL is set
                
                article_queue.put(article)
                stats.add_fetch_success()
                logger.info(f"[{i+1}/{len(articles)}] Fetched OK: {article.get('title', discovered_title)[:60]}")
            else:
                # Log failure and mark in DB immediately
                stats.add_fetch_failure()
                mark_article_failed(url, "fetch_failed")
                logger.warning(f"[{i+1}/{len(articles)}] FETCH FAILED: {url}")
        
        except Exception as e:
            stats.add_fetch_failure()
            mark_article_failed(url, f"fetch_error: {str(e)[:100]}")
            logger.error(f"[{i+1}/{len(articles)}] FETCH ERROR: {url} - {e}")
        
        # Polite delay between requests
        if i < len(articles) - 1 and not stop_event.is_set():
            time.sleep(CRAWL_DELAY_SECONDS)
    
    # Signal end of fetching
    article_queue.put(None)
    logger.info("Fetch worker completed")


def embed_worker(
    article_queue: queue.Queue,
    stats: ScraperStats,
    stop_event: threading.Event,
    total_articles: int
):
    """
    Worker thread that embeds articles from the queue.
    
    Args:
        article_queue: Queue to get articles from
        stats: Shared statistics object
        stop_event: Event to signal stop
        total_articles: Total number of articles (for logging)
    """
    processed = 0
    
    while not stop_event.is_set():
        try:
            article = article_queue.get(timeout=1.0)
            
            if article is None:
                # End signal from fetch worker
                logger.info("Embed worker received stop signal")
                break
            
            processed += 1
            url = article.get("url", "")
            title = article.get("title") or article.get("discovered_title") or "Untitled"
            article_id = article.get("article_id") or article.get("discovered_id")
            
            logger.info(f"[Embed {processed}] Processing: {title[:60]}")
            
            try:
                # Embed article
                chunks = embed_article(article)
                
                if chunks > 0:
                    # Save to database immediately
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
                    stats.add_embed_success(chunks)
                    logger.info(f"[Embed {processed}] SUCCESS: {title[:50]} ({chunks} chunks)")
                else:
                    mark_article_failed(url, "embed_no_chunks")
                    stats.add_embed_failure()
                    logger.warning(f"[Embed {processed}] FAILED (no chunks): {title[:50]}")
            
            except Exception as e:
                mark_article_failed(url, f"embed_error: {str(e)[:100]}")
                stats.add_embed_failure()
                logger.error(f"[Embed {processed}] ERROR: {title[:50]} - {e}")
            
            article_queue.task_done()
        
        except queue.Empty:
            continue
    
    logger.info(f"Embed worker completed. Processed {processed} articles.")


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
    Run the KB scraping workflow with threaded fetching and embedding.
    
    Args:
        skip_existing: If True, skip already indexed articles
    """
    # Initialize database tables
    init_kb_tables()
    
    console.print(Panel.fit(
        "[bold blue]Qlik Replicate KB Scraper[/bold blue]\n"
        "This will scrape KB articles from Qlik Community.\n"
        f"Log file: {LOG_FILE}",
        title="Scrape Mode"
    ))
    
    logger.info("="*60)
    logger.info("Starting KB scrape session")
    logger.info("="*60)
    
    # Step 1: Discover articles
    console.print("\n[bold]Step 1: Discovering articles from KB listing...[/bold]")
    logger.info("Discovering articles from KB listing...")
    
    articles = discover_kb_articles()
    
    if not articles:
        console.print("[yellow]No articles found. Exiting.[/yellow]")
        logger.warning("No articles found")
        return
    
    logger.info(f"Discovered {len(articles)} articles")
    
    # Filter out already indexed
    if skip_existing:
        indexed_urls = get_indexed_urls()
        original_count = len(articles)
        articles = [a for a in articles if a["url"] not in indexed_urls]
        skipped = original_count - len(articles)
        if skipped > 0:
            console.print(f"[dim]Skipping {skipped} already indexed articles[/dim]")
            logger.info(f"Skipping {skipped} already indexed articles")
    
    if not articles:
        console.print("[green]All articles already indexed. Nothing to do.[/green]")
        logger.info("All articles already indexed")
        return
    
    # Estimate time (crawl delay + ~2-3 seconds for fetch/parse/embed per article)
    avg_per_article = CRAWL_DELAY_SECONDS + 3  # delay + fetch/parse/embed overhead
    est_seconds = len(articles) * avg_per_article
    est_minutes = est_seconds / 60
    
    console.print(f"\n[bold]Found {len(articles)} articles to process[/bold]")
    console.print(f"[dim]Crawl delay: {CRAWL_DELAY_SECONDS}s per article[/dim]")
    console.print(f"[dim]Estimated time: ~{est_minutes:.1f} minutes ({avg_per_article:.1f}s per article)[/dim]")
    console.print(f"[dim]Log file: {LOG_FILE}[/dim]")
    
    logger.info(f"Articles to process: {len(articles)}")
    logger.info(f"Estimated time: {est_minutes:.1f} minutes")
    
    # Confirmation
    if not Confirm.ask("\n[yellow]Proceed with scraping?[/yellow]"):
        console.print("[dim]Cancelled by user[/dim]")
        logger.info("Cancelled by user")
        return
    
    # Step 2: Fetch and embed articles using threads
    console.print("\n[bold]Step 2: Fetching and embedding articles...[/bold]")
    console.print("[dim]Check the log file for detailed per-article status[/dim]")
    logger.info("Starting threaded fetch and embed process")
    
    # Create shared objects
    article_queue = queue.Queue(maxsize=QUEUE_SIZE)
    stats = ScraperStats()
    stop_event = threading.Event()
    
    # Start fetch worker thread
    fetch_thread = threading.Thread(
        target=fetch_worker,
        args=(articles, article_queue, stats, stop_event),
        name="FetchWorker"
    )
    fetch_thread.start()
    logger.info("Fetch worker thread started")
    
    # Start embed worker thread
    embed_thread = threading.Thread(
        target=embed_worker,
        args=(article_queue, stats, stop_event, len(articles)),
        name="EmbedWorker"
    )
    embed_thread.start()
    logger.info("Embed worker thread started")
    
    # Progress display
    start_time = time.time()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        task = progress.add_task("Processing...", total=len(articles))
        
        try:
            while fetch_thread.is_alive() or embed_thread.is_alive():
                current_stats = stats.get_stats()
                total_processed = current_stats['embedded'] + current_stats['embed_failed']
                
                progress.update(
                    task,
                    completed=total_processed,
                    description=f"Fetched: {current_stats['fetched']} | Embedded: {current_stats['embedded']} | Failed: {current_stats['fetch_failed'] + current_stats['embed_failed']}"
                )
                
                time.sleep(0.5)
            
            # Final update
            final_stats = stats.get_stats()
            progress.update(task, completed=len(articles))
        
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted! Stopping workers...[/yellow]")
            logger.warning("Process interrupted by user")
            stop_event.set()
            fetch_thread.join(timeout=5)
            embed_thread.join(timeout=5)
    
    # Wait for threads to complete
    fetch_thread.join()
    embed_thread.join()
    
    elapsed = time.time() - start_time
    final_stats = stats.get_stats()
    
    # Summary
    logger.info("="*60)
    logger.info("Scrape session completed")
    logger.info(f"  Time elapsed: {elapsed/60:.1f} minutes")
    logger.info(f"  Fetched: {final_stats['fetched']}")
    logger.info(f"  Fetch failed: {final_stats['fetch_failed']}")
    logger.info(f"  Embedded: {final_stats['embedded']}")
    logger.info(f"  Embed failed: {final_stats['embed_failed']}")
    logger.info(f"  Total chunks: {final_stats['total_chunks']}")
    logger.info("="*60)
    
    console.print("\n" + "="*50)
    console.print(f"[bold green]Completed![/bold green]")
    console.print(f"  Time elapsed: {elapsed/60:.1f} minutes")
    console.print(f"  Successfully embedded: {final_stats['embedded']}")
    console.print(f"  Total chunks created: {final_stats['total_chunks']}")
    console.print(f"  Failed (fetch): {final_stats['fetch_failed']}")
    console.print(f"  Failed (embed): {final_stats['embed_failed']}")
    console.print(f"\n[dim]Log file: {LOG_FILE}[/dim]")
    
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
        similarity = max(0, 1 - distance) * 100
        
        console.print(f"[bold cyan]Result {i}[/bold cyan] (similarity: {similarity:.1f}%)")
        console.print(f"  [bold]Title:[/bold] {meta.get('title', 'Unknown')}")
        console.print(f"  [bold]Source:[/bold] {meta.get('source', 'Unknown')}")
        console.print(f"  [bold]URL:[/bold] {meta.get('url', 'N/A')}")
        
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
        console.print("  7. View recent logs")
        console.print("  q. Quit")
        
        choice = Prompt.ask("\nSelect option", choices=["1", "2", "3", "4", "5", "6", "7", "q"], default="q")
        
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
                
                for article in articles[:50]:
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
        
        elif choice == "7":
            # View recent logs
            log_files = sorted(LOG_DIR.glob("kb_loader_*.log"), reverse=True)[:5]
            if not log_files:
                console.print("[yellow]No log files found[/yellow]")
            else:
                console.print("\n[bold]Recent log files:[/bold]")
                for lf in log_files:
                    size = lf.stat().st_size
                    console.print(f"  {lf.name} ({size/1024:.1f} KB)")
                
                if Confirm.ask("\nView latest log?"):
                    with open(log_files[0], 'r', encoding='utf-8') as f:
                        lines = f.readlines()[-100:]  # Last 100 lines
                        for line in lines:
                            console.print(f"[dim]{line.rstrip()}[/dim]")
        
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
