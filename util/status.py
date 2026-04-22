#!/usr/bin/env python3
"""
status.py — System health and uptime checker for power monitor daemon.

Displays current system status including:
  - Daemon uptime (if running under systemd)
  - Last database reading (timestamp and age)
  - Total readings collected
  - Database file size
  - Collection rate (readings per day)

Usage:
    python3 util/status.py                    # Show all status
    python3 util/status.py --json             # JSON output for integration
    python3 util/status.py --verbose          # Detailed output

Configuration:
    Edit main() to customize database path or output format.
"""

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from logger import DataLogger


# Configuration
DEFAULT_DB_PATH = "data/readings.db"
DEFAULT_TZ = "America/Los_Angeles"


class StatusChecker:
    """Check and report power monitor system health."""
    
    def __init__(self, db_path=DEFAULT_DB_PATH, tz=DEFAULT_TZ):
        """Initialize status checker."""
        self.db_path = db_path
        self.tz = ZoneInfo(tz)
        self.status = {}
    
    def get_database_info(self):
        """Get database statistics."""
        if not os.path.exists(self.db_path):
            return {"exists": False, "error": "Database not found"}
        
        try:
            db = DataLogger(self.db_path)
            total_rows = db.get_row_count()
            
            # Get file size in MB
            file_size_bytes = os.path.getsize(self.db_path)
            file_size_mb = file_size_bytes / (1024 * 1024)
            
            # Get last reading
            rows = db.query_all(limit=1)  # DESC order, so first is newest
            
            last_reading = None
            last_age_minutes = None
            
            if rows and len(rows[0]) >= 3:
                try:
                    row_id, timestamp_str, amps = rows[0]
                    last_reading = {
                        "timestamp": timestamp_str,
                        "amps": amps
                    }
                except (ValueError, TypeError):
                    pass
                
                # Calculate age
                try:
                    last_ts = datetime.fromisoformat(timestamp_str)
                    now = datetime.now(self.tz)
                    age = now - last_ts
                    last_age_minutes = age.total_seconds() / 60
                except Exception:
                    pass
            
            return {
                "exists": True,
                "path": os.path.abspath(self.db_path),
                "total_rows": total_rows,
                "file_size_mb": round(file_size_mb, 2),
                "file_size_bytes": file_size_bytes,
                "last_reading": last_reading,
                "last_age_minutes": last_age_minutes
            }
        
        except Exception as e:
            return {"exists": True, "error": str(e)}
    
    def get_daemon_status(self):
        """Get systemd daemon status if running under it."""
        try:
            # Check if systemd service exists
            result = subprocess.run(
                ["systemctl", "is-active", "power-monitor.service"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            is_active = result.returncode == 0
            
            if is_active:
                # Get uptime
                uptime_result = subprocess.run(
                    ["systemctl", "show", "power-monitor.service", "-p", "ActiveEnterTimestamp", "-p", "ExecMainStartTimestamp"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                return {
                    "active": True,
                    "status": result.stdout.strip(),
                    "uptime_info": uptime_result.stdout.strip()
                }
            else:
                return {
                    "active": False,
                    "status": result.stdout.strip() if result.stdout else "inactive"
                }
        
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # systemctl not available
            return {"active": None, "info": "systemd not available"}
        except Exception as e:
            return {"active": None, "error": str(e)}
    
    def calculate_collection_rate(self):
        """Estimate collection rate (samples per day)."""
        try:
            db = DataLogger(self.db_path)
            total_rows = db.get_row_count()
            
            if total_rows == 0:
                return None
            
            # Get oldest and newest timestamps
            rows_newest = db.query_all(limit=1)  # DESC
            rows_oldest = db.query_all(order="ASC", limit=1)
            
            if rows_newest and rows_oldest:
                _, newest_ts_str, _ = rows_newest[0]
                _, oldest_ts_str, _ = rows_oldest[0]
                
                newest_ts = datetime.fromisoformat(newest_ts_str)
                oldest_ts = datetime.fromisoformat(oldest_ts_str)
                
                time_span = newest_ts - oldest_ts
                days_elapsed = time_span.total_seconds() / (24 * 3600)
                
                if days_elapsed > 0:
                    samples_per_day = total_rows / days_elapsed
                    return round(samples_per_day, 1)
        
        except Exception:
            pass
        
        return None
    
    def check_all(self):
        """Run all status checks."""
        self.status = {
            "timestamp": datetime.now(self.tz).isoformat(),
            "database": self.get_database_info(),
            "daemon": self.get_daemon_status(),
            "collection_rate_samples_per_day": self.calculate_collection_rate()
        }
        return self.status
    
    def display_text(self, verbose=False):
        """Display status in human-readable format."""
        db_info = self.status.get("database", {})
        daemon_info = self.status.get("daemon", {})
        rate = self.status.get("collection_rate_samples_per_day")
        
        print("=" * 70)
        print("EV MONITOR SYSTEM STATUS")
        print("=" * 70)
        print(f"Check Time: {self.status.get('timestamp')}\n")
        
        # Database status
        print("DATABASE:")
        if db_info.get("exists"):
            if "error" in db_info:
                print(f"  ✗ Error: {db_info.get('error')}")
            else:
                print(f"  Path: {db_info.get('path')}")
                total = db_info.get('total_rows')
                if total is not None:
                    print(f"  Total readings: {total:,}")
                    print(f"  File size: {db_info.get('file_size_mb')} MB")
            
            last_reading = db_info.get("last_reading")
            if last_reading:
                amps = last_reading.get("amps")
                timestamp = last_reading.get("timestamp")
                age = db_info.get("last_age_minutes")
                
                print(f"  Last reading: {amps:.1f}A @ {timestamp}")
                
                if age is not None:
                    if age < 1:
                        age_str = f"{age * 60:.0f} seconds ago"
                    elif age < 60:
                        age_str = f"{age:.1f} minutes ago"
                    elif age < 1440:
                        age_str = f"{age / 60:.1f} hours ago"
                    else:
                        age_str = f"{age / 1440:.1f} days ago"
                    
                    print(f"  Last update: {age_str}")
            
            if rate:
                print(f"  Collection rate: {rate:.0f} samples/day (@ 1 Hz)")
        else:
            print("  ✗ Database not found")
        
        print()
        
        # Daemon status
        print("DAEMON:")
        if daemon_info.get("active") is True:
            print("  Status: ✓ RUNNING")
            print(f"  Service: {daemon_info.get('status')}")
        elif daemon_info.get("active") is False:
            print("  Status: ✗ NOT RUNNING")
            print("  To start:")
            print("    sudo systemctl start power-monitor.service")
        else:
            print("  Status: ? UNKNOWN (systemd not available)")
        
        print()
        
        # Health summary
        print("HEALTH:")
        if db_info.get("exists") and db_info.get("total_rows", 0) > 0:
            if daemon_info.get("active"):
                status_emoji = "✓"
                health = "OPERATIONAL"
            else:
                status_emoji = "⚠"
                health = "DATA COLLECTING (daemon not running)"
            print(f"  {status_emoji} {health}")
        else:
            print("  ✗ NOT OPERATIONAL (no data)")
        
        print("=" * 70 + "\n")
    
    def display_json(self):
        """Display status as JSON."""
        print(json.dumps(self.status, indent=2))


def main():
    """Check and display system status."""
    parser = argparse.ArgumentParser(description="Check EV Monitor system status")
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help=f"Database path (default: {DEFAULT_DB_PATH})"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    checker = StatusChecker(db_path=args.db)
    checker.check_all()
    
    if args.json:
        checker.display_json()
    else:
        checker.display_text(verbose=args.verbose)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
