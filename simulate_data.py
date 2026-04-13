#!/usr/bin/env python3
"""
simulate_data.py — Generate 30 days of realistic power consumption and inject into database.

This script creates a complete dataset for testing plotter.py without waiting for real hardware data.

Usage:
    python3 simulate_data.py
    
    # Then view the generated charts:
    python3 plotter.py

Optional arguments:
    python3 simulate_data.py --days 30 --baseline 20 --noise 2

This will:
1. Create data/readings.db if it doesn't exist (via logger.DataLogger)
2. Generate 30 days of 1 Hz sampled power data
3. Insert into database with realistic daily patterns
4. Output summary statistics
5. Ready for plotter.py to visualize
"""

import sys
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import random
import logging

# Import our logger module
try:
    from logger import DataLogger
except ImportError:
    print("ERROR: logger.py not found. Make sure it's in the same directory.")
    sys.exit(1)

class PowerDataSimulator:
    """Generate realistic home power consumption data."""
    
    def __init__(self, days=30, baseline_amps=20, noise_level=2):
        """
        Args:
            days: Number of days to simulate
            baseline_amps: Average home load (A)
            noise_level: Random noise variation (A)
        """
        self.days = days
        self.baseline_amps = baseline_amps
        self.noise_level = noise_level
        self.tz = ZoneInfo("America/Los_Angeles")
        self.logger = DataLogger("data/readings.db")
        self.all_amps = []
    
    def get_load_for_time(self, dt):
        """Get realistic load based on time of day and day of week."""
        hour = dt.hour
        weekday = dt.weekday()  # 0=Monday, 6=Sunday
        
        # Base load by hour (24-hour pattern)
        if 0 <= hour < 6:
            base = self.baseline_amps * 0.75    # Overnight: minimal
        elif 6 <= hour < 9:
            base = self.baseline_amps * 0.9     # Morning: ramp up
        elif 9 <= hour < 17:
            base = self.baseline_amps * 1.2     # Daytime: HVAC, appliances
        elif 17 <= hour < 21:
            base = self.baseline_amps * 1.5     # Evening: cooking, peak
        else:
            base = self.baseline_amps * 0.85    # Late night: wind down
        
        # Weekday variation (higher weekend load)
        if weekday >= 5:  # Saturday, Sunday
            base *= 1.1
        
        # Add noise
        noise = random.gauss(0, self.noise_level)
        
        # Occasional spikes (appliances, compressor kicks in)
        if random.random() < 0.01:  # 1% chance per second
            spike = random.uniform(10, 30)
            return max(0, base + noise + spike)
        
        return max(0, base + noise)
    
    def generate_data(self):
        """Generate 30 days of 1 Hz power data."""
        print(f"[Simulator] Generating {self.days} days of power data...")
        print(f"[Simulator] Baseline: {self.baseline_amps}A, Noise: {self.noise_level}A")
        
        # Start 30 days ago from now
        end_time = datetime.now(self.tz)
        start_time = end_time - timedelta(days=self.days)
        
        current_time = start_time
        sample_count = 0
        batch = []
        batch_size = 1000  # Commit every 1000 samples
        
        while current_time < end_time:
            amps = self.get_load_for_time(current_time)
            timestamp = current_time.isoformat()
            
            batch.append((timestamp, amps))
            self.all_amps.append(amps)
            sample_count += 1
            
            # Flush batch to DB
            if len(batch) >= batch_size:
                self.logger.insert_batch(batch)
                print(f"  Inserted {sample_count} samples ({100*sample_count/(self.days*86400):.1f}%)")
                batch = []
            
            # Increment by 1 second (1 Hz sampling)
            current_time += timedelta(seconds=1)
        
        # Final batch
        if batch:
            self.logger.insert_batch(batch)
        
        print(f"[Simulator] Complete! {sample_count} total samples inserted.")
        return sample_count
    
    def summarize(self):
        """Print statistics about generated data."""
        import numpy as np
        
        if not self.all_amps:
            print("ERROR: No data generated")
            return
        
        amps = self.all_amps
        print(f"\n{'='*60}")
        print(f"Generated Data Summary ({len(amps)} samples)")
        print(f"{'='*60}")
        print(f"Min load:       {min(amps):6.1f} A")
        print(f"Max load:       {max(amps):6.1f} A")
        print(f"Mean load:      {np.mean(amps):6.1f} A")
        print(f"Std dev:        {np.std(amps):6.1f} A")
        print(f"95th percentile: {np.percentile(amps, 95):6.1f} A")
        print(f"{'='*60}")
        
        # EV feasibility check
        headroom = [100 - a for a in amps]
        pct_with_ev = 100 * sum(1 for h in headroom if h >= 48) / len(headroom)
        print(f"\nEV Charging Analysis (50A circuit = 48A usable):")
        print(f"  Time with ≥48A headroom: {pct_with_ev:.1f}%")
        print(f"  Min headroom: {min(headroom):.1f}A")
        print(f"  Max headroom: {max(headroom):.1f}A")
        
        # Overnight (21:00-06:00) analysis
        from datetime import datetime
        tz = ZoneInfo("America/Los_Angeles")
        
        # Get all readings and filter to overnight
        conn = __import__('sqlite3').connect("data/readings.db")
        rows = conn.execute("SELECT timestamp, amps FROM readings").fetchall()
        conn.close()
        
        overnight_amps = []
        for ts_str, amp in rows:
            ts = datetime.fromisoformat(ts_str)
            hour = ts.hour
            if hour >= 21 or hour < 6:
                overnight_amps.append(amp)
        
        if overnight_amps:
            p95_overnight = np.percentile(overnight_amps, 95)
            headroom_p95 = 100 - p95_overnight
            ev_feasible = headroom_p95 >= 48
            print(f"\nOvernight Peak (21:00-06:00, 95th percentile):")
            print(f"  95th percentile load: {p95_overnight:.1f}A")
            print(f"  Available headroom:   {headroom_p95:.1f}A")
            print(f"  EV compatible:        {'YES ✓' if ev_feasible else 'NO ✗'}")
        
        print(f"{'='*60}")
        print(f"\nNext: Run 'python3 plotter.py' to generate charts")
        print(f"{'='*60}\n")

def main():
    """Entry point — generate simulated power data."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate realistic power consumption data for testing"
    )
    parser.add_argument("--days", type=int, default=30, help="Days to simulate (default 30)")
    parser.add_argument("--baseline", type=float, default=20.0, help="Baseline load (A, default 20)")
    parser.add_argument("--noise", type=float, default=2.0, help="Noise level (A, default 2)")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
    
    simulator = PowerDataSimulator(
        days=args.days,
        baseline_amps=args.baseline,
        noise_level=args.noise
    )
    simulator.generate_data()
    simulator.summarize()

if __name__ == "__main__":
    main()
