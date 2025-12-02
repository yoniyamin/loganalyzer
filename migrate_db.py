"""
Database migration script to add line_number column to performance table.

Run this script before starting the application after updating the code.
"""

import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "log_analyzer.db")

def migrate():
    if not os.path.exists(DB_PATH):
        print("Database doesn't exist yet. Will be created on first run.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if line_number column already exists
        cursor.execute("PRAGMA table_info(performance)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'line_number' not in columns:
            print("Adding line_number column to performance table...")
            cursor.execute("ALTER TABLE performance ADD COLUMN line_number INTEGER")
            conn.commit()
            print("✓ Migration completed successfully!")
            print("\nNOTE: Existing performance data will not have line numbers.")
            print("      Please re-index your log files to populate line numbers.")
        else:
            print("✓ Database is already up to date!")
            
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Log Analyzer Database Migration")
    print("=" * 60)
    migrate()
    print("=" * 60)

