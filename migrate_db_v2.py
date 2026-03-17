"""
Database migration script to add new tables for Performance Cockpit feature.
Run this after updating to the latest version.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.database import engine, Base, init_db

def migrate():
    """Create new tables if they don't exist."""
    print("Running database migration for Performance Cockpit tables...")
    
    # This will create any new tables that don't exist
    # Existing tables are left untouched
    Base.metadata.create_all(bind=engine)
    
    print("Migration complete! New tables created:")
    print("  - batches")
    print("  - sorter_events")
    print("  - file_operations")
    print("  - apply_events")
    print("  - table_stats")
    print("  - task_config")

if __name__ == "__main__":
    migrate()














