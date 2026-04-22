"""
pytest configuration for EV Monitor tests.

Adds parent directory to path so tests can import core modules.
"""

import sys
import os

# Add parent directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
