#!/usr/bin/env python3
"""
init_db.py — Initialize database and directory structure.

Creates necessary directories (data/, reports/, backups/) and initializes
the SQLite database schema. Safe to run multiple times (idempotent).

Usage:
    python3 init_db.py                  # Use defaults
    python3 init_db.py --db-path custom_db.db
    python3 init_db.py --check          # Verify setup only

Configuration:
    Edit main() to customize paths or schema initialization.
"""

import os
import sys
import argparse
from logger import DataLogger


# Default directory structure
DEFAULT_DIRS = {
    "data": "SQLite database files",
    "reports": "Chart PNG files and analysis reports",
    "backups": "Database backups and archives"
}


def create_directories(base_path="."):
    """
    Create required directories if they don't exist.
    
    Args:
        base_path: Root directory for creating subdirectories
        
    Returns:
        dict: Mapping of directory -> full path
    """
    created = {}
    
    for dirname, description in DEFAULT_DIRS.items():
        dirpath = os.path.join(base_path, dirname)
        
        if not os.path.exists(dirpath):
            try:
                os.makedirs(dirpath, mode=0o755, exist_ok=True)
                print(f"✓ Created directory: {dirpath}")
                created[dirname] = dirpath
            except OSError as e:
                print(f"✗ Failed to create {dirname}: {e}", file=sys.stderr)
                return None
        else:
            print(f"  Directory exists: {dirpath}")
            created[dirname] = dirpath
    
    return created


def initialize_database(db_path="data/readings.db"):
    """
    Initialize SQLite database with schema.
    
    Creates readings table with proper indexes if it doesn't exist.
    Safe to call multiple times (uses CREATE TABLE IF NOT EXISTS).
    
    Args:
        db_path: Path to database file
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # DataLogger will create the table automatically on first insert
        # But we can verify it's readable
        logger_db = DataLogger(db_path)
        
        # Test basic operations
        row_count = logger_db.get_row_count()
        print(f"✓ Database initialized: {db_path}")
        print(f"  Current rows: {row_count}")
        
        # Verify integrity
        integrity_ok = logger_db.integrity_check()
        if integrity_ok:
            print(f"✓ Database integrity check passed")
            return True
        else:
            print(f"✗ Database integrity check failed", file=sys.stderr)
            return False
    
    except Exception as e:
        print(f"✗ Failed to initialize database: {e}", file=sys.stderr)
        return False


def verify_setup(base_path=".", db_path="data/readings.db"):
    """
    Verify that all required directories and database exist.
    
    Args:
        base_path: Root directory to check
        db_path: Path to database file
        
    Returns:
        bool: True if all checks pass
    """
    all_ok = True
    
    print("\nVerifying setup...\n")
    
    # Check directories
    for dirname in DEFAULT_DIRS.keys():
        dirpath = os.path.join(base_path, dirname)
        exists = os.path.isdir(dirpath)
        status = "✓" if exists else "✗"
        print(f"{status} {dirname}/ → {dirpath}")
        if not exists:
            all_ok = False
    
    # Check database
    db_exists = os.path.exists(db_path)
    status = "✓" if db_exists else "✗"
    print(f"{status} {db_path}")
    if not db_exists:
        all_ok = False
    
    return all_ok


def main():
    """Initialize database and directories."""
    parser = argparse.ArgumentParser(
        description="Initialize EV Monitor database and directory structure"
    )
    parser.add_argument(
        "--db-path",
        default="data/readings.db",
        help="Path to SQLite database (default: data/readings.db)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify setup without making changes"
    )
    parser.add_argument(
        "--base-path",
        default=".",
        help="Base directory for creating subdirectories (default: .)"
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("EV MONITOR - Database & Directory Initialization")
    print("=" * 70 + "\n")
    
    # If check-only mode, just verify
    if args.check:
        success = verify_setup(args.base_path, args.db_path)
        print()
        if success:
            print("✓ All checks passed!")
            return 0
        else:
            print("✗ Setup incomplete - run without --check to initialize")
            return 1
    
    # Create directories
    print("Creating directories...\n")
    dirs = create_directories(args.base_path)
    if dirs is None:
        return 1
    
    print()
    
    # Initialize database
    print("Initializing database...\n")
    if not initialize_database(args.db_path):
        return 1
    
    print()
    
    # Verify complete setup
    if verify_setup(args.base_path, args.db_path):
        print("\n✓ Initialization complete!")
        print("\nNext steps:")
        print("  1. Run unit tests:")
        print("     python3 test_logger.py")
        print("     python3 test_reader.py")
        print("  2. Install dependencies:")
        print("     pip install -r requirements.txt")
        print("  3. On Raspberry Pi, run the daemon:")
        print("     python3 reader.py")
        print("  4. Generate charts:")
        print("     python3 plotter.py --days 30")
        return 0
    else:
        print("\n✗ Setup verification failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
