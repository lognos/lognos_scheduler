import sqlite3
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from backend.config.settings import settings

def check_embeddings():
    db_path = settings.P6_DB_LOC
    print(f"Checking database at: {db_path}")
    
    if not os.path.exists(db_path):
        print("Database file not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='TASK_EMBEDDINGS'")
    if not cursor.fetchone():
        print("TASK_EMBEDDINGS table does not exist.")
        conn.close()
        return

    # Count rows
    cursor.execute("SELECT COUNT(*) FROM TASK_EMBEDDINGS")
    count = cursor.fetchone()[0]
    print(f"TASK_EMBEDDINGS row count: {count}")
    
    if count > 0:
        # Show breakdown by project
        print("\nBreakdown by Project:")
        cursor.execute("SELECT PROJ_ID, COUNT(*) FROM TASK_EMBEDDINGS GROUP BY PROJ_ID")
        for row in cursor.fetchall():
            print(f"Project {row[0]}: {row[1]} embeddings")

    conn.close()

if __name__ == "__main__":
    check_embeddings()
