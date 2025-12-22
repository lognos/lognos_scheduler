import sqlite3
import os
import shutil
from datetime import datetime
from contextlib import ContextDecorator
from backend.config.settings import settings
import logfire

class SafeP6Transaction(ContextDecorator):
    """
    A context manager that implements a safe Copy-Modify-Check-Replace workflow for SQLite.
    
    Usage:
        with SafeP6Transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(...)
            conn.commit()
    
    Workflow:
    1. Copies the live DB to a temporary file.
    2. Yields a connection to the temporary file.
    3. On exit (if no errors AND modifications were made):
       a. Checks integrity of the temporary file.
       b. Moves the original DB to a 'superseded' subfolder with a timestamp.
       c. Moves the temporary file to the original location.
    
    Note: Call mark_modified() to signal that changes were made.
    If no modifications are marked, the temp file is discarded without backup.
    """
    def __init__(self):
        self.original_db_path = settings.P6_DB_LOC
        # Create temp file in the same directory to ensure atomic moves (if on same filesystem)
        # or at least to avoid cross-device link errors if possible, though shutil handles it.
        # Using a unique name.
        self.temp_db_path = f"{self.original_db_path}.temp_{int(datetime.now().timestamp())}.db"
        self.conn = None
        self._modified = False  # Track whether any modifications were made
    
    def mark_modified(self):
        """Mark that the database has been modified and should be saved."""
        self._modified = True

    def __enter__(self):
        # 1. Copy original to temp
        if not os.path.exists(self.original_db_path):
             raise FileNotFoundError(f"Database not found at {self.original_db_path}")
        
        try:
            shutil.copy2(self.original_db_path, self.temp_db_path)
        except Exception as e:
            logfire.error(f"Failed to copy database to temp: {e}")
            raise

        # 2. Connect to temp
        self.conn = sqlite3.connect(self.temp_db_path)
        return self  # Return self so caller can access both conn and mark_modified()

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            # An error occurred in the code block, discard temp
            logfire.warn(f"Exception during DB operation: {exc_value}. Discarding changes.")
            if self.conn:
                self.conn.close()
            self._cleanup_temp()
            return False # Propagate exception

        # Close connection (commit any pending transactions)
        try:
            if self.conn:
                self.conn.commit()
                self.conn.close()
        except Exception as e:
            logfire.error(f"Failed to commit/close temp DB: {e}")
            self._cleanup_temp()
            raise

        # If no modifications were made, just discard the temp file
        if not self._modified:
            logfire.debug("No modifications made during transaction. Discarding temp file.")
            self._cleanup_temp()
            return True

        # Modifications were made - proceed with backup and replace
        
        # 3. Check Integrity
        if not self._check_integrity():
            logfire.error("Database integrity check failed on modified temporary file. Operation aborted.")
            self._cleanup_temp()
            raise RuntimeError("Database integrity check failed on modified temporary file. Operation aborted.")

        # 4. Backup and Replace
        try:
            self._backup_original()
            shutil.move(self.temp_db_path, self.original_db_path)
            logfire.info(f"Successfully updated database. Original backed up to superseded folder.")
        except Exception as e:
            logfire.error(f"Failed to swap database files: {e}")
            self._cleanup_temp()
            raise RuntimeError(f"Failed to swap database files: {e}")

        return True

    def _check_integrity(self) -> bool:
        try:
            conn = sqlite3.connect(self.temp_db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            result = cursor.fetchone()
            conn.close()
            return result and result[0] == "ok"
        except Exception as e:
            logfire.error(f"Integrity check exception: {e}")
            return False

    def _backup_original(self):
        db_dir = os.path.dirname(self.original_db_path)
        db_name = os.path.basename(self.original_db_path)
        superseded_dir = os.path.join(db_dir, "superseded")
        
        os.makedirs(superseded_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # e.g. PPMDBSQLite.db_20251120_143000
        backup_name = f"{db_name}_{timestamp}"
        backup_path = os.path.join(superseded_dir, backup_name)
        
        # Move original to backup
        shutil.move(self.original_db_path, backup_path)

    def _cleanup_temp(self):
        if os.path.exists(self.temp_db_path):
            try:
                os.remove(self.temp_db_path)
            except Exception as e:
                logfire.warn(f"Failed to cleanup temp file: {e}")
