#!/usr/bin/env python3
"""
logger.py — SQLite database wrapper for power monitoring data.

Provides DataLogger class for managing power consumption readings:
- Creates and initializes SQLite database with WAL journaling
- Handles batch inserts for efficiency
- Queries data with filtering and ordering
- Archives old data to separate databases
- Uses PRAGMA synchronous=NORMAL for balanced durability on flash storage

Usage:
    from logger import DataLogger
    
    db = DataLogger("data/readings.db")
    db.insert_batch([
        ("2026-04-12T10:30:45-07:00", 45.2),
        ("2026-04-12T10:30:46-07:00", 45.5),
    ])
    
    rows = db.query_all(limit=10)
    print(rows)
"""

import sqlite3
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

logger = logging.getLogger(__name__)


class DataLogger:
    """SQLite database wrapper for power consumption readings."""
    
    def __init__(self, db_path="data/readings.db"):
        """
        Initialize database connection and create schema if needed.
        
        Args:
            db_path: Path to SQLite database file (default: data/readings.db)
        """
        self.db_path = db_path
        self.tz = ZoneInfo("America/Los_Angeles")
        
        # Create directory if it doesn't exist
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._init_db()
    
    def _init_db(self):
        """Create database schema and enable WAL mode with synchronous=NORMAL."""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Enable WAL (Write-Ahead Logging) for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            
            # Use NORMAL synchronous mode: balance durability with performance
            # Max 1 second of data loss on sudden power loss; acceptable for monitoring
            conn.execute("PRAGMA synchronous=NORMAL")
            
            # Create readings table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    amps REAL NOT NULL
                )
            """)
            
            # Create index on timestamp for efficient queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON readings(timestamp)")
            
            conn.commit()
            conn.close()
            logger.info(f"Database initialized at {self.db_path}")
        
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def insert_batch(self, rows):
        """
        Insert batch of (timestamp, amps) tuples into database.
        
        Args:
            rows: List of (timestamp_str, amps_float) tuples
                  Example: [("2026-04-12T10:30:45-07:00", 45.2), ...]
        
        Returns:
            int: Number of rows inserted
        
        Raises:
            sqlite3.Error: If insert fails
        """
        if not rows:
            return 0
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.executemany(
                "INSERT INTO readings (timestamp, amps) VALUES (?, ?)",
                rows
            )
            conn.commit()
            conn.close()
            logger.debug(f"Inserted {len(rows)} rows")
            return len(rows)
        
        except sqlite3.Error as e:
            logger.error(f"Insert failed: {e}")
            raise
    
    def query_all(self, limit=100, order="DESC"):
        """
        Fetch readings from database.
        
        Args:
            limit: Maximum number of rows to return (default: 100)
            order: Sort order: "DESC" (newest first) or "ASC" (oldest first)
        
        Returns:
            List of (timestamp, amps) tuples
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                f"SELECT timestamp, amps FROM readings ORDER BY timestamp {order} LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            conn.close()
            return rows
        
        except sqlite3.Error as e:
            logger.error(f"Query failed: {e}")
            raise
    
    def query_by_date_range(self, start_timestamp, end_timestamp):
        """
        Fetch readings within a date range.
        
        Args:
            start_timestamp: ISO8601 timestamp string (inclusive)
            end_timestamp: ISO8601 timestamp string (inclusive)
        
        Returns:
            List of (timestamp, amps) tuples
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "SELECT timestamp, amps FROM readings WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp ASC",
                (start_timestamp, end_timestamp)
            )
            rows = cursor.fetchall()
            conn.close()
            return rows
        
        except sqlite3.Error as e:
            logger.error(f"Range query failed: {e}")
            raise
    
    def get_row_count(self):
        """Get total number of rows in database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute("SELECT COUNT(*) FROM readings")
            count = cursor.fetchone()[0]
            conn.close()
            return count
        
        except sqlite3.Error as e:
            logger.error(f"Count query failed: {e}")
            raise
    
    def archive_old_data(self, days=90):
        """
        Move readings older than N days to archived database.
        
        Creates separate database files named: readings_archived_YYYYMM.db
        
        Args:
            days: Move data older than this many days (default: 90)
        
        Returns:
            int: Number of rows archived
        """
        try:
            cutoff = (datetime.now(self.tz) - timedelta(days=days)).isoformat()
            
            conn = sqlite3.connect(self.db_path)
            
            # Fetch old rows
            old_rows = conn.execute(
                "SELECT * FROM readings WHERE timestamp < ?",
                (cutoff,)
            ).fetchall()
            
            if not old_rows:
                logger.info(f"No rows older than {days} days to archive")
                return 0
            
            # Create archive database with YYYYMM naming
            cutoff_dt = datetime.fromisoformat(cutoff)
            archive_name = f"readings_archived_{cutoff_dt.strftime('%Y%m')}.db"
            archive_path = os.path.join(os.path.dirname(self.db_path), archive_name)
            
            # Insert into archive
            archive_conn = sqlite3.connect(archive_path)
            archive_conn.execute("""
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    amps REAL NOT NULL
                )
            """)
            archive_conn.executemany(
                "INSERT OR IGNORE INTO readings VALUES (?, ?, ?)",
                old_rows
            )
            archive_conn.commit()
            archive_conn.close()
            
            # Delete from main database
            conn.execute("DELETE FROM readings WHERE timestamp < ?", (cutoff,))
            conn.commit()
            conn.close()
            
            logger.info(f"Archived {len(old_rows)} rows to {archive_name}")
            return len(old_rows)
        
        except sqlite3.Error as e:
            logger.error(f"Archive failed: {e}")
            raise
    
    def integrity_check(self):
        """
        Run SQLite integrity check.
        
        Returns:
            bool: True if OK, False if issues found
        """
        try:
            conn = sqlite3.connect(self.db_path)
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            conn.close()
            
            if result == "ok":
                logger.info("Database integrity check: OK")
                return True
            else:
                logger.error(f"Database integrity check failed: {result}")
                return False
        
        except sqlite3.Error as e:
            logger.error(f"Integrity check error: {e}")
            return False


def main():
    """Entry point — test database functionality."""
    logging.basicConfig(level=logging.INFO)
    
    # Create test database
    db = DataLogger("data/readings.db")
    
    # Test insert
    test_data = [
        ("2026-04-12T10:30:45-07:00", 45.2),
        ("2026-04-12T10:30:46-07:00", 45.5),
        ("2026-04-12T10:30:47-07:00", 44.8),
    ]
    
    db.insert_batch(test_data)
    print(f"✓ Inserted {len(test_data)} test rows")
    
    # Test query
    rows = db.query_all(limit=5)
    print(f"✓ Query returned {len(rows)} rows:")
    for ts, amps in rows:
        print(f"  {ts}: {amps:.1f}A")
    
    # Test row count
    count = db.get_row_count()
    print(f"✓ Total rows in database: {count}")
    
    # Test integrity check
    ok = db.integrity_check()
    print(f"✓ Integrity check: {'PASS' if ok else 'FAIL'}")
    
    print("\n✓ All tests passed!")


if __name__ == "__main__":
    main()
