# EV Power Monitor — RPICT3V1 Pipeline

A Raspberry Pi-based power monitoring system to track electrical load and determine if a Level 2 EV charger can be supported on your circuit without overloading the main breaker.

**What it does:**
- Continuously samples current from a CT clamp via RPICT3V1 current transformer board
- Stores 30+ days of power consumption data in SQLite
- Generates charts showing load patterns and available headroom
- Calculates if your panel has enough capacity for a 48A EV charger

---

## Overview

This project consists of:
- **`reader.py`** — Daemon that reads current data from RPICT3V1 serial port and buffers to database
- **`logger.py`** — Database abstraction layer for efficient data storage
- **`plotter.py`** — Generates 4 visualization charts and feasibility analysis
- **Simulation tools** — Test the system without hardware

---

## Prerequisites

**Hardware:**
- Raspberry Pi (any model with GPIO and UART)
- RPICT3V1 current transformer interface board
- 100A CT clamp (or appropriate size for your breaker)

**Software:**
- Python 3.9 or higher
- pip package manager

**Verify your Python version:**
```bash
python3 --version
```

---

## Installation

### Step 1: Clone/Download Project

```bash
git clone <repository-url>  # Or download as ZIP
cd EV_Monitor
```

### Step 2: Create Project Directory (on your device)

```bash
mkdir -p ~/ev-monitor-project
cd ~/ev-monitor-project
cp -r /path/to/EV_Monitor/* .
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `pyserial>=3.5` — Serial communication with RPICT3V1
- `matplotlib>=3.5` — Chart generation
- `numpy>=1.21` — Numerical calculations

**On Raspberry Pi with PEP 668 enforcement:**
```bash
sudo pip install --break-system-packages -r requirements.txt
```

### Step 4: Verify Dependencies

```bash
python3 check_dependencies.py
```

Expected output: `✓ All required dependencies are installed!`

---

## Testing Without Hardware (Simulation)

Before deploying to actual hardware, test the entire pipeline with simulated data. This allows you to verify database writes, chart generation, and EV feasibility logic without waiting for 30 days of real data collection.

### Quick Test (5 minutes)

```bash
# Generate 30 days of simulated power data
python3 simulate_data.py

# Generate charts
python3 plotter.py

# View the 4 PNG files in reports/ directory
```

### Detailed Simulation Workflow

**Phase 1 — Test Database + Plotter:**
```bash
python3 init_db.py                                          # Fresh database
python3 simulate_data.py --days 30 --baseline 20 --noise 2  # Generate test data
python3 plotter.py                                          # Create charts
```

Output includes:
- 2.6M samples (30 days of 1 Hz sampling)
- 4 PNG charts in `reports/` directory
- Console summary with EV feasibility decision

**Phase 2 — Test Serial Reader (with mock data):**
```bash
# Terminal 1: Start mock RPICT3V1 serial stream
python3 simulate_serial.py --rate 1 --baseline 20 --noise 2

# Terminal 2: Run reader.py to consume mock data
python3 reader.py
```

**Simulation Parameters:**
```bash
simulate_data.py:
  --days N         # Days to simulate (default: 30)
  --baseline A     # Baseline load in Amps (default: 20)
  --noise A        # Noise variation in Amps (default: 2)

simulate_serial.py:
  --rate HZ        # Sampling rate (default: 1)
  --baseline A     # Baseline load in Amps (default: 20)
  --noise A        # Noise variation in Amps (default: 2)
  --duration SEC   # Run duration in seconds (default: infinite)
```

---

## Hardware Setup & Deployment

### Step 1: Connect Hardware

1. Mount RPICT3V1 board on Raspberry Pi GPIO pins
2. Clamp CT sensor around the hot leg of your breaker
3. Verify `/dev/serial0` exists:
   ```bash
   ls -la /dev/serial0
   ```

### Step 2: Test Serial Connection

```bash
python3 test_serial.py
```

This reads 20 samples and labels each column. **Important:** Note which column contains RMS current (typically 0–100A range), then update the `parse_line()` method in `reader.py` with the correct column index.

### Step 3: Initialize Database

```bash
python3 init_db.py
```

This creates directories (`data/`, `reports/`, `backups/`) and initializes the SQLite database.

### Step 4: Run Reader Continuously

#### Option A: Manual (for testing)
```bash
python3 reader.py
```

Press Ctrl+C to stop gracefully (flushes final buffer to DB).

#### Option B: Systemd Daemon (for production)

1. **Install the systemd service:**
   ```bash
   sudo cp power-monitor.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable power-monitor.service
   ```

2. **Start the service:**
   ```bash
   sudo systemctl start power-monitor.service
   ```

3. **Monitor the service:**
   ```bash
   systemctl status power-monitor.service
   journalctl -u power-monitor -n 20 -f  # Live logs
   ```

### Step 5: Wait for Data Collection

Collect data for at least **7 days** (ideally 30 days) to get representative patterns.

### Step 6: Generate Analysis

```bash
python3 plotter.py
```

This generates 4 PNG charts in `reports/` and prints EV charging feasibility to console.

---

## Project Structure

```
ev-monitor-project/
├── reader.py              # Serial reader daemon
├── logger.py              # SQLite database wrapper
├── plotter.py             # Chart generation & analysis
├── init_db.py             # Database initialization
├── test_serial.py         # Serial format diagnostic
├── check_dependencies.py  # Dependency verification
├── simulate_data.py       # Generate 30-day simulated dataset
├── simulate_serial.py     # Mock RPICT3V1 serial data
├── power-monitor.service  # Systemd unit file (for Raspberry Pi)
├── requirements.txt       # Python dependencies
├── README.md              # This file
├── data/
│   └── readings.db        # SQLite database (auto-created)
├── reports/               # Output charts (auto-created)
└── backups/               # Database backups (auto-created)
```

---

## Files Overview

### Core Scripts

- **`reader.py`** — Continuously reads current from RPICT3V1 via serial port. Buffers readings and flushes to database every 10 seconds or 100 rows. Handles graceful shutdown.

- **`logger.py`** — SQLite database wrapper. Manages data storage, batch inserts, and archival of old data. Uses WAL journaling for reliability.

- **`plotter.py`** — Generates 4 matplotlib charts and analyzes data:
  1. Raw load over 30 days with breaker capacity lines
  2. Average load by hour of day
  3. Headroom distribution (how often is 48A available)
  4. Daily heatmap (load by day and hour)
  
  Outputs PNGs to `reports/` and includes EV feasibility analysis.

### Utility Scripts

- **`init_db.py`** — Creates necessary directories and initializes SQLite database with proper schema.

- **`test_serial.py`** — Diagnostic tool to identify which column of RPICT3V1 output contains RMS current.

- **`check_dependencies.py`** — Verifies all required Python packages are installed.

### Testing & Simulation Scripts

- **`simulate_data.py`** — Generates 30 days of realistic power consumption data. Insert directly into database for testing without hardware.

- **`simulate_serial.py`** — Mock RPICT3V1 serial output. Test reader.py without actual hardware.

### Configuration

- **`power-monitor.service`** — Systemd unit for running reader.py as a system daemon (Raspberry Pi).

- **`requirements.txt`** — Python package versions.

---

## Deployment Checklist

- [ ] Clone/download project and install dependencies
- [ ] Run `python3 check_dependencies.py` to verify packages
- [ ] Test with simulated data: `python3 simulate_data.py && python3 plotter.py`
- [ ] Connect RPICT3V1 hardware to Raspberry Pi
- [ ] Run `python3 test_serial.py` and verify RMS current column
- [ ] Update `parse_line()` method in `reader.py` with correct column index
- [ ] Run `python3 init_db.py` to create database
- [ ] Start reader manually: `python3 reader.py` (test for errors)
- [ ] (Optional) Install as systemd service for auto-startup
- [ ] Wait 7–30 days for data collection
- [ ] Run `python3 plotter.py` to generate charts
- [ ] Review EV charging feasibility decision

---

## Cron Jobs (for automated plotting)

If running as systemd service, optionally add cron jobs to automate chart generation:

```bash
crontab -e

# Add these lines:

# Daily plotter run (2 AM)
0 2 * * * python3 /path/to/plotter.py >> plotter.log 2>&1

# Weekly data integrity check (Sunday, 1 AM)
0 1 * * 0 sqlite3 data/readings.db "PRAGMA integrity_check;" >> integrity.log 2>&1

# Daily database backup
0 3 * * * cp data/readings.db backups/readings.db.bak

# Weekly data archival (Sunday, 4 AM)
0 4 * * 0 python3 -c "from logger import DataLogger; DataLogger().archive_old_data(90)"
```

---

## Troubleshooting

### Dependencies won't install

On Raspberry Pi OS (Bullseye+), use:
```bash
sudo pip install --break-system-packages -r requirements.txt
```

This is required due to PEP 668 externally-managed environments.

### Serial connection issues

1. Verify UART is enabled: `ls -la /dev/serial0` should exist
2. Confirm RPICT3V1 board is properly seated on GPIO pins
3. Check CT clamp is clamped around the hot leg (center conductor) of breaker
4. Run `python3 test_serial.py` to see live data and identify columns

### Database corruption

```bash
# Restore from backup
cp backups/readings.db.bak data/readings.db

# Or start fresh
python3 init_db.py
```

### Service won't start

```bash
# Check systemd logs
journalctl -u power-monitor -n 50

# Verify service file
systemctl status power-monitor.service
```

---

## Configuration & Customization

### Changing Thresholds

Edit `plotter.py` main() function to customize analysis parameters:

```python
plotter = PowerPlotter(
    db_path="data/readings.db",
    output_dir="reports",
    breaker_limit=100,        # Your breaker capacity (A)
    ev_draw=48,               # EV charger draw (A)
    analysis_hours=(21, 6),   # Analysis window (9 PM to 6 AM)
    percentile=95             # Percentile for worst-case
)
```

### Changing Serial Port

Edit `reader.py` to use a different serial port:

```python
reader = SerialReader(
    port="/dev/ttyUSB0",      # Change this
    baud=38400,
    ...
)
```

### Changing Database Location

Edit database path in `init_db.py`, `reader.py`, and `plotter.py`:

```python
logger = DataLogger("path/to/readings.db")
```

---

## Key Design Decisions

- **1 Hz sampling** — High resolution, ~260 MB per month
- **Batch commits** — Every 10 seconds or 100 rows to reduce write frequency
- **SQLite with WAL** — Reliable on SD cards and other flash storage
- **America/Los_Angeles timezone** — Customizable in code; uses ISO8601 format
- **90-day retention** — Archives older data to separate databases
- **Off-peak analysis (21:00–06:00)** — Typical overnight EV charging window

---

## Troubleshooting

### I'm getting incorrect current values

Run `python3 test_serial.py` and carefully examine which column contains values in the 0–100A range. Update the column index in `reader.py` parse_line() method.

### Plotter says "No data in database"

Wait at least 7 days of continuous data collection. Check that `reader.py` is running:
```bash
ps aux | grep reader.py
```

### Charts show unrealistic patterns

Verify the simulation parameters match your home's baseline load and noise level. Adjust with:
```bash
python3 simulate_data.py --baseline 25 --noise 3
```
