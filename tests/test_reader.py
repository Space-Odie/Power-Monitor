#!/usr/bin/env python3
"""
test_reader.py — Unit tests for reader.py SerialReader class.

Tests the serial reading, parsing, buffering, and database flushing logic
without requiring actual hardware.
"""

import unittest
import tempfile
import shutil
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from io import StringIO
import sys

from reader import SerialReader
from logger import DataLogger


class MockSerialPort:
    """Mock serial.Serial for testing without hardware."""
    
    def __init__(self, lines):
        """
        Args:
            lines: List of strings to return on readline() calls
        """
        self.lines = lines
        self.index = 0
        self.is_open = True
    
    def readline(self):
        """Return next mocked line."""
        if self.index >= len(self.lines):
            return b""  # Return empty when done
        line = self.lines[self.index]
        self.index += 1
        return line.encode("utf-8")
    
    def close(self):
        """Mock close."""
        self.is_open = False


class TestSerialReaderParsing(unittest.TestCase):
    """Test serial line parsing logic."""
    
    def setUp(self):
        """Create reader instance for testing."""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_readings.db")
        
        # Create reader with test database
        self.reader = SerialReader(port="/dev/null", baud=38400)
        self.reader.logger_db = DataLogger(self.db_path)
    
    def tearDown(self):
        """Clean up test database."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_parse_valid_line(self):
        """Test parsing a valid RPICT3V1 format line."""
        # Format: V1 V2 V3 I1 I2 I3 (I1 = RMS current at index 3)
        line = "120.5 120.3 120.2 45.2 5.1 4.8"
        amps = self.reader.parse_line(line)
        self.assertEqual(amps, 45.2)
    
    def test_parse_with_decimal_precision(self):
        """Test parsing preserves decimal precision."""
        line = "120.0 120.0 120.0 45.12345 5.0 4.0"
        amps = self.reader.parse_line(line)
        self.assertAlmostEqual(amps, 45.12345, places=5)
    
    def test_parse_zero_current(self):
        """Test parsing zero current (valid)."""
        line = "120.0 120.0 120.0 0.0 0.0 0.0"
        amps = self.reader.parse_line(line)
        self.assertEqual(amps, 0.0)
    
    def test_parse_high_current(self):
        """Test parsing high current values."""
        line = "120.0 120.0 120.0 100.5 2.0 1.5"
        amps = self.reader.parse_line(line)
        self.assertEqual(amps, 100.5)
    
    def test_parse_invalid_line_too_few_tokens(self):
        """Test parsing line with too few tokens."""
        line = "120.0 120.0"  # Missing tokens
        amps = self.reader.parse_line(line)
        self.assertIsNone(amps)
    
    def test_parse_invalid_line_non_numeric(self):
        """Test parsing line with non-numeric values."""
        line = "120.0 120.0 120.0 INVALID 5.0 4.0"
        amps = self.reader.parse_line(line)
        self.assertIsNone(amps)
    
    def test_parse_empty_line(self):
        """Test parsing empty line."""
        line = ""
        amps = self.reader.parse_line(line)
        self.assertIsNone(amps)
    
    def test_parse_with_whitespace(self):
        """Test parsing with extra whitespace."""
        line = "  120.0   120.0   120.0   45.2   5.1   4.8  "
        amps = self.reader.parse_line(line)
        self.assertEqual(amps, 45.2)


class TestSerialReaderBuffering(unittest.TestCase):
    """Test buffering and flush logic."""
    
    def setUp(self):
        """Create reader with test database."""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_readings.db")
        
        self.reader = SerialReader(
            port="/dev/null",
            baud=38400,
            buffer_size=5,  # Small buffer for testing
            flush_interval=10
        )
        self.reader.logger_db = DataLogger(self.db_path)
    
    def tearDown(self):
        """Clean up."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_buffer_accumulates(self):
        """Test that buffer accumulates readings."""
        self.reader.buffer.append(("2026-04-12T10:30:45-07:00", 45.2))
        self.reader.buffer.append(("2026-04-12T10:30:46-07:00", 45.5))
        
        self.assertEqual(len(self.reader.buffer), 2)
    
    def test_should_flush_on_buffer_full(self):
        """Test that flush is triggered when buffer reaches size limit."""
        # Fill buffer to size limit
        for i in range(5):
            self.reader.buffer.append((f"2026-04-12T10:30:{30+i}-07:00", 45.0 + i))
        
        should_flush = self.reader._should_flush()
        self.assertTrue(should_flush)
    
    def test_should_not_flush_on_small_buffer(self):
        """Test that flush is not triggered with small buffer."""
        self.reader.buffer.append(("2026-04-12T10:30:45-07:00", 45.2))
        
        should_flush = self.reader._should_flush()
        self.assertFalse(should_flush)
    
    def test_flush_clears_buffer(self):
        """Test that flush empties the buffer."""
        self.reader.buffer.append(("2026-04-12T10:30:45-07:00", 45.2))
        self.reader.buffer.append(("2026-04-12T10:30:46-07:00", 45.5))
        
        self.reader.flush()
        
        self.assertEqual(len(self.reader.buffer), 0)
    
    def test_flush_writes_to_database(self):
        """Test that flush actually writes data to database."""
        data = [
            ("2026-04-12T10:30:45-07:00", 45.2),
            ("2026-04-12T10:30:46-07:00", 45.5),
        ]
        self.reader.buffer.extend(data)
        
        self.reader.flush()
        
        # Verify data is in database
        rows = self.reader.logger_db.query_all(limit=10)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][1], 45.5)  # DESC order
    
    def test_flush_empty_buffer(self):
        """Test flush with empty buffer does nothing."""
        self.reader.flush()  # Should not raise error
        
        count = self.reader.logger_db.get_row_count()
        self.assertEqual(count, 0)


class TestSerialReaderIntegration(unittest.TestCase):
    """Integration tests for serial reading workflow."""
    
    def setUp(self):
        """Create reader for integration testing."""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_readings.db")
        
        self.reader = SerialReader(
            port="/dev/null",
            baud=38400,
            buffer_size=3,
            flush_interval=10
        )
        self.reader.logger_db = DataLogger(self.db_path)
    
    def tearDown(self):
        """Clean up."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_parse_and_buffer_workflow(self):
        """Test the full parse-to-buffer workflow."""
        raw_lines = [
            "120.5 120.3 120.2 45.2 5.1 4.8",
            "120.4 120.3 120.1 45.5 5.0 4.9",
        ]
        
        for raw_line in raw_lines:
            amps = self.reader.parse_line(raw_line)
            if amps is not None:
                timestamp = datetime.now(self.reader.tz).isoformat()
                self.reader.buffer.append((timestamp, amps))
        
        self.assertEqual(len(self.reader.buffer), 2)
        
        # Flush to database
        self.reader.flush()
        
        # Verify in database
        rows = self.reader.logger_db.query_all(limit=10)
        self.assertEqual(len(rows), 2)
    
    def test_auto_flush_on_buffer_full(self):
        """Test that auto-flush triggers when buffer size exceeded."""
        # Add readings until buffer should flush
        for i in range(3):
            self.reader.buffer.append((f"2026-04-12T10:30:{30+i}-07:00", 45.0 + i))
        
        # Check that we should flush
        self.assertTrue(self.reader._should_flush())
        
        # Do the flush
        self.reader.flush()
        
        # Buffer should be empty, data in DB
        self.assertEqual(len(self.reader.buffer), 0)
        self.assertEqual(self.reader.logger_db.get_row_count(), 3)


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestSerialReaderParsing))
    suite.addTests(loader.loadTestsFromTestCase(TestSerialReaderBuffering))
    suite.addTests(loader.loadTestsFromTestCase(TestSerialReaderIntegration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    exit(run_tests())
