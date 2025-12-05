"""
ChromaDB client for KB storage.
Shares the same ChromaDB path as the main log_analyzer.
"""
import os
from typing import Optional

import chromadb
from chromadb.config import Settings

from config import CHROMA_PERSIST_DIR, KB_COLLECTION_NAME


class KBChromaClient:
    """
    ChromaDB client for the Qlik Replicate KB collection.
    """
    
    _instance: Optional["KBChromaClient"] = None
    
    def __init__(self, persist_directory: Optional[str] = None):
        """
        Initialize the ChromaDB client.
        
        Args:
            persist_directory: Directory to persist ChromaDB data.
                             Defaults to shared chroma_db in project root.
        """
        self.persist_dir = persist_directory or CHROMA_PERSIST_DIR
        
        # Ensure directory exists
        os.makedirs(self.persist_dir, exist_ok=True)
        
        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Get or create the KB collection
        self.collection = self.client.get_or_create_collection(
            name=KB_COLLECTION_NAME,
            metadata={"description": "Qlik Replicate Knowledge Base articles"}
        )
    
    def get_collection(self):
        """Get the KB collection."""
        return self.collection
    
    def get_stats(self) -> dict:
        """Get collection statistics."""
        return {
            "collection_name": KB_COLLECTION_NAME,
            "document_count": self.collection.count(),
            "persist_directory": self.persist_dir
        }
    
    def clear_collection(self) -> int:
        """
        Clear all documents from the KB collection.
        
        Returns:
            Number of documents deleted.
        """
        count = self.collection.count()
        if count > 0:
            # Get all IDs and delete them
            all_docs = self.collection.get()
            if all_docs and all_docs['ids']:
                self.collection.delete(ids=all_docs['ids'])
        return count


def get_kb_client() -> KBChromaClient:
    """Get singleton KB ChromaDB client instance."""
    if KBChromaClient._instance is None:
        KBChromaClient._instance = KBChromaClient()
    return KBChromaClient._instance
