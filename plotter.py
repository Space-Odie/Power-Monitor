#!/usr/bin/env python3
"""
plotter.py — Generate power consumption charts and EV feasibility analysis.

Reads historical data from SQLite database and creates matplotlib visualizations
to help assess whether a Level 2 EV charger can be supported on the circuit.

Usage:
    python3 plotter.py                    # Plot all data
    python3 plotter.py --days 7           # Last 7 days
    python3 plotter.py --days 30          # Last 30 days (default if data exists)

Output charts (saved to reports/ directory):
    - daily_distribution.png — Power distribution by hour of day
    - power_timeline.png — 30-day power consumption timeline
    - peak_analysis.png — 95th percentile during off-peak hours
    - weekly_pattern.png — Weekly average power patterns

Configuration:
    Modify main() to adjust chart aesthetics, thresholds, or output directory.
"""

import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict

from logger import DataLogger

# Chart styling
plt.style.use("seaborn-v0_8-darkgrid")
FIGURE_DPI = 100
FIGURE_SIZE = (14, 6)

# EV parameters
BREAKER_LIMIT = 100  # Amps (hard safety limit)
EV_DRAW = 48  # Amps (Level 2 charger typical)
HEADROOM_THRESHOLD = BREAKER_LIMIT - EV_DRAW  # 52A available headroom
OFF_PEAK_START = 21  # 9 PM
OFF_PEAK_END = 6    # 6 AM


class PowerPlotter:
    """Generate charts and analysis from power database."""
    
    def __init__(self, db_path="data/readings.db", output_dir="reports", tz="America/Los_Angeles"):
        """
        Initialize plotter with database and output directory.
        
        Args:
            db_path: Path to SQLite database
            output_dir: Directory for output PNG files
            tz: Timezone for timestamp interpretation
        """
        self.db = DataLogger(db_path)
        self.output_dir = output_dir
        self.tz = ZoneInfo(tz)
        
        # Create output directory if needed
        os.makedirs(output_dir, exist_ok=True)
    
    def plot_daily_distribution(self, days=30):
        """
        Create hourly power consumption distribution chart.
        
        Shows mean, min, max for each hour across all days in range.
        Highlights off-peak window (21:00-06:00).
        """
        # Query data
        end_date = datetime.now(self.tz)
        start_date = end_date - timedelta(days=days)
        rows = self.db.query_by_date_range(start_date, end_date)
        
        if not rows:
            print(f"No data for last {days} days")
            return
        
        # Aggregate by hour
        hourly = defaultdict(list)
        for _, timestamp_str, amps in rows:
            ts = datetime.fromisoformat(timestamp_str)
            hour = ts.hour
            hourly[hour].append(amps)
        
        # Calculate statistics
        hours = sorted(hourly.keys())
        means = [np.mean(hourly[h]) for h in hours]
        mins = [np.min(hourly[h]) for h in hours]
        maxs = [np.max(hourly[h]) for h in hours]
        
        # Create plot
        fig, ax = plt.subplots(figsize=FIGURE_SIZE, dpi=FIGURE_DPI)
        
        # Highlight off-peak zone
        if OFF_PEAK_START > OFF_PEAK_END:  # Wraps midnight
            ax.axvspan(OFF_PEAK_START, 24, alpha=0.1, color="green", label="Off-peak (21:00-06:00)")
            ax.axvspan(0, OFF_PEAK_END, alpha=0.1, color="green")
        else:
            ax.axvspan(OFF_PEAK_START, OFF_PEAK_END, alpha=0.1, color="green", label="Off-peak")
        
        # Plot lines
        ax.plot(hours, means, "o-", linewidth=2, markersize=6, label="Mean", color="blue")
        ax.fill_between(hours, mins, maxs, alpha=0.2, color="blue", label="Min/Max range")
        
        # Thresholds
        ax.axhline(BREAKER_LIMIT, color="red", linestyle="--", linewidth=2, label=f"Breaker limit ({BREAKER_LIMIT}A)")
        ax.axhline(HEADROOM_THRESHOLD, color="orange", linestyle="--", linewidth=2, label=f"Headroom for EV ({HEADROOM_THRESHOLD}A)")
        
        ax.set_xlabel("Hour of Day", fontsize=12, fontweight="bold")
        ax.set_ylabel("Current (Amps)", fontsize=12, fontweight="bold")
        ax.set_title(f"Hourly Power Distribution (Last {days} Days)", fontsize=14, fontweight="bold")
        ax.set_xticks(range(0, 24, 2))
        ax.set_xlim(-0.5, 23.5)
        ax.legend(loc="upper right")
        ax.grid(True, alpha=0.3)
        
        filepath = os.path.join(self.output_dir, "daily_distribution.png")
        fig.savefig(filepath, bbox_inches="tight", dpi=FIGURE_DPI)
        print(f"✓ Saved {filepath}")
        plt.close(fig)
    
    def plot_timeline(self, days=30):
        """
        Create 30-day power consumption timeline.
        
        Shows individual samples (downsampled if needed) over time with
        breaker limit and EV headroom thresholds.
        """
        # Query data
        end_date = datetime.now(self.tz)
        start_date = end_date - timedelta(days=days)
        rows = self.db.query_by_date_range(start_date, end_date)
        
        if not rows:
            print(f"No data for last {days} days")
            return
        
        # Extract timestamps and values
        timestamps = []
        amps = []
        for _, timestamp_str, amp_value in rows:
            ts = datetime.fromisoformat(timestamp_str)
            timestamps.append(ts)
            amps.append(amp_value)
        
        # Create plot
        fig, ax = plt.subplots(figsize=FIGURE_SIZE, dpi=FIGURE_DPI)
        
        # Plot data (may be downsampled if too many points)
        if len(amps) > 50000:
            # Downsample for visibility
            step = len(amps) // 50000
            ax.plot(timestamps[::step], amps[::step], ".", markersize=1, alpha=0.6, color="blue")
        else:
            ax.plot(timestamps, amps, ".", markersize=2, alpha=0.6, color="blue")
        
        # Thresholds
        ax.axhline(BREAKER_LIMIT, color="red", linestyle="--", linewidth=2, label=f"Breaker limit ({BREAKER_LIMIT}A)")
        ax.axhline(HEADROOM_THRESHOLD, color="orange", linestyle="--", linewidth=2, label=f"Headroom for EV ({HEADROOM_THRESHOLD}A)")
        
        ax.set_xlabel("Date", fontsize=12, fontweight="bold")
        ax.set_ylabel("Current (Amps)", fontsize=12, fontweight="bold")
        ax.set_title(f"Power Consumption Timeline (Last {days} Days)", fontsize=14, fontweight="bold")
        ax.legend(loc="upper right")
        ax.grid(True, alpha=0.3)
        fig.autofmt_xdate()
        
        filepath = os.path.join(self.output_dir, "power_timeline.png")
        fig.savefig(filepath, bbox_inches="tight", dpi=FIGURE_DPI)
        print(f"✓ Saved {filepath}")
        plt.close(fig)
    
    def plot_peak_analysis(self, days=30):
        """
        Analyze 95th percentile during off-peak hours.
        
        Filters to OFF_PEAK_START-OFF_PEAK_END window and shows percentile
        distribution with decision threshold for EV feasibility.
        """
        # Query data
        end_date = datetime.now(self.tz)
        start_date = end_date - timedelta(days=days)
        rows = self.db.query_by_date_range(start_date, end_date)
        
        if not rows:
            print(f"No data for last {days} days")
            return
        
        # Filter to off-peak hours
        off_peak_amps = []
        for _, timestamp_str, amp_value in rows:
            ts = datetime.fromisoformat(timestamp_str)
            hour = ts.hour
            
            # Check if in off-peak window
            if OFF_PEAK_START > OFF_PEAK_END:  # Wraps midnight
                in_off_peak = hour >= OFF_PEAK_START or hour < OFF_PEAK_END
            else:
                in_off_peak = OFF_PEAK_START <= hour < OFF_PEAK_END
            
            if in_off_peak:
                off_peak_amps.append(amp_value)
        
        if not off_peak_amps:
            print("No off-peak data available")
            return
        
        # Calculate percentiles
        p95 = np.percentile(off_peak_amps, 95)
        p75 = np.percentile(off_peak_amps, 75)
        p50 = np.percentile(off_peak_amps, 50)
        p25 = np.percentile(off_peak_amps, 25)
        
        # Create plot
        fig, ax = plt.subplots(figsize=FIGURE_SIZE, dpi=FIGURE_DPI)
        
        # Histogram of off-peak distribution
        ax.hist(off_peak_amps, bins=50, alpha=0.7, color="blue", edgecolor="black")
        
        # Percentile lines
        ax.axvline(p25, color="green", linestyle="--", linewidth=2, label=f"25th percentile ({p25:.1f}A)")
        ax.axvline(p50, color="cyan", linestyle="--", linewidth=2, label=f"Median ({p50:.1f}A)")
        ax.axvline(p75, color="orange", linestyle="--", linewidth=2, label=f"75th percentile ({p75:.1f}A)")
        ax.axvline(p95, color="red", linestyle="--", linewidth=2.5, label=f"95th percentile ({p95:.1f}A)")
        
        # EV headroom threshold
        ax.axvline(HEADROOM_THRESHOLD, color="purple", linestyle=":", linewidth=2.5, label=f"EV headroom ({HEADROOM_THRESHOLD}A)")
        
        ax.set_xlabel("Current (Amps)", fontsize=12, fontweight="bold")
        ax.set_ylabel("Frequency", fontsize=12, fontweight="bold")
        ax.set_title(f"Off-Peak Current Distribution (95th Percentile: {p95:.1f}A)", fontsize=14, fontweight="bold")
        ax.legend(loc="upper right", fontsize=10)
        ax.grid(True, alpha=0.3, axis="y")
        
        filepath = os.path.join(self.output_dir, "peak_analysis.png")
        fig.savefig(filepath, bbox_inches="tight", dpi=FIGURE_DPI)
        print(f"✓ Saved {filepath}")
        plt.close(fig)
        
        # Print EV feasibility decision
        self._print_ev_feasibility(p95)
    
    def plot_weekly_pattern(self, days=30):
        """
        Show weekly patterns: average power by day of week.
        
        Helps identify if weekends/weekdays have different consumption patterns.
        """
        # Query data
        end_date = datetime.now(self.tz)
        start_date = end_date - timedelta(days=days)
        rows = self.db.query_by_date_range(start_date, end_date)
        
        if not rows:
            print(f"No data for last {days} days")
            return
        
        # Aggregate by day of week
        weekday_amps = defaultdict(list)
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        
        for _, timestamp_str, amp_value in rows:
            ts = datetime.fromisoformat(timestamp_str)
            weekday = ts.weekday()  # 0=Monday, 6=Sunday
            weekday_amps[weekday].append(amp_value)
        
        # Calculate means
        weekdays = sorted(weekday_amps.keys())
        means = [np.mean(weekday_amps[wd]) for wd in weekdays]
        labels = [day_names[wd] for wd in weekdays]
        
        # Create plot
        fig, ax = plt.subplots(figsize=FIGURE_SIZE, dpi=FIGURE_DPI)
        
        bars = ax.bar(labels, means, color="steelblue", edgecolor="black", alpha=0.7)
        
        # Highlight weekends
        for i, (wd, mean_val) in enumerate(zip(weekdays, means)):
            if wd >= 5:  # Saturday, Sunday
                bars[i].set_color("lightcoral")
        
        # Thresholds
        ax.axhline(BREAKER_LIMIT, color="red", linestyle="--", linewidth=2, label=f"Breaker limit ({BREAKER_LIMIT}A)")
        ax.axhline(HEADROOM_THRESHOLD, color="orange", linestyle="--", linewidth=2, label=f"EV headroom ({HEADROOM_THRESHOLD}A)")
        
        ax.set_ylabel("Average Current (Amps)", fontsize=12, fontweight="bold")
        ax.set_title(f"Weekly Average Power Pattern (Last {days} Days)", fontsize=14, fontweight="bold")
        ax.legend(loc="upper right")
        ax.grid(True, alpha=0.3, axis="y")
        
        filepath = os.path.join(self.output_dir, "weekly_pattern.png")
        fig.savefig(filepath, bbox_inches="tight", dpi=FIGURE_DPI)
        print(f"✓ Saved {filepath}")
        plt.close(fig)
    
    def _print_ev_feasibility(self, p95_offpeak):
        """
        Print decision on whether EV charger can be supported.
        
        Decision criteria:
            - 95th percentile during off-peak hours + EV draw must be <= breaker limit
            - Equivalent: p95_offpeak + EV_DRAW <= BREAKER_LIMIT
        """
        total_load = p95_offpeak + EV_DRAW
        margin = BREAKER_LIMIT - total_load
        
        print("\n" + "=" * 70)
        print("EV CHARGER FEASIBILITY ANALYSIS")
        print("=" * 70)
        print(f"Off-peak 95th percentile load:  {p95_offpeak:6.1f}A")
        print(f"Level 2 EV charger draw:        {EV_DRAW:6.1f}A")
        print(f"Total combined load:            {total_load:6.1f}A")
        print(f"Breaker capacity:               {BREAKER_LIMIT:6.1f}A")
        print(f"Safety margin:                  {margin:6.1f}A")
        print("-" * 70)
        
        if margin >= 0:
            print(f"✓ YES - EV charger is FEASIBLE")
            print(f"  Total load ({total_load:.1f}A) is within breaker capacity with {margin:.1f}A safety margin")
        else:
            print(f"✗ NO - EV charger is NOT FEASIBLE")
            print(f"  Total load ({total_load:.1f}A) exceeds breaker capacity by {abs(margin):.1f}A")
        print("=" * 70 + "\n")


def main():
    """Generate all charts and analysis."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Plot power consumption data and analyze EV feasibility")
    parser.add_argument("--days", type=int, default=30, help="Days of history to plot (default: 30)")
    parser.add_argument("--db", default="data/readings.db", help="Path to database (default: data/readings.db)")
    parser.add_argument("--output", default="reports", help="Output directory (default: reports)")
    
    args = parser.parse_args()
    
    # Check database exists
    if not os.path.exists(args.db):
        print(f"Error: Database not found at {args.db}")
        print("Run: python3 simulate_data.py  (to generate test data)")
        return 1
    
    # Create plotter and generate charts
    plotter = PowerPlotter(db_path=args.db, output_dir=args.output)
    
    print(f"\nGenerating charts from {args.days} days of data...\n")
    
    try:
        plotter.plot_daily_distribution(args.days)
        plotter.plot_timeline(args.days)
        plotter.plot_peak_analysis(args.days)
        plotter.plot_weekly_pattern(args.days)
        
        print(f"\n✓ Charts saved to {os.path.abspath(args.output)}/\n")
        return 0
    
    except Exception as e:
        print(f"Error generating charts: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
