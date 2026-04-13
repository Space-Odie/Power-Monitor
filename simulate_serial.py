#!/usr/bin/env python3
"""
simulate_serial.py — Mock RPICT3V1 serial data for testing reader.py without hardware.

Usage:
    # Terminal 1 — Start the mock serial server
    python3 simulate_serial.py
    
    # Terminal 2 — Run reader.py (it will connect to /dev/pts/X)
    python3 reader.py

This creates a virtual serial port pair so you can test reader.py's serial I/O,
buffering, and database writes without the actual CT clamp.
"""

import serial
import time
import random
from datetime import datetime
from zoneinfo import ZoneInfo

class MockRPICT3V1:
    """Simulate RPICT3V1 serial output with realistic power consumption patterns."""
    
    def __init__(self, rate_hz=1, baseline_amps=20, noise_level=2):
        """
        Args:
            rate_hz: Samples per second (1 Hz = one reading/second)
            baseline_amps: Average home load (A)
            noise_level: Random noise variation (A)
        """
        self.rate_hz = rate_hz
        self.interval = 1.0 / rate_hz
        self.baseline_amps = baseline_amps
        self.noise_level = noise_level
        self.sample_count = 0
    
    def get_realistic_load(self):
        """Generate load based on time of day (daily pattern)."""
        tz = ZoneInfo("America/Los_Angeles")
        now = datetime.now(tz)
        hour = now.hour
        minute = now.minute
        
        # Daily pattern: low overnight, peaks during day
        if 0 <= hour < 6:
            # Overnight (0-6 AM): baseline ~15A
            base = self.baseline_amps * 0.75
        elif 6 <= hour < 9:
            # Early morning (6-9 AM): ramp up, breakfast
            base = self.baseline_amps * 0.9
        elif 9 <= hour < 17:
            # Daytime (9-5 PM): higher load, HVAC active
            base = self.baseline_amps * 1.2
        elif 17 <= hour < 21:
            # Evening (5-9 PM): cooking, peak usage
            base = self.baseline_amps * 1.5
        else:
            # Late evening (9 PM-midnight): wind down
            base = self.baseline_amps * 0.85
        
        # Add random variation (noise)
        noise = random.gauss(0, self.noise_level)
        
        # Occasional spikes (simulating kettle, HVAC compressor, etc.)
        if random.random() < 0.02:  # 2% chance of spike
            spike = random.uniform(10, 30)
            return max(0, base + noise + spike)
        
        return max(0, base + noise)
    
    def generate_line(self):
        """Generate one RPICT3V1-format output line.
        
        Example RPICT3V1 output (space-delimited):
        V1 V2 V3 I1 I2 I3
        or
        V1 V2 V3 I1 I2 I3 P1 P2 P3 F
        
        We'll use: V1 V2 V3 I1 I2 I3 (RMS current in Amps is one of the I columns)
        For simplicity: assume I1 is RMS current (modify as needed based on actual RPICT3V1 output)
        """
        # Typical values for RPICT3V1
        v1 = random.uniform(115, 125)  # Phase 1 voltage
        v2 = random.uniform(115, 125)  # Phase 2 voltage
        v3 = random.uniform(115, 125)  # Phase 3 voltage
        
        i1 = self.get_realistic_load()  # RMS current (our measured value)
        i2 = random.uniform(5, 15)       # Other phases (low load)
        i3 = random.uniform(5, 15)
        
        # Format: space-delimited floats
        # Verify the column order with test_serial.py on actual hardware
        line = f"{v1:.2f} {v2:.2f} {v3:.2f} {i1:.2f} {i2:.2f} {i3:.2f}\n"
        self.sample_count += 1
        return line
    
    def run(self, duration_seconds=None):
        """Stream mock data to stdout at specified rate."""
        print(f"[MockRPICT3V1] Starting simulation at {self.rate_hz} Hz...")
        print(f"[MockRPICT3V1] Baseline: {self.baseline_amps}A, Noise: {self.noise_level}A")
        print(f"[MockRPICT3V1] Sending data to stdout (pipe to your app)...")
        print("-" * 80)
        
        start_time = time.time()
        next_sample_time = start_time
        
        try:
            while True:
                now = time.time()
                
                # Wait until it's time for next sample
                if now < next_sample_time:
                    time.sleep(next_sample_time - now)
                    now = time.time()
                
                # Generate and output line
                line = self.generate_line()
                print(line, end="", flush=True)
                
                next_sample_time = now + self.interval
                
                # Optional: stop after duration
                if duration_seconds and (now - start_time) > duration_seconds:
                    break
        
        except KeyboardInterrupt:
            elapsed = time.time() - start_time
            print(f"\n[MockRPICT3V1] Stopped after {elapsed:.1f}s ({self.sample_count} samples)")

def main():
    """Entry point — run mock serial generator."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Mock RPICT3V1 serial data generator for testing reader.py"
    )
    parser.add_argument("--rate", type=float, default=1.0, help="Sampling rate (Hz, default 1.0)")
    parser.add_argument("--baseline", type=float, default=20.0, help="Baseline load (A, default 20)")
    parser.add_argument("--noise", type=float, default=2.0, help="Noise level (A, default 2)")
    parser.add_argument("--duration", type=float, default=None, help="Run duration (seconds, default infinite)")
    
    args = parser.parse_args()
    
    simulator = MockRPICT3V1(
        rate_hz=args.rate,
        baseline_amps=args.baseline,
        noise_level=args.noise
    )
    simulator.run(duration_seconds=args.duration)

if __name__ == "__main__":
    main()
