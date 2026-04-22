#!/usr/bin/env python3
"""
test_serial.py — Diagnostic tool to identify RPICT3V1 RMS current column.

Reads raw serial output from RPICT3V1 and displays columns with labels.
Run this on the Raspberry Pi to determine which column contains the RMS current
measurement needed by reader.py.

Usage (on Pi with RPICT3V1 connected):
    python3 util/test_serial.py                    # Use /dev/serial0, 20 samples
    python3 util/test_serial.py --port /dev/ttyAMA0
    python3 util/test_serial.py --count 100        # Read 100 samples
    python3 util/test_serial.py --timeout 30       # Read for 30 seconds

Common RPICT3V1 output formats:
    V1 V2 V3 I1 I2 I3        (RMS current at index 3 for phase 1)
    Other variants exist; this tool helps identify your format.
"""

import serial
import time
import argparse
import sys
from datetime import datetime


def read_serial_samples(port="/dev/serial0", baud=38400, count=20, timeout=60):
    """
    Read raw serial data from RPICT3V1 and display columns.
    
    Args:
        port: Serial port path (e.g., /dev/serial0, /dev/ttyAMA0)
        baud: Baud rate (RPICT3V1 uses 38400)
        count: Number of samples to read
        timeout: Maximum time to wait (seconds)
        
    Returns:
        list: List of parsed lines
    """
    lines = []
    start_time = time.time()
    
    try:
        ser = serial.Serial(port, baud, timeout=2)
        print(f"✓ Connected to {port} @ {baud} baud\n")
    except serial.SerialException as e:
        print(f"✗ Failed to open {port}: {e}", file=sys.stderr)
        print("\nTroubleshooting:")
        print("  - Check that RPICT3V1 is connected")
        print("  - Verify port path (try: ls /dev/tty* | grep -E 'serial|AMA')")
        print("  - Check permissions: sudo usermod -a -G dialout $USER")
        return None
    
    print(f"Reading {count} samples (timeout: {timeout}s)...\n")
    
    try:
        while len(lines) < count and (time.time() - start_time) < timeout:
            try:
                raw_line = ser.readline()
                if not raw_line:
                    continue
                
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                
                lines.append(line)
                elapsed = time.time() - start_time
                print(f"[{elapsed:6.1f}s] Sample {len(lines):3d}: {line}")
            
            except UnicodeDecodeError:
                continue  # Skip malformed lines
            except KeyboardInterrupt:
                print("\nInterrupted by user")
                break
        
        ser.close()
        return lines
    
    except Exception as e:
        print(f"✗ Error reading serial data: {e}", file=sys.stderr)
        ser.close()
        return None


def analyze_samples(lines):
    """
    Analyze line samples and identify column structure.
    
    Args:
        lines: List of raw serial output lines
    """
    if not lines:
        print("No samples read", file=sys.stderr)
        return
    
    print("\n" + "=" * 80)
    print("COLUMN ANALYSIS")
    print("=" * 80 + "\n")
    
    # Parse first few lines to identify structure
    parsed_lines = []
    for line in lines[:5]:
        tokens = line.split()
        parsed_lines.append(tokens)
        
        print(f"Tokens: {len(tokens)}")
        for i, token in enumerate(tokens):
            try:
                value = float(token)
                print(f"  [{i}] = {value:8.2f}  (numeric)")
            except ValueError:
                print(f"  [{i}] = {token:8s}  (non-numeric)")
        print()
    
    # Try to identify RMS current column
    print("=" * 80)
    print("LIKELY RMS CURRENT COLUMN")
    print("=" * 80 + "\n")
    
    # RPICT3V1 typically outputs voltages (120V range) and currents (0-100A range)
    # Look for columns that:
    # 1. Are numeric
    # 2. Fall in 0-100A range (not 110-130V range)
    # 3. Vary across samples
    
    if len(parsed_lines) > 0:
        first_line = parsed_lines[0]
        num_cols = len(first_line)
        
        print(f"Format appears to be {num_cols} space-delimited columns\n")
        
        # Analyze each column
        for col_idx in range(num_cols):
            values = []
            all_numeric = True
            
            for line in parsed_lines:
                if col_idx < len(line):
                    try:
                        values.append(float(line[col_idx]))
                    except ValueError:
                        all_numeric = False
                        break
            
            if not all_numeric or not values:
                continue
            
            min_val = min(values)
            max_val = max(values)
            mean_val = sum(values) / len(values)
            
            # Heuristic: current columns are typically 0-100A
            # voltage columns are typically 110-130V
            is_current_range = 0 <= min_val <= 100 and 0 <= max_val <= 100
            is_voltage_range = 100 <= min_val <= 130 or 100 <= max_val <= 130
            
            print(f"Column [{col_idx}]:")
            print(f"  Range:  {min_val:8.2f} - {max_val:8.2f}")
            print(f"  Mean:   {mean_val:8.2f}")
            
            if is_current_range:
                print(f"  ✓ LIKELY RMS CURRENT (0-100A range)")
            elif is_voltage_range:
                print(f"  • Likely voltage (110-130V range)")
            else:
                print(f"  • Unknown (range: {min_val:.1f}-{max_val:.1f})")
            print()
    
    # Display recommendation
    print("=" * 80)
    print("CONFIGURATION RECOMMENDATION")
    print("=" * 80 + "\n")
    
    print("Update reader.py main() function:")
    print("  rms_current_column = 3  # Adjust based on analysis above\n")
    
    # Try to auto-detect
    if len(parsed_lines) > 0:
        first_line = parsed_lines[0]
        for col_idx in range(len(first_line)):
            try:
                values = [float(line[col_idx]) for line in parsed_lines if col_idx < len(line)]
                if all(0 <= v <= 100 for v in values):
                    min_val, max_val = min(values), max(values)
                    if min_val < 50 and max_val < 60:  # Typical current draw range
                        print(f"Auto-detected: Column [{col_idx}] looks like RMS current")
                        break
            except (ValueError, IndexError):
                continue


def main():
    """Run serial diagnostic."""
    parser = argparse.ArgumentParser(
        description="Identify RPICT3V1 RMS current column from serial output"
    )
    parser.add_argument(
        "--port",
        default="/dev/serial0",
        help="Serial port (default: /dev/serial0)"
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=38400,
        help="Baud rate (default: 38400)"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="Number of samples to read (default: 20)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Maximum read time in seconds (default: 60)"
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("RPICT3V1 Serial Diagnostic Tool")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Read samples
    lines = read_serial_samples(
        port=args.port,
        baud=args.baud,
        count=args.count,
        timeout=args.timeout
    )
    
    if lines is None:
        return 1
    
    if len(lines) == 0:
        print("\nNo data received. Check:")
        print("  - RPICT3V1 power and connections")
        print("  - Serial port permissions")
        print("  - Baud rate setting")
        return 1
    
    print(f"\n✓ Read {len(lines)} samples")
    
    # Analyze
    analyze_samples(lines)
    
    print("=" * 80 + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        sys.exit(1)
