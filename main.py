#!/usr/bin/env python3
"""
Main entry point script - demonstrates how to use the utilities.

For normal usage, run utilities directly:
    python3 util/init_db.py      - Initialize database
    python3 util/status.py       - Check system status
    python3 util/test_serial.py  - Test serial connection
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("""
EV Monitor - Power Consumption Monitoring System
================================================

Core Components:
  logger.py    - SQLite database management
  reader.py    - RPICT3V1 serial data acquisition  
  plotter.py   - Chart generation & analysis

Utilities (in util/ folder):
  init_db.py   - Database & directory setup
  status.py    - System health monitoring
  test_serial.py - Serial port diagnostics

Tests (in tests/ folder):
  test_logger.py - Database unit tests (22 tests)
  test_reader.py - Serial reader unit tests (16 tests)

Quick Start:
  1. python3 util/init_db.py          # Setup
  2. python3 -m pytest tests/          # Run tests
  3. python3 reader.py                # Start daemon
  4. python3 util/status.py           # Check status
  5. python3 plotter.py --days 30     # Generate charts

For help on any utility:
  python3 util/<script>.py --help
""")
