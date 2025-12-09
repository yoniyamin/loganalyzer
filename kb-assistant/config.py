"""
Configuration settings for KB Scraper CLI.
"""
import os
from pathlib import Path

# Base paths
PROJECT_ROOT = Path(__file__).parent.parent
KB_ASSISTANT_ROOT = Path(__file__).parent

# ChromaDB path - shared with main log_analyzer
CHROMA_PERSIST_DIR = os.environ.get(
    "CHROMA_PERSIST_DIR",
    str(PROJECT_ROOT / "chroma_db")
)

# KB collection name
KB_COLLECTION_NAME = "qlik_replicate_kb"

# Data paths
DATA_DIR = PROJECT_ROOT / "data"
KB_REGISTRY_PATH = DATA_DIR / "kb_registry.jsonl"  # Legacy, now using SQLite

# Main app database (shared with log_analyzer)
DB_PATH = PROJECT_ROOT / "log_analyzer.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Sitemap settings (fallback)
QLIK_COMMUNITY_SITEMAP_ROOT = "https://community.qlik.com/sitemap.xml"

# Direct KB listing page for Qlik Replicate articles (~921 articles)
QLIK_REPLICATE_KB_URL = "https://community.qlik.com/t5/b-qlik-support-knowledge-base/Qlik+Replicate/pd-p/qlikReplicate"

# API endpoint for fetching article list (Lithium/Khoros API)
QLIK_KB_API_URL = "https://community.qlik.com/api/2.0/search"

# URL patterns to filter for Qlik Replicate KB articles
KB_URL_PATTERNS = [
    "/t5/Official-Support-Articles/",
    "/t5/Knowledge/",
    "/ta-p/",  # Article pages (e.g., /ta-p/2538166)
]

# Keywords to identify Replicate-related articles
REPLICATE_KEYWORDS = [
    "replicate",
    "qlik replicate",
    "attunity",
    "cdc",
    "change data capture",
]

# Crawl settings
CRAWL_DELAY_SECONDS = 5  # Polite delay between requests
REQUEST_TIMEOUT = 30  # Seconds
MAX_RETRIES = 3

# User agent for requests
USER_AGENT = "QlikReplicateKBScraper/1.0 (Knowledge Base Builder)"

# Chunking settings for embeddings
CHUNK_SIZE = 500  # Approximate tokens per chunk
CHUNK_OVERLAP = 50  # Overlap between chunks

# Embedding settings
# Using ChromaDB's default local embeddings (all-MiniLM-L6-v2)
# No API key required
