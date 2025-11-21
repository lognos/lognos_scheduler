import sqlite3
from contextlib import contextmanager
from typing import Generator
from backend.config.settings import settings

@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """
    Yields a synchronous SQLite connection to the P6 database.
    Ensures the connection is closed after use.
    """
    conn = sqlite3.connect(settings.P6_DB_LOC)
    # Enable row factory to access columns by name if needed, 
    # but for P6 we often stick to standard tuples or specific queries.
    # conn.row_factory = sqlite3.Row 
    try:
        yield conn
    finally:
        conn.close()
