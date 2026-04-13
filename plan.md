# RPICT3V1 Power Monitoring Pipeline — PiPro

## Goal

Monitor a 100A main breaker over 30 days to build a load profile. Use the data to determine
available amperage headroom at different times of day, specifically to evaluate whether a Level 2
EV charger (typically 24–48A on a 240V/50A circuit) can be supported without overloading the panel.

---

## Hardware

- Raspberry Pi (PiPro) — already configured, SSH accessible at 192.168.4.50
- RPICT3V1 — current transformer interface board, mounts on GPIO header
- CT clamp — 100A rated, clamps around the hot leg of the monitored breaker
- UART serial output on `/dev/serial0` (already enabled in user-data config)

---

## Pipeline Overview

```
[CT Clamp on 100A Breaker]
        |
        v
[RPICT3V1 Board on Pi GPIO]
        |  (UART serial, /dev/serial0)
        v
[1. Serial Reader — reader.py]
        |  (timestamped amperage readings)
        v
[2. Logger — logger.py or SQLite DB]
        |  (data/readings.db or data/readings.csv)
        v
[3. Plotter — plotter.py]
        |  (matplotlib graphs)
        v
[4. Output — PNG charts or live dashboard]
```

---

## Architecture & Extensibility Design

### File Structure (11 Files Total)

```
/home/pi/power-monitor/
├── reader.py              [DAEMON] Continuous serial reader, writes to logger
├── logger.py              [LIBRARY] Data access layer, SQLite wrapper, batch commits
├── plotter.py             [BATCH] Analytics & visualization, reads from DB
├── init_db.py             [UTILITY] One-time DB + directory initialization
├── test_serial.py         [DIAGNOSTIC] Identifies RMS current column before deployment
├── check_dependencies.py   [DIAGNOSTIC] Verifies all pip packages installed
├── power-monitor.service  [CONFIG] Systemd unit to run reader.py as daemon
├── data/
│   └── readings.db        [DATABASE] SQLite with WAL journaling
├── reports/
│   ├── 30day_load.png     [OUTPUT] Raw load chart
│   ├── hourly_avg.png     [OUTPUT] Peak usage by hour
│   ├── headroom_dist.png  [OUTPUT] Availability histogram
│   └── daily_heatmap.png  [OUTPUT] Load by day×hour
├── requirements.txt       [MANIFEST] 3 external dependencies (pyserial, matplotlib, numpy)
└── README.md              [DOCS] Quick-start guide
```

### Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER                                         │
│  ├─ plotter.py (4 chart types + summary stats)             │
│  └─ Outputs: PNG files + console reports                   │
└────────────────┬────────────────────────────────────────────┘
                 │ reads
                 v
┌─────────────────────────────────────────────────────────────┐
│  DATA ACCESS LAYER (Library)                                │
│  ├─ logger.py (DataLogger class)                           │
│  ├─ Methods: init_db(), insert_batch(), query_all(),       │
│  │            archive_old_data()                            │
│  └─ Handles: batch commits, WAL journaling, schema         │
└────────────────┬────────────────────────────────────────────┘
                 │ writes & commits
                 v
┌─────────────────────────────────────────────────────────────┐
│  DATABASE LAYER                                             │
│  ├─ readings.db (SQLite, WAL mode, synchronous=NORMAL)    │
│  └─ Schema: readings(id, timestamp, amps)                 │
└────────────────┬────────────────────────────────────────────┘
                 │ reads from
                 v
┌─────────────────────────────────────────────────────────────┐
│  ACQUISITION LAYER (Daemon)                                 │
│  ├─ reader.py (SerialReader class)                          │
│  ├─ Methods: connect(), parse_line(), run(),              │
│  │            flush(), shutdown()                           │
│  └─ Handles: serial I/O, timestamps, buffering,            │
│              graceful shutdown, reconnection               │
└────────────────┬────────────────────────────────────────────┘
                 │ reads from
                 v
┌─────────────────────────────────────────────────────────────┐
│  HARDWARE LAYER                                             │
│  ├─ RPICT3V1 board (UART on /dev/serial0)                 │
│  └─ CT clamp (measures current on 100A breaker)           │
└─────────────────────────────────────────────────────────────┘
```

### Code Organization Standard (PEP 8 + Clean Code)

All scripts follow this pattern for clean control flow:

```python
# reader.py — Example structure

from logger import DataLogger  # Import classes from other modules
import logging

class SerialReader:
    """Business logic and core functionality."""
    def __init__(self, ...):
        pass
    
    def connect(self):
        pass
    
    def run(self):
        pass

def main():
    """Entry point — orchestrates the control flow."""
    logger = logging.getLogger(__name__)
    logger.info("Starting power monitor daemon...")
    
    reader = SerialReader()
    reader.connect()
    reader.run()

if __name__ == "__main__":
    main()
```

**Standards applied:**
- **PEP 8**: Variable/function naming (snake_case), indentation (4 spaces), line length
- **PEP 20** (Zen of Python): "Explicit is better than implicit" — main() makes control flow obvious
- **SOLID — Single Responsibility**: Each class/module does one thing well
- **SOLID — Dependency Inversion**: `reader.py` imports `DataLogger` interface, not hardcoded DB calls
- **Clean Code**: Control flow is immediately clear by reading `main()` function first

**Your preference:** All functions/classes live in dedicated `.py` files, `main()` in each script orchestrates the flow. This makes the code:
- ✓ Easy to test (import classes independently)
- ✓ Easy to reuse (other scripts can import and use your classes)
- ✓ Easy to understand (read `main()` to see what the script does)
- ✓ Easy to extend (add new functions without touching existing ones)

---

### Design Patterns for Extensibility

**1. Module Abstraction (logger.py as library)**
- `logger.py` exports `DataLogger` class, all DB operations go through it
- Easy to swap SQLite for PostgreSQL, MySQL, InfluxDB — just reimplement `DataLogger` interface
- `reader.py` imports `from logger import DataLogger` — no hardcoded DB calls
- **Extension point:** Create `logger_postgres.py`, update import in `reader.py`

**2. Pluggable Reader Backends (reader.py design)**
- `SerialReader` class wraps port I/O, `parse_line()` is separate method
- Future: Add `ModbusReader`, `HTTPReader`, `CANBusReader` with same interface
- `reader.py` pattern:
  ```python
  class SerialReader:
      def parse_line(self, line):
          # Override this for different serial formats (Modbus, LoRaWAN, etc.)
          pass
  ```
- **Extension point:** Subclass `SerialReader` for new hardware (MQTT reader, REST API, GPIO direct)

**3. Configurable Thresholds (plotter.py design)**
- All magic numbers at top of file:
  ```python
  BREAKER_LIMIT = 100     # Change for different breaker
  EV_DRAW = 48            # Change for different EV
  ANALYSIS_HOURS = (21, 6)  # Change analysis window
  PERCENTILE = 95         # Change decision metric
  ```
- **Extension point:** Read from config file (YAML/JSON) instead of hardcoded values

**4. Batch Processing Pipeline (reader.py → logger.py → plotter.py)**
- `reader.py` writes continuous data in real-time
- `plotter.py` runs independently on schedule (cron job)
- Decoupled: can run multiple plotters, analyzers, exporters in parallel
- **Extension point:** Add `exporter.py` (export to InfluxDB), `alerter.py` (send SMS if over threshold), `web_dashboard.py` (Flask API)

**5. Logging & Monitoring (all scripts use `logging` module)**
- All errors go to syslog (visible in `journalctl`)
- Easy to add Prometheus metrics, StatsD, CloudWatch logging
- **Extension point:** Replace `logging.info()` calls with metrics exporter

### How to Add New Features

#### Example 1: Add Database Export to CSV

1. Add method to `logger.py`:
   ```python
   def export_csv(self, filepath):
       """Write all readings to CSV file."""
       df = pd.read_sql("SELECT * FROM readings", self.conn)
       df.to_csv(filepath, index=False)
   ```

2. Create new script `export.py`:
   ```python
   from logger import DataLogger
   db = DataLogger()
   db.export_csv("/home/pi/reports/readings.csv")
   ```

3. Add cron job to run daily
4. **No changes needed** to reader.py, plotter.py, or database schema ✓

#### Example 2: Add Email Alerts for Peak Load

1. Create new script `alerter.py`:
   ```python
   from logger import DataLogger
   import smtplib
   
   class PowerAlerter:
       def check_threshold(self, threshold_amps):
           db = DataLogger()
           readings = db.query_all()
           peak = max([r[2] for r in readings])
           if peak > threshold_amps:
               self.send_email(f"Peak load: {peak}A exceeded {threshold_amps}A")
   ```

2. Add cron job or run as separate daemon
3. **No database schema changes needed** ✓

#### Example 3: Add Multi-Circuit Monitoring

1. Extend database schema (modify `logger.py` init):
   ```python
   CREATE TABLE readings(
       id INTEGER PRIMARY KEY,
       timestamp TEXT,
       circuit_id TEXT,  # NEW: "main", "kitchen", "ev_outlet"
       amps REAL
   )
   ```

2. Update `reader.py` to handle multiple ports:
   ```python
   readers = [
       SerialReader("/dev/serial0", circuit_id="main"),
       SerialReader("/dev/serial1", circuit_id="kitchen"),
   ]
   ```

3. Update `plotter.py` to filter by circuit_id
4. **All layer boundaries maintained**, no architectural changes ✓

#### Example 4: Add Real-Time Web Dashboard

1. Create new script `dashboard.py` with Flask:
   ```python
   from flask import Flask
   from logger import DataLogger
   
   app = Flask(__name__)
   db = DataLogger()
   
   @app.route('/api/current')
   def get_current():
       readings = db.query_all()
       return jsonify(readings[-1])  # Latest reading
   ```

2. Run as separate systemd service on port 5000
3. **No changes to reader.py, logger.py, plotter.py** ✓

#### Example 5: Add InfluxDB Support

1. Create `logger_influx.py` implementing same interface as `logger.py`:
   ```python
   class DataLoggerInflux:
       def insert_batch(self, batch):
           # Write to InfluxDB instead of SQLite
           pass
   ```

2. Update `reader.py` import:
   ```python
   # from logger import DataLogger  # OLD
   from logger_influx import DataLoggerInflux as DataLogger  # NEW
   ```

3. `reader.py` code unchanged, different backend used ✓

### Extensibility Principles Applied

1. **Separation of Concerns**
   - reader.py = I/O and buffering
   - logger.py = persistence and queries
   - plotter.py = analysis and visualization
   - Each can be replaced independently

2. **Dependency Injection**
   - `reader.py` imports `DataLogger` from module, not hardcoded calls
   - Easy to swap implementations (SQLite → PostgreSQL, Serial → MQTT)

3. **Configuration Over Code**
   - Thresholds in plotter.py top-level constants
   - Can become YAML/JSON config file without code changes

4. **Stateless Scripts**
   - `plotter.py`, `alerter.py`, etc. read from DB, compute, output
   - No shared state = multiple instances can run in parallel safely

5. **Standard Logging**
   - All scripts use Python `logging` module
   - Easy to add monitoring, metrics, error tracking

### No Single Point of Failure

- **Reader daemon dies?** → Reconnect logic restarts it, systemd auto-restarts
- **DB locked?** → WAL mode allows concurrent readers while writing
- **Plotter takes 10 minutes?** → Doesn't block reader, runs on schedule
- **New feature needed?** → Add new script, don't modify existing ones

---

## Stage 1 — Serial Reader (`reader.py`)

**Purpose:** Continuously read current measurements from RPICT3V1 via UART and pass them to logger.

**Critical First Step — Serial Format Verification:**

Before deploying `reader.py`, you MUST verify the exact output format from RPICT3V1. Run on the Pi:
```bash
screen /dev/serial0 38400
```
Capture 10–20 sample lines and identify which token is RMS current (Amps). Use the provided `test_serial.py` diagnostic script to parse and label each column before deploying production code.

**Technical details:**
- Open `/dev/serial0` at 38400 baud (RPICT3V1 default)
- RPICT3V1 outputs space-delimited values; RMS current position determined from manual verification above
- Parse each line, extract RMS current as float, ignore invalid lines gracefully
- Attach timezone-aware ISO8601 timestamp in America/Los_Angeles (ZoneInfo handles DST automatically)
- Buffer readings in memory, pass to logger in batches (see Stage 2)
- Reconnect on serial errors (ConnectionError, timeout) with exponential backoff (1s → 10s)
- Install signal handlers (SIGTERM, SIGINT) to flush buffer and shutdown cleanly
- Rate-limit error logging to prevent syslog spam (max 1 error per 30s)
- Run as systemd service, survive reboots, log to syslog/journal

**Python dependencies:**
- `pyserial` — serial communication
- `pytz` / `zoneinfo` — timezone-aware timestamps (Python 3.9+)
- `logging` — syslog integration

**Code skeleton:**
```python
import serial
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from logger import DataLogger

class SerialReader:
    def __init__(self, port="/dev/serial0", baud=38400, buffer_size=100, flush_interval=10):
        self.port = port
        self.baud = baud
        self.buffer = []
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        self.last_flush = datetime.now()
        self.logger_obj = DataLogger()
        self.tz = ZoneInfo("America/Los_Angeles")
    
    def connect(self):
        """Open serial connection with retry logic."""
        retry_delay = 1
        while True:
            try:
                self.ser = serial.Serial(self.port, self.baud, timeout=2)
                logging.info(f"Serial connected at {self.baud} baud")
                return
            except serial.SerialException as e:
                logging.error(f"Serial error: {e}. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 10)
    
    def parse_line(self, line):
        """Extract RMS current (Amps) from RPICT3V1 output."""
        # Example: "V1 V2 V3 V4 V5" → return float(V2) if V2 is RMS current
        # Verify actual format with: screen /dev/serial0 38400
        try:
            tokens = line.strip().split()
            amps = float(tokens[1])  # Adjust index based on actual format
            return amps
        except (IndexError, ValueError):
            logging.warning(f"Failed to parse line: {line}")
            return None
    
    def run(self):
        """Main loop: read serial, buffer, and flush periodically."""
        self.connect()
        while True:
            try:
                line = self.ser.readline().decode("utf-8", errors="ignore")
                if line:
                    amps = self.parse_line(line)
                    if amps is not None:
                        timestamp = datetime.now(self.tz).isoformat()
                        self.buffer.append((timestamp, amps))
                
                # Flush buffer if full or flush_interval exceeded
                if len(self.buffer) >= self.buffer_size or \
                   (datetime.now() - self.last_flush).total_seconds() >= self.flush_interval:
                    self.flush()
            except Exception as e:
                logging.error(f"Read error: {e}")
                self.connect()
    
    def flush(self):
        """Write buffer to database."""
        if self.buffer:
            self.logger_obj.insert_batch(self.buffer)
            self.buffer.clear()
            self.last_flush = datetime.now()
    
    def shutdown(self, signum, frame):
        """Graceful shutdown on SIGTERM/SIGINT."""
        logging.info("Shutting down gracefully...")
        self.flush()  # Ensure final buffer is written
        self.ser.close()
        exit(0)

def main():
    """Entry point — orchestrates control flow."""
    import signal
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info("Starting power monitor daemon...")
    
    reader = SerialReader()
    signal.signal(signal.SIGTERM, reader.shutdown)
    signal.signal(signal.SIGINT, reader.shutdown)
    reader.run()

if __name__ == "__main__":
    main()
```

---

## Stage 2 — Logger (`logger.py`)

**Purpose:** SQLite wrapper that batches writes and manages the readings database.

**Technical details:**
- Create `/data/readings.db` with table `readings(id INTEGER PRIMARY KEY, timestamp TEXT, amps REAL)`
- Use WAL (Write-Ahead Logging) for safer concurrent writes on SD card
- Set `PRAGMA synchronous = NORMAL` to reduce write amplification without sacrificing durability on power loss
  - **Note:** This mode can lose up to ~1s of unflushed data on sudden power loss; acceptable for monitoring use case
- Batch inserts (100 rows or every 10s) to minimize journal flushes
- Auto-rotate/archive data older than 90 days (move to `readings_archived_YYYYMM.db`)
- Implement connection pooling and error recovery
- Monthly integrity check via cron: `PRAGMA integrity_check`
- Daily backup to `/home/pi/backups/readings.db.bak`

**Python dependencies:**
- `sqlite3` (built-in)

**Code skeleton:**
```python
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import logging

class DataLogger:
    def __init__(self, db_path="data/readings.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Create database and enable WAL + synchronous=NORMAL."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                amps REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON readings(timestamp)")
        conn.commit()
        conn.close()
        logging.info(f"Database initialized at {self.db_path}")
    
    def insert_batch(self, rows):
        """Insert batch of (timestamp, amps) tuples."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executemany(
                "INSERT INTO readings (timestamp, amps) VALUES (?, ?)",
                rows
            )
            conn.commit()
            logging.info(f"Inserted {len(rows)} rows")
        except Exception as e:
            logging.error(f"Insert failed: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def query_all(self, limit=10, order="DESC"):
        """Fetch recent or oldest readings."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            f"SELECT timestamp, amps FROM readings ORDER BY timestamp {order} LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()
        conn.close()
        return rows
    
    def archive_old_data(self, days=90):
        """Move readings older than N days to archived DB."""
        import os
        cutoff = (datetime.now(ZoneInfo("America/Los_Angeles")) - timedelta(days=days)).isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            # Get YYYYMM for archived DB name
            cutoff_dt = datetime.fromisoformat(cutoff)
            archive_name = f"readings_archived_{cutoff_dt.strftime('%Y%m')}.db"
            archive_path = os.path.join(os.path.dirname(self.db_path), archive_name)
            
            # Copy old rows to archive and delete from main
            archive_conn = sqlite3.connect(archive_path)
            archive_conn.execute("CREATE TABLE IF NOT EXISTS readings (id INTEGER, timestamp TEXT, amps REAL)")
            old_rows = conn.execute("SELECT * FROM readings WHERE timestamp < ?", (cutoff,)).fetchall()
            archive_conn.executemany(
                "INSERT OR IGNORE INTO readings VALUES (?, ?, ?)",
                old_rows
            )
            archive_conn.commit()
            conn.execute("DELETE FROM readings WHERE timestamp < ?", (cutoff,))
            conn.commit()
            archive_conn.close()
            logging.info(f"Archived {len(old_rows)} rows to {archive_name}")
        except Exception as e:
            logging.error(f"Archive failed: {e}")
            conn.rollback()
        finally:
            conn.close()

def main():
    """Entry point — test database functionality."""
    logging.basicConfig(level=logging.INFO)
    logger = DataLogger()
    logger.insert_batch([
        ("2026-04-12T10:30:45-07:00", 45.2),
        ("2026-04-12T10:30:46-07:00", 45.5),
    ])
    rows = logger.query_all(2)
    print(f"Test query returned: {rows}")

if __name__ == "__main__":
    main()
```

---

## Stage 3 — Plotter (`plotter.py`)

**Purpose:** Generate 4 matplotlib charts from readings database to analyze load patterns and EV charging feasibility.

**Configurable Parameters (edit at top of file):**
```python
# Configuration
BREAKER_LIMIT = 100         # Main breaker capacity (A)
EV_DRAW = 48                # Level 2 EV charger draw (A)
HEADROOM_THRESHOLD = BREAKER_LIMIT - EV_DRAW  # 52A
ANALYSIS_HOURS = (21, 6)    # 9 PM to 6 AM (overnight charging window)
PERCENTILE = 95             # 95th percentile for worst-case analysis
MIN_DATA_DAYS = 7           # Require at least 7 days of data before plotting
```

**Technical details:**
- Read all readings from SQLite; validate minimum data collection period (≥ 7 days recommended)
- Timestamps already in America/Los_Angeles, so no additional conversion needed
- **Data validation:** warn if gaps > 1 hour detected (indicates reader downtime); log % uptime in summary
- Chart 1 (Raw Load) — line plot of all samples with reference lines at 100A and 52A
- Chart 2 (Hourly Average) — bar chart of mean load per hour (0–23) across all days
- Chart 3 (Headroom Distribution) — histogram of available headroom (100A - load) with overlay showing % time ≥ 48A
- Chart 4 (Daily Heatmap) — 2D heatmap (day vs. hour) with color intensity = amperage
- Save outputs as high-res PNGs (dpi=150) to `/home/pi/reports/`
- **Key Decision Output:** Calculate and print clear pass/fail for Level 2 EV feasibility based on 95th percentile during analysis window
- Include summary statistics: min, max, mean, 95th percentile, % uptime, % time ≥ 48A headroom

**Python dependencies:**
- `matplotlib` — plotting
- `numpy` — stats and aggregation
- `sqlite3` (built-in) — data reading
- `pandas` (optional but recommended) — easy groupby operations

**Code skeleton:**
```python
import sqlite3
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo
import logging

class PowerPlotter:
    def __init__(self, db_path="data/readings.db", output_dir="reports", 
                 breaker_limit=100, ev_draw=48, analysis_hours=(21, 6), percentile=95):
        self.db_path = db_path
        self.output_dir = output_dir
        self.tz = ZoneInfo("America/Los_Angeles")
        self.breaker_limit = breaker_limit
        self.ev_draw = ev_draw
        self.headroom_threshold = self.breaker_limit - self.ev_draw  # 52A
        self.analysis_hours = analysis_hours
        self.percentile = percentile
    
    def load_data(self):
        """Fetch all readings from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT timestamp, amps FROM readings ORDER BY timestamp"
        )
        rows = cursor.fetchall()
        conn.close()
        
        timestamps = [datetime.fromisoformat(row[0]) for row in rows]
        amps = [row[1] for row in rows]
        return timestamps, amps
    
    def plot_raw_load(self, timestamps, amps):
        """Chart 1: Raw load over time with reference lines."""
        fig, ax = plt.subplots(figsize=(14, 6))
        ax.plot(timestamps, amps, linewidth=1, alpha=0.7, label="Load (A)")
        ax.axhline(self.breaker_limit, color="red", linestyle="--", linewidth=2, label=f"Breaker limit ({self.breaker_limit}A)")
        ax.axhline(self.headroom_threshold, color="orange", linestyle="--", linewidth=2, label=f"EV headroom threshold ({self.headroom_threshold}A)")
        ax.set_xlabel("Date & Time")
        ax.set_ylabel("Current (A)")
        ax.set_title("30-Day Power Load Profile")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.savefig(f"{self.output_dir}/01_raw_load.png", dpi=150, bbox_inches="tight")
        logging.info("Saved 01_raw_load.png")
    
    def plot_hourly_avg(self, timestamps, amps):
        """Chart 2: Average load by hour of day."""
        hourly_buckets = [[] for _ in range(24)]
        for ts, amp in zip(timestamps, amps):
            hour = ts.hour
            hourly_buckets[hour].append(amp)
        
        hourly_avg = [np.mean(bucket) if bucket else 0 for bucket in hourly_buckets]
        
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.bar(range(24), hourly_avg, color="steelblue", alpha=0.7)
        ax.axhline(self.headroom_threshold, color="orange", linestyle="--", linewidth=2, label=f"EV threshold ({self.headroom_threshold}A)")
        ax.set_xlabel("Hour of Day (Local Time)")
        ax.set_ylabel("Average Current (A)")
        ax.set_title("Typical Daily Load Pattern (Hourly Average)")
        ax.set_xticks(range(24))
        ax.legend()
        ax.grid(True, alpha=0.3, axis="y")
        fig.savefig(f"{self.output_dir}/02_hourly_avg.png", dpi=150, bbox_inches="tight")
        logging.info("Saved 02_hourly_avg.png")
    
    def plot_headroom_dist(self, amps):
        """Chart 3: Distribution of available headroom."""
        headroom = [self.breaker_limit - amp for amp in amps]
        pct_at_48a = 100 * sum(1 for h in headroom if h >= self.ev_draw) / len(headroom)
        
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.hist(headroom, bins=50, color="green", alpha=0.7, edgecolor="black")
        ax.axvline(self.ev_draw, color="red", linestyle="--", linewidth=2, label=f"EV requirement ({self.ev_draw}A)")
        ax.set_xlabel("Available Headroom (A)")
        ax.set_ylabel("Frequency")
        ax.set_title(f"Headroom Distribution ({pct_at_48a:.1f}% of time ≥ {self.ev_draw}A available)")
        ax.legend()
        ax.grid(True, alpha=0.3, axis="y")
        fig.savefig(f"{self.output_dir}/03_headroom_dist.png", dpi=150, bbox_inches="tight")
        logging.info("Saved 03_headroom_dist.png")
    
    def plot_heatmap(self, timestamps, amps):
        """Chart 4 (optional): Daily peak heatmap (day vs. hour)."""
        daily_hourly = {}
        for ts, amp in zip(timestamps, amps):
            day = ts.date()
            hour = ts.hour
            key = (day, hour)
            if key not in daily_hourly:
                daily_hourly[key] = []
            daily_hourly[key].append(amp)
        
        # Aggregate: mean per day-hour
        days = sorted(set(day for day, _ in daily_hourly.keys()))
        hours = range(24)
        matrix = np.zeros((len(days), 24))
        
        for i, day in enumerate(days):
            for j, hour in enumerate(hours):
                if (day, hour) in daily_hourly:
                    matrix[i, j] = np.mean(daily_hourly[(day, hour)])
        
        fig, ax = plt.subplots(figsize=(14, 8))
        im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto", interpolation="nearest")
        ax.set_xlabel("Hour of Day (Local Time)")
        ax.set_ylabel("Date")
        ax.set_title("Daily Peak Heatmap (Color = Amperage)")
        ax.set_xticks(range(24))
        ax.set_yticks(range(0, len(days), max(1, len(days)//10)))
        ax.set_yticklabels([str(days[i]) for i in ax.get_yticks() if i < len(days)])
        fig.colorbar(im, ax=ax, label="Current (A)")
        fig.savefig(f"{self.output_dir}/04_heatmap.png", dpi=150, bbox_inches="tight")
        logging.info("Saved 04_heatmap.png")
    
    def summarize(self, timestamps, amps):
        """Print summary statistics and EV feasibility decision."""
        headroom = [self.breaker_limit - a for a in amps]
        print(f"\n=== Summary Statistics ===")
        print(f"Min load: {min(amps):.1f}A, Max: {max(amps):.1f}A, Mean: {np.mean(amps):.1f}A")
        print(f"{self.percentile}th percentile: {np.percentile(amps, self.percentile):.1f}A")
        print(f"Min headroom: {min(headroom):.1f}A, Max: {max(headroom):.1f}A")
        pct_with_ev = 100*sum(1 for h in headroom if h >= self.ev_draw)/len(headroom)
        print(f"Time with ≥{self.ev_draw}A headroom: {pct_with_ev:.1f}%")
        
        # EV Feasibility Analysis
        print(f"\n=== EV Charging Feasibility ({self.analysis_hours[0]}:00–{self.analysis_hours[1]}:00 local time) ===")
        offpeak_amps = [a for ts, a in zip(timestamps, amps) if self.analysis_hours[0] <= ts.hour or ts.hour < self.analysis_hours[1]]
        if offpeak_amps:
            p_threshold = np.percentile(offpeak_amps, self.percentile)
            ev_compatible = (self.breaker_limit - p_threshold) >= self.ev_draw
            print(f"{self.percentile}th percentile load (off-peak): {p_threshold:.1f}A")
            print(f"Available headroom ({self.percentile}th percentile): {self.breaker_limit - p_threshold:.1f}A")
            print(f"Required for Level 2 EV: {self.ev_draw}A")
            print(f"\n*** DECISION: {('YES' if ev_compatible else 'NO')} - Panel {'CAN' if ev_compatible else 'CANNOT'} support Level 2 EV charger without upgrade ***")
    
    def run(self):
        """Generate all charts."""
        timestamps, amps = self.load_data()
        if not timestamps:
            logging.error("No data in database")
            return
        
        self.plot_raw_load(timestamps, amps)
        self.plot_hourly_avg(timestamps, amps)
        self.plot_headroom_dist(amps)
        self.plot_heatmap(timestamps, amps)
        self.summarize(timestamps, amps)

def main():
    """Entry point — orchestrates chart generation."""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info("Starting plotter analysis...")
    
    plotter = PowerPlotter(
        db_path="data/readings.db",
        output_dir="reports",
        breaker_limit=100,
        ev_draw=48,
        analysis_hours=(21, 6),
        percentile=95
    )
    plotter.run()

if __name__ == "__main__":
    main()
```

---

## Stage 4A — Utilities & Diagnostics

### `test_serial.py` — Serial Format Diagnostic

**Purpose:** Identify the exact column containing RMS current before deploying `reader.py`.

**Code skeleton:**
```python
import serial
import time

# Run on Raspberry Pi: python3 test_serial.py
# Examine output to identify which token is RMS current (Amps)

ser = serial.Serial("/dev/serial0", 38400, timeout=2)
print("Reading 20 samples from RPICT3V1...")
print("=" * 100)
for i in range(20):
    line = ser.readline().decode("utf-8", errors="ignore").strip()
    if line:
        tokens = line.split()
        print(f"Sample {i+1:2d}: ", end="")
        for j, token in enumerate(tokens):
            try:
                val = float(token)
                print(f"[{j}]={val:8.2f}  ", end="")
            except ValueError:
                print(f"[{j}]={token:8s}  ", end="")
        print()
    time.sleep(0.5)
ser.close()
print("=" * 100)
print("\nNote which column appears to be RMS current (typically 0-100A range)")
print("Update parse_line() index in reader.py accordingly")
```

### `init_db.py` — Database Initialization

**Purpose:** Create directory structure and initialize empty database with schema.

**Code skeleton:**
```python
import os
from logger import DataLogger

# Create directories
os.makedirs("/home/pi/power-monitor/data", exist_ok=True)
os.makedirs("/home/pi/power-monitor/reports", exist_ok=True)
os.makedirs("/home/pi/backups", exist_ok=True)

# Initialize database
logger = DataLogger("/home/pi/power-monitor/data/readings.db")
print("Database initialized at /home/pi/power-monitor/data/readings.db")

# Verify by inserting a test row
logger.insert_batch([("2026-04-12T10:00:00-07:00", 45.5)])
rows = logger.query_all(1)
if rows:
    print(f"Test insert successful: {rows[0]}")
else:
    print("ERROR: Test insert failed")
```

### `simulate_serial.py` — Mock RPICT3V1 Serial Data

**Purpose:** Simulate RPICT3V1 serial output without hardware for testing reader.py in isolation.

**Usage:**
```bash
# Terminal 1: Start mock serial data stream
python3 simulate_serial.py --rate 1 --baseline 20 --noise 2

# Terminal 2: Run reader.py to consume the mock data
python3 reader.py
```

**Key features:**
- Generates realistic daily power patterns (low overnight, peaks during day/evening)
- Configurable sampling rate, baseline load, and noise
- Outputs RPICT3V1-format space-delimited data
- Allows testing reader.py's serial I/O, buffering, and DB writes without hardware

**Arguments:**
- `--rate` — Sampling rate (Hz, default 1.0)
- `--baseline` — Baseline load (A, default 20)
- `--noise` — Noise variation (A, default 2)
- `--duration` — Run time in seconds (default infinite)

### `simulate_data.py` — Generate 30-Day Dataset

**Purpose:** Generate realistic 30-day power consumption data and inject directly into SQLite database. Perfect for testing logger.py + plotter.py without waiting for real hardware data collection.

**Usage:**
```bash
# Generate 30 days of data
python3 simulate_data.py

# With custom parameters
python3 simulate_data.py --days 30 --baseline 20 --noise 2

# Then generate charts (immediately):
python3 plotter.py
```

**Key features:**
- Creates 30 days of 1 Hz sampled power data (2.6M samples)
- Realistic daily patterns: low overnight (~15A), peaks daytime (~40-60A), evening spikes (~80A)
- Weekday vs. weekend variations
- Occasional appliance spikes (kettle, HVAC compressor, etc.)
- Inserts directly into `data/readings.db` via DataLogger
- Prints summary statistics and EV feasibility analysis
- Ready for immediate plotter.py visualization

**Arguments:**
- `--days` — Days to simulate (default 30)
- `--baseline` — Baseline load (A, default 20)
- `--noise` — Noise level (A, default 2)

### `status.py` — Health & Uptime Check

**Purpose:** Monitor reader health and data freshness. Run manually or via cron.

**Code skeleton:**
```python
from logger import DataLogger
from datetime import datetime
from zoneinfo import ZoneInfo
import os

logger = DataLogger("/home/pi/power-monitor/data/readings.db")
tz = ZoneInfo("America/Los_Angeles")

# Get most recent timestamp
rows = logger.query_all(1)
if not rows:
    print("ERROR: No data in database")
else:
    last_ts_str = rows[0][0]
    last_ts = datetime.fromisoformat(last_ts_str)
    now = datetime.now(tz)
    age_sec = (now - last_ts).total_seconds()
    
    print(f"Last reading: {last_ts_str}")
    print(f"Age: {age_sec:.0f}s ({age_sec/3600:.1f}h)")
    
    if age_sec > 3600:
        print("WARNING: Data is > 1 hour old. Reader may be stuck or crashed.")
    else:
        print("OK: Reader is active")
    
    # Check systemd service status
    os.system("systemctl status power-monitor.service | grep 'Active:'")
```

---

## Stage 4B — Automation & Deployment

### Systemd Service (`power-monitor.service`)

**Purpose:** Run `reader.py` as a daemon that survives reboots and auto-restarts on failure.

**Configuration skeleton:**
```ini
[Unit]
Description=EV Power Monitor - RPICT3V1 Serial Reader
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/power-monitor
ExecStart=/usr/bin/python3 /home/pi/power-monitor/reader.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=power-monitor

[Install]
WantedBy=multi-user.target
```

### Cron Job for Plotting

**Purpose:** Run `plotter.py` daily to regenerate charts from accumulated data.

**Schedule:**
```bash
# Run plotter.py every day at 2 AM local time
0 2 * * * /usr/bin/python3 /home/pi/power-monitor/plotter.py >> /var/log/power-monitor-plotter.log 2>&1

# Monthly database integrity check (first day of month at 1 AM)
0 1 1 * * sqlite3 /home/pi/power-monitor/data/readings.db "PRAGMA integrity_check;" >> /var/log/power-monitor-integrity.log 2>&1

# Daily database backup (3 AM, keeps rolling 7-day window)
0 3 * * * cp /home/pi/power-monitor/data/readings.db /home/pi/backups/readings.db.bak

# Weekly data archival (Sunday at 4 AM, archive data older than 90 days)
0 4 * * 0 /usr/bin/python3 -c "from logger import DataLogger; DataLogger().archive_old_data(90)"
```

### Directory Structure

```
/home/pi/power-monitor/
├── reader.py                      # Main serial reader (runs as systemd service)
├── logger.py                      # SQLite database wrapper
├── plotter.py                     # Chart generation
├── init_db.py                     # One-time DB initialization script
├── data/
│   └── readings.db                # SQLite database (auto-created by init_db.py)
├── reports/                       # Output PNG charts (auto-created)
│   ├── 01_raw_load.png
│   ├── 02_hourly_avg.png
│   ├── 03_headroom_dist.png
│   └── 04_heatmap.png
├── systemd/
│   └── power-monitor.service      # Systemd unit file
└── requirements.txt               # Python dependencies
```

## Python Implementation Stack

**Target environment:** Raspberry Pi (PiPro) running Python 3.9+

**Core dependencies:**
- `pyserial>=3.5` — serial communication
- `matplotlib>=3.5` — plotting
- `numpy>=1.21` — numerical operations
- `pytz>=2021.3` OR built-in `zoneinfo` (Python 3.9+)
- `sqlite3` (built-in) — database

**Optional:** pandas for easier data aggregation (not strictly necessary but recommended for large datasets)

**requirements.txt:**
```
pyserial>=3.5
matplotlib>=3.5
numpy>=1.21
```

**Development workflow:**
1. Create `/home/pi/power-monitor/` directory structure
2. Generate `init_db.py` to create empty database with schema
3. Generate `logger.py` — `DataLogger` class
4. Generate `reader.py` — `SerialReader` class (runs in infinite loop)
5. Generate `plotter.py` — `PowerPlotter` class (batch processing)
6. Generate `power-monitor.service` systemd unit
7. Deploy: copy all files to Pi, run `init_db.py`, start systemd service, verify with journalctl

## Deployment Checklist

### Pre-Deployment (on desktop/local machine)

- [ ] Clone/sync project to your desktop development machine
- [ ] Review and finalize all Python source files (`reader.py`, `logger.py`, `plotter.py`, etc.)
- [ ] Ensure `requirements.txt` is complete and tested locally (optional: test in venv)
- [ ] Create systemd unit file: `power-monitor.service` with correct paths and user (`pi`)

### On-Pi Initial Setup

1. **SSH into Pi:**
   ```bash
   ssh pi@192.168.4.50
   ```

2. **Create project directory:**
   ```bash
   mkdir -p /home/pi/power-monitor
   cd /home/pi/power-monitor
   ```

3. **Copy files from desktop to Pi** (from your desktop machine):
   ```bash
   scp reader.py logger.py plotter.py init_db.py test_serial.py status.py pi@192.168.4.50:/home/pi/power-monitor/
   scp requirements.txt pi@192.168.4.50:/home/pi/power-monitor/
   scp power-monitor.service pi@192.168.4.50:/tmp/
   ```

4. **Install dependencies** (on Pi):
   ```bash
   cd /home/pi/power-monitor
   pip install -r requirements.txt
   ```

### Serial Format Verification (Critical)

5. **Test serial connection** (on Pi):
   ```bash
   python3 test_serial.py
   ```
   - Capture output and identify which token is RMS current (usually 0–100A)
   - **Edit `reader.py` parse_line() to use correct column index**
   - Run again to confirm

### Database Initialization

6. **Initialize database** (on Pi):
   ```bash
   python3 init_db.py
   ```
   - Verify `data/readings.db` was created
   - Verify test insert succeeded

### Service Deployment

7. **Install systemd service** (on Pi):
   ```bash
   sudo cp /tmp/power-monitor.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable power-monitor.service
   sudo systemctl start power-monitor.service
   ```

8. **Verify service is running** (on Pi):
   ```bash
   systemctl status power-monitor.service
   journalctl -u power-monitor -n 20 -f  # Monitor live logs
   ```

9. **Check data is collecting** (on Pi, after ~30s):
   ```bash
   python3 -c "from logger import DataLogger; print(DataLogger().query_all(5))"
   ```
   - Should show 5 recent readings with timestamps and amps

### Cron Jobs & Automation

10. **Add cron jobs** (on Pi):
    ```bash
    crontab -e
    ```
    Paste (or copy from plan.md Cron Jobs section):
    ```
    0 2 * * * /usr/bin/python3 /home/pi/power-monitor/plotter.py >> /var/log/power-monitor-plotter.log 2>&1
    0 1 1 * * sqlite3 /home/pi/power-monitor/data/readings.db "PRAGMA integrity_check;" >> /var/log/power-monitor-integrity.log 2>&1
    0 3 * * * cp /home/pi/power-monitor/data/readings.db /home/pi/backups/readings.db.bak
    0 4 * * 0 /usr/bin/python3 -c "from logger import DataLogger; DataLogger().archive_old_data(90)"
    ```

11. **Create backup directory** (on Pi):
    ```bash
    mkdir -p /home/pi/backups
    ```

### Post-Deployment Verification

12. **Monitor for 24–48 hours:**
    - Check systemd logs regularly: `journalctl -u power-monitor -n 50`
    - Run status check: `python3 status.py`
    - Verify data is being collected: `python3 -c "from logger import DataLogger; print(DataLogger().query_all(100))"`

13. **Run plotter manually** (after ~7 days of data):
    ```bash
    python3 plotter.py
    ```
    - Check output PNGs in `reports/` directory
    - Review summary statistics and EV feasibility decision

14. **Troubleshooting tips:**
    - If no data: check serial connection with `test_serial.py`
    - If service keeps crashing: check `journalctl` for error details
    - If plotter fails: verify timestamps are ISO8601 and parseable
    - If DB is corrupted: restore from `/home/pi/backups/readings.db.bak`

---

A Level 2 charger on a 50A circuit draws up to 48A continuous.

From the data, determine:
1. What is the average load during 9pm–6am (likely charging window)?
2. What is the 95th percentile load during that window (worst case)?
3. Does `100A - 95th_percentile_load >= 48A`?

If yes — the panel can support a Level 2 charger without an upgrade during off-peak hours.
If no — either a load management device (smart EVSE with current sensing) or a panel upgrade is needed.

---

## Next Steps

## Decisions

- **Sampling rate:** default 1 Hz (high resolution). Alternatives: 5s or 10s to reduce write frequency and SD wear if desired.
- **Buffering / commit policy:** buffer in memory and commit in batches (recommended: every 10 seconds or after 100 rows) to reduce SD card wear.
- **Timestamps:** store timezone-aware ISO8601 timestamps in America/Los_Angeles (local CA time, handles PST/PDT)
- **Data storage:** `data/readings.db` (SQLite) with schema `readings(id INTEGER PRIMARY KEY, timestamp TEXT, amps REAL)`.
- **SQLite tuning:** use WAL journaling and `PRAGMA synchronous = NORMAL` to balance durability and write amplification.
- **Service user & paths:** run `power-monitor.service` as user `pi`; output reports to `/home/pi/reports/`.
- **Thresholds & analysis window:** breaker = 100A, EV draw = 48A (headroom threshold 52A), analysis window 21:00–06:00 local time for the 95th-percentile test.

## Next Steps (project TODO)

- [x] Decide sampling & buffering — sampling, buffering/commit policy, timezone decided (see Decisions above)
- [ ] Implement `reader.py` — Serial reader: open `/dev/serial0` at 38400, parse RMS current (amps), attach America/Los_Angeles timestamp, emit to logger buffer
- [ ] Implement `logger.py` — SQLite wrapper at `data/readings.db` with schema `readings(id INTEGER PRIMARY KEY, timestamp TEXT, amps REAL)`. Use WAL and `synchronous=NORMAL`, batch commits.
- [ ] Initialize DB and migrations — create `data/` and initialize SQLite DB with PRAGMAs and `readings` table
- [ ] Create `power-monitor.service` — systemd unit to run `reader.py` as `pi`, ensure restart on failure
- [ ] Scaffold `plotter.py` — generate charts (raw, hourly avg, headroom distribution) and output PNGs to `/home/pi/reports/`
- [ ] Deploy & test on Pi — deploy scripts, verify serial output format with `screen /dev/serial0 38400`, run service, validate data collection and plots
