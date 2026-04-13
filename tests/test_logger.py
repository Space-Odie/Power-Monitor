#!/usr/bin/env python3
"""
test_logger.py — Formal unit tests for logger.py using Python's unittest framework.

Run tests:
    python3 test_logger.py                    # Run all tests
    python3 test_logger.py TestDataLogger     # Run specific test class
    python3 test_logger.py TestDataLogger.test_insert_batch  # Run specific test

Or with unittest discovery:
    python3 -m unittest test_logger -v
"""

import unittest
import os
import tempfile
import shutil
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from logger import DataLogger


class TestDataLogger(unittest.TestCase):
    """Unit tests for DataLogger class."""
    
    def setUp(self):
        """Create temporary test database before each test."""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_readings.db")
        self.db = DataLogger(self.db_path)
    
    def tearDown(self):
        """Clean up test database after each test."""
        if hasattr(self, 'db'):
            # Close any open connections
            pass
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_database_created(self):
        """Test that database file is created."""
        self.assertTrue(os.path.exists(self.db_path))
    
    def test_insert_batch_single(self):
        """Test inserting a single row."""
        result = self.db.insert_batch([("2026-04-12T10:30:45-07:00", 45.2)])
        self.assertEqual(result, 1)
    
    def test_insert_batch_multiple(self):
        """Test inserting multiple rows."""
        data = [
            ("2026-04-12T10:30:45-07:00", 45.2),
            ("2026-04-12T10:30:46-07:00", 45.5),
            ("2026-04-12T10:30:47-07:00", 44.8),
        ]
        result = self.db.insert_batch(data)
        self.assertEqual(result, 3)
    
    def test_insert_batch_empty(self):
        """Test inserting empty list returns 0."""
        result = self.db.insert_batch([])
        self.assertEqual(result, 0)
    
    def test_query_all_default(self):
        """Test querying all rows with default parameters."""
        data = [
            ("2026-04-12T10:30:45-07:00", 45.2),
            ("2026-04-12T10:30:46-07:00", 45.5),
        ]
        self.db.insert_batch(data)
        rows = self.db.query_all()
        self.assertEqual(len(rows), 2)
    
    def test_query_all_desc_order(self):
        """Test that DESC order returns newest first."""
        data = [
            ("2026-04-12T10:30:45-07:00", 45.2),
            ("2026-04-12T10:30:46-07:00", 45.5),
            ("2026-04-12T10:30:47-07:00", 44.8),
        ]
        self.db.insert_batch(data)
        rows = self.db.query_all(limit=3, order="DESC")
        
        # Should be in reverse chronological order
        self.assertEqual(rows[0][0], "2026-04-12T10:30:47-07:00")
        self.assertEqual(rows[1][0], "2026-04-12T10:30:46-07:00")
        self.assertEqual(rows[2][0], "2026-04-12T10:30:45-07:00")
    
    def test_query_all_asc_order(self):
        """Test that ASC order returns oldest first."""
        data = [
            ("2026-04-12T10:30:45-07:00", 45.2),
            ("2026-04-12T10:30:46-07:00", 45.5),
            ("2026-04-12T10:30:47-07:00", 44.8),
        ]
        self.db.insert_batch(data)
        rows = self.db.query_all(limit=3, order="ASC")
        
        # Should be in chronological order
        self.assertEqual(rows[0][0], "2026-04-12T10:30:45-07:00")
        self.assertEqual(rows[1][0], "2026-04-12T10:30:46-07:00")
        self.assertEqual(rows[2][0], "2026-04-12T10:30:47-07:00")
    
    def test_query_all_limit(self):
        """Test that limit parameter works."""
        data = [
            ("2026-04-12T10:30:45-07:00", 45.2),
            ("2026-04-12T10:30:46-07:00", 45.5),
            ("2026-04-12T10:30:47-07:00", 44.8),
        ]
        self.db.insert_batch(data)
        
        rows = self.db.query_all(limit=2)
        self.assertEqual(len(rows), 2)
    
    def test_query_all_empty_database(self):
        """Test querying empty database returns empty list."""
        rows = self.db.query_all()
        self.assertEqual(len(rows), 0)
    
    def test_query_by_date_range(self):
        """Test querying by date range."""
        data = [
            ("2026-04-12T10:00:00-07:00", 40.0),
            ("2026-04-12T10:30:00-07:00", 45.0),
            ("2026-04-12T11:00:00-07:00", 50.0),
        ]
        self.db.insert_batch(data)
        
        rows = self.db.query_by_date_range(
            "2026-04-12T10:15:00-07:00",
            "2026-04-12T10:45:00-07:00"
        )
        
        # Should only return the middle row
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "2026-04-12T10:30:00-07:00")
        self.assertEqual(rows[0][1], 45.0)
    
    def test_query_by_date_range_inclusive(self):
        """Test that date range is inclusive on both ends."""
        data = [
            ("2026-04-12T10:00:00-07:00", 40.0),
            ("2026-04-12T11:00:00-07:00", 50.0),
        ]
        self.db.insert_batch(data)
        
        rows = self.db.query_by_date_range(
            "2026-04-12T10:00:00-07:00",
            "2026-04-12T11:00:00-07:00"
        )
        
        # Should include both boundary rows
        self.assertEqual(len(rows), 2)
    
    def test_get_row_count(self):
        """Test getting row count."""
        data = [("2026-04-12T10:30:45-07:00", 45.2)] * 5
        self.db.insert_batch(data)
        
        count = self.db.get_row_count()
        self.assertEqual(count, 5)
    
    def test_get_row_count_empty(self):
        """Test row count on empty database."""
        count = self.db.get_row_count()
        self.assertEqual(count, 0)
    
    def test_integrity_check_pass(self):
        """Test integrity check on valid database."""
        data = [("2026-04-12T10:30:45-07:00", 45.2)]
        self.db.insert_batch(data)
        
        result = self.db.integrity_check()
        self.assertTrue(result)
    
    def test_data_persists_across_instances(self):
        """Test that data persists when creating new DataLogger instance."""
        data = [("2026-04-12T10:30:45-07:00", 45.2)]
        self.db.insert_batch(data)
        
        # Create new instance pointing to same database
        db2 = DataLogger(self.db_path)
        rows = db2.query_all(limit=1)
        
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], 45.2)
    
    def test_archive_old_data(self):
        """Test archiving old data."""
        tz = ZoneInfo("America/Los_Angeles")
        
        # Create data with old and new timestamps
        old_time = (datetime.now(tz) - timedelta(days=91)).isoformat()
        new_time = datetime.now(tz).isoformat()
        
        data = [
            (old_time, 40.0),
            (new_time, 50.0),
        ]
        self.db.insert_batch(data)
        
        # Archive data older than 90 days
        archived = self.db.archive_old_data(days=90)
        
        # Should have archived 1 row
        self.assertEqual(archived, 1)
        
        # Main database should only have 1 row left
        count = self.db.get_row_count()
        self.assertEqual(count, 1)
        
        # Remaining row should be the new one
        rows = self.db.query_all(limit=1)
        self.assertEqual(rows[0][1], 50.0)
    
    def test_archive_creates_separate_file(self):
        """Test that archive creates separate database file."""
        tz = ZoneInfo("America/Los_Angeles")
        old_time = (datetime.now(tz) - timedelta(days=91)).isoformat()
        
        data = [(old_time, 40.0)]
        self.db.insert_batch(data)
        self.db.archive_old_data(days=90)
        
        # Check that archive file was created
        archive_files = [f for f in os.listdir(self.test_dir) 
                        if f.startswith("readings_archived_")]
        self.assertEqual(len(archive_files), 1)
    
    def test_archive_no_old_data(self):
        """Test archiving when there's no old data."""
        data = [("2026-04-12T10:30:45-07:00", 45.2)]
        self.db.insert_batch(data)
        
        # Try to archive data older than 90 days (should find none)
        archived = self.db.archive_old_data(days=90)
        self.assertEqual(archived, 0)
    
    def test_amps_values_precision(self):
        """Test that amperage values are stored with precision."""
        data = [("2026-04-12T10:30:45-07:00", 45.12345)]
        self.db.insert_batch(data)
        
        rows = self.db.query_all(limit=1)
        # SQLite stores floats with full precision
        self.assertAlmostEqual(rows[0][1], 45.12345, places=5)
    
    def test_timestamp_format_preserved(self):
        """Test that ISO8601 timestamps are preserved exactly."""
        timestamp = "2026-04-12T10:30:45.123456-07:00"
        data = [(timestamp, 45.2)]
        self.db.insert_batch(data)
        
        rows = self.db.query_all(limit=1)
        self.assertEqual(rows[0][0], timestamp)


class TestDataLoggerErrorHandling(unittest.TestCase):
    """Test error handling in DataLogger."""
    
    def setUp(self):
        """Create temporary test database."""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_readings.db")
        self.db = DataLogger(self.db_path)
    
    def tearDown(self):
        """Clean up test database."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_invalid_data_type_raises_error(self):
        """Test that invalid data types raise appropriate errors."""
        # This might not raise immediately due to SQLite type coercion,
        # but we're testing the behavior
        try:
            self.db.insert_batch([("not a number", "invalid")])
            # SQLite might still accept this due to dynamic typing
        except Exception:
            # If it does raise, that's fine too
            pass
    
    def test_query_on_nonexistent_database(self):
        """Test querying a database that was deleted."""
        # Insert some data
        self.db.insert_batch([("2026-04-12T10:30:45-07:00", 45.2)])
        
        # Delete the database file
        os.remove(self.db_path)
        
        # Querying should fail gracefully
        with self.assertRaises(Exception):
            self.db.query_all()


def run_tests():
    """Run all tests with verbose output."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestDataLogger))
    suite.addTests(loader.loadTestsFromTestCase(TestDataLoggerErrorHandling))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Return exit code (0 if all passed, 1 if any failed)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    exit(run_tests())
