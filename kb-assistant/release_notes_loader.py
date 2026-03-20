#!/usr/bin/env python3
"""
Qlik Replicate Release Notes Loader CLI

Scrapes release notes from saved HTML and indexes them into ChromaDB
for correlation with log analysis reports.

Usage:
    python release_notes_loader.py                         # Interactive mode
    python release_notes_loader.py --mode scrape           # Scrape release notes
    python release_notes_loader.py --mode query -q "Oracle CDC"  # Query
    python release_notes_loader.py --stats                 # Show stats
"""
import argparse
import sys
import time
import logging
import threading
import queue
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    Progress, SpinnerColumn, BarColumn, TextColumn,
    TimeElapsedColumn, TimeRemainingColumn,
)
from rich.prompt import Confirm, Prompt
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent))

import chromadb
from chromadb.config import Settings

from config import CHROMA_PERSIST_DIR, CHUNK_SIZE, CHUNK_OVERLAP, CRAWL_DELAY_SECONDS
from release_notes_discovery import discover_release_notes
from release_notes_fetcher import fetch_and_parse_release_note
from embedder import chunk_text, generate_chunk_id
from db_client import (
    init_kb_tables, get_indexed_urls,
    add_or_update_article, mark_article_failed,
    get_stats as get_db_stats,
)

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"release_notes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

logger = logging.getLogger('release_notes_loader')
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)
console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
logger.addHandler(console_handler)

console = Console()

COLLECTION_NAME = "qlik_replicate_release_notes"


def _get_rn_collection():
    """Get or create the release notes ChromaDB collection."""
    client = chromadb.PersistentClient(
        path=CHROMA_PERSIST_DIR,
        settings=Settings(anonymized_telemetry=False, allow_reset=True),
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "Qlik Replicate release notes and fixes"},
    )


def embed_release_note(article: dict) -> int:
    """
    Chunk and embed a single release note into ChromaDB.

    Returns:
        Number of chunks added
    """
    collection = _get_rn_collection()

    content = article.get("content", "")
    if not content:
        return 0

    full_text = f"{article.get('title', '')}\n\n{content}"
    chunks = chunk_text(full_text)
    if not chunks:
        return 0

    endpoint_types_str = ",".join(
        e.lower() for e in article.get("endpoint_types", [])
    )

    ids, documents, metadatas = [], [], []
    for i, chunk in enumerate(chunks):
        chunk_id = generate_chunk_id("release_notes", article["url"], i)
        ids.append(chunk_id)
        documents.append(chunk)
        metadatas.append({
            "source": "release_notes",
            "url": article["url"],
            "title": article.get("title", "Untitled"),
            "article_id": article.get("article_id", ""),
            "version": article.get("version", ""),
            "endpoint_types": endpoint_types_str,
            "fix_ids": ",".join(article.get("fix_ids", [])),
            "chunk_index": i,
            "total_chunks": len(chunks),
            "content_hash": article.get("content_hash", ""),
            "indexed_at": datetime.utcnow().isoformat(),
        })

    try:
        existing = collection.get(where={"url": article["url"]})
        if existing and existing['ids']:
            collection.delete(ids=existing['ids'])

        collection.add(ids=ids, documents=documents, metadatas=metadatas)
        return len(chunks)
    except Exception as e:
        console.print(f"[red]Error embedding release note: {e}[/red]")
        return 0


class ScraperStats:
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
                'total_chunks': self.total_chunks,
            }


def fetch_worker(articles, article_queue, stats, stop_event):
    for i, info in enumerate(articles):
        if stop_event.is_set():
            break
        url = info["url"]
        logger.info(f"[{i+1}/{len(articles)}] Fetching: {url}")
        try:
            article = fetch_and_parse_release_note(url)
            if article:
                article['discovered_title'] = info.get("title", "")
                article_queue.put(article)
                stats.add_fetch_success()
                logger.info(f"[{i+1}/{len(articles)}] OK: {article.get('title', '')[:60]}")
            else:
                stats.add_fetch_failure()
                mark_article_failed(url, "fetch_failed")
        except Exception as e:
            stats.add_fetch_failure()
            mark_article_failed(url, f"fetch_error: {str(e)[:100]}")
            logger.error(f"[{i+1}/{len(articles)}] ERROR: {e}")

        if i < len(articles) - 1 and not stop_event.is_set():
            time.sleep(CRAWL_DELAY_SECONDS)

    article_queue.put(None)


def embed_worker(article_queue, stats, stop_event, total):
    processed = 0
    while not stop_event.is_set():
        try:
            article = article_queue.get(timeout=1.0)
            if article is None:
                break
            processed += 1
            title = article.get("title", "Untitled")
            url = article.get("url", "")
            try:
                chunks = embed_release_note(article)
                if chunks > 0:
                    add_or_update_article(
                        url=url, title=title,
                        source="release_notes",
                        article_id=article.get("article_id"),
                        content_hash=article.get("content_hash"),
                        content_length=article.get("content_length", 0),
                        chunks_count=chunks, status="indexed",
                    )
                    stats.add_embed_success(chunks)
                else:
                    mark_article_failed(url, "embed_no_chunks")
                    stats.add_embed_failure()
            except Exception as e:
                mark_article_failed(url, f"embed_error: {str(e)[:100]}")
                stats.add_embed_failure()
                logger.error(f"Embed error: {e}")
            article_queue.task_done()
        except queue.Empty:
            continue


def show_stats():
    collection = _get_rn_collection()
    count = collection.count()
    table = Table(title="Release Notes Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Collection", COLLECTION_NAME)
    table.add_row("ChromaDB Chunks", str(count))
    console.print(table)


def run_scrape_mode(skip_existing: bool = True):
    init_kb_tables()

    console.print(Panel.fit(
        "[bold blue]Qlik Replicate Release Notes Scraper[/bold blue]\n"
        f"Log file: {LOG_FILE}",
        title="Scrape Mode",
    ))

    console.print("\n[bold]Step 1: Discovering release note articles...[/bold]")
    articles = discover_release_notes()
    if not articles:
        return

    if skip_existing:
        indexed_urls = get_indexed_urls()
        original = len(articles)
        articles = [a for a in articles if a["url"] not in indexed_urls]
        skipped = original - len(articles)
        if skipped:
            console.print(f"[dim]Skipping {skipped} already indexed[/dim]")

    if not articles:
        console.print("[green]All release notes already indexed.[/green]")
        return

    console.print(f"\n[bold]Found {len(articles)} release notes to process[/bold]")
    if not Confirm.ask("[yellow]Proceed?[/yellow]"):
        return

    console.print("\n[bold]Step 2: Fetching and embedding...[/bold]")
    article_queue = queue.Queue(maxsize=50)
    stats = ScraperStats()
    stop_event = threading.Event()

    ft = threading.Thread(target=fetch_worker, args=(articles, article_queue, stats, stop_event))
    et = threading.Thread(target=embed_worker, args=(article_queue, stats, stop_event, len(articles)))
    ft.start()
    et.start()

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(), TimeRemainingColumn(), console=console,
    ) as progress:
        task = progress.add_task("Processing...", total=len(articles))
        try:
            while ft.is_alive() or et.is_alive():
                s = stats.get_stats()
                done = s['embedded'] + s['embed_failed']
                progress.update(task, completed=done,
                    description=f"Fetched: {s['fetched']} | Embedded: {s['embedded']} | Failed: {s['fetch_failed']+s['embed_failed']}")
                time.sleep(0.5)
            progress.update(task, completed=len(articles))
        except KeyboardInterrupt:
            stop_event.set()
            ft.join(timeout=5)
            et.join(timeout=5)

    ft.join()
    et.join()

    final = stats.get_stats()
    console.print(f"\n[bold green]Done![/bold green]  Embedded: {final['embedded']}, Chunks: {final['total_chunks']}, Failed: {final['fetch_failed']+final['embed_failed']}")
    show_stats()


def run_query_mode(query_text: str, n_results: int = 5):
    collection = _get_rn_collection()
    results = collection.query(query_texts=[query_text], n_results=n_results)
    if not results or not results['documents'] or not results['documents'][0]:
        console.print("[yellow]No results found[/yellow]")
        return

    console.print(f"\n[bold]Found {len(results['documents'][0])} results:[/bold]\n")
    for i, doc in enumerate(results['documents'][0], 1):
        meta = results['metadatas'][0][i - 1] if results['metadatas'] else {}
        dist = results['distances'][0][i - 1] if results.get('distances') else 0
        sim = max(0, 1 - dist) * 100
        console.print(f"[bold cyan]Result {i}[/bold cyan] (similarity: {sim:.1f}%)")
        console.print(f"  [bold]Title:[/bold] {meta.get('title', 'Unknown')}")
        console.print(f"  [bold]Version:[/bold] {meta.get('version', 'N/A')}")
        console.print(f"  [bold]Endpoints:[/bold] {meta.get('endpoint_types', 'N/A')}")
        console.print(f"  [bold]URL:[/bold] {meta.get('url', 'N/A')}")
        preview = doc[:300] + "..." if len(doc) > 300 else doc
        console.print(f"  [dim]{preview}[/dim]\n")


def main():
    init_kb_tables()

    parser = argparse.ArgumentParser(description="Qlik Replicate Release Notes Loader")
    parser.add_argument("--mode", "-m", choices=["scrape", "query"])
    parser.add_argument("--query", "-q", help="Search query")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--no-skip", action="store_true")
    args = parser.parse_args()

    if args.stats:
        show_stats()
    elif args.mode == "scrape":
        run_scrape_mode(skip_existing=not args.no_skip)
    elif args.mode == "query":
        if not args.query:
            console.print("[red]--query required[/red]")
            sys.exit(1)
        run_query_mode(args.query)
    else:
        console.print(Panel.fit("[bold]Release Notes Loader[/bold]\nUse --mode scrape or --mode query"))
        show_stats()


if __name__ == "__main__":
    main()
