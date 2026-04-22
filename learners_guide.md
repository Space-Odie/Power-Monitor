# EV Power Monitor — Implementation Deep Dive

Technical walkthrough of design decisions and implementation details.

---

## Architecture

Three-layer separation:

1. **Acquisition** (`reader.py`) — Continuous serial I/O with in-memory buffering
2. **Persistence** (`logger.py`) — SQLite abstraction with batch operations
3. **Analysis** (`plotter.py`) — Full dataset load, aggregation, visualization

Each layer is independent. `reader.py` never queries the database; it only writes. `plotter.py` never writes; it only reads. This decoupling makes testing and modifications easier.

---

## `reader.py` — The Acquisition Loop

### Buffering Strategy

Why buffer? Serial I/O and disk writes are both slow. Without buffering:
- Read 1 sample/sec from serial (fast)
- Write 1 sample/sec to disk (slow, creates 86,400 I/O ops/day)

With buffering:
- Accumulate ~100 samples in RAM (~100 seconds of data)
- Flush all 100 to disk in one transaction (1 I/O op per flush)
- Result: ~900 I/O ops/day instead of 86,400 (100x improvement)

The buffer is just a Python list. When it hits 100 items, we dump it to the database in a single batch transaction.

### Parse Function and Formatting

```python
def parse_line(self, line):
    try:
        parts = line.split(',')
        current = float(parts[2].split(':')[1].strip().rstrip('A'))
        now = datetime.now(ZoneInfo("America/Los_Angeles"))
        return {"timestamp": now.isoformat(), "current": current}
    except:
        return None
```

Assumes fixed format from RPICT3V1: `"RMS Voltage: 123.4V, RMS Current: 25.3A"`

We split by comma, extract column 2, parse the float, strip the unit. If parsing fails, return None and skip.

**Key choice:** Timestamp at read time, not flush time. With a 100-sample buffer, max timestamp error is ~100 seconds, acceptable for 1Hz data. The alternative (requesting timestamps from hardware) doesn't work—RPICT3V1 doesn't provide them.

### Connection with Exponential Backoff

```python
def connect(self):
    wait_time = 1
    while True:
        try:
            self.connection = serial.Serial(port=self.port, baudrate=self.baud)
            return
        except:
            time.sleep(wait_time)
            wait_time = min(wait_time * 2, 30)
```

If the serial port fails to open (device unplugged, enumeration delay, etc.), retry with exponential backoff: 1s, 2s, 4s, 8s, 16s, 30s (max). This handles transient failures without hammering the device or filling logs.

### Main Loop

```python
def run(self):
    self.connect()
    while True:
        try:
            line = self.connection.readline().decode('utf-8').strip()
            if line:
                reading = self.parse_line(line)
                if reading:
                    self.buffer.append(reading)
                    if len(self.buffer) >= 100:
                        self.flush()
        except:
            time.sleep(1)
```

The `readline()` call blocks with a 1-second timeout. This means the loop checks roughly once/second, which is responsive enough for SIGTERM shutdown signals while avoiding busy-spinning.

---

## `logger.py` — Database Layer

### Batch Insert Performance

```python
def insert_batch(self, rows):
    conn = sqlite3.connect(self.db_path)
    cursor = conn.cursor()
    
    for row in rows:
        cursor.execute("INSERT INTO readings (timestamp, current) VALUES (?, ?)",
                      (row["timestamp"], row["current"]))
    
    conn.commit()  # One commit for all 100 rows
    conn.close()
```

The loop adds statements to the transaction; `commit()` at the end saves everything atomically.

**Why this matters:**
- Naive approach (commit after each insert): 86,400 commits/day = 86,400 disk syncs
- Batch approach (one commit per ~100 inserts): ~900 commits/day = ~900 disk syncs

Each `commit()` in SQLite triggers a WAL checkpoint, which is expensive. Batching reduces this by ~100x.

### Queries

**`query_all()`:** Full table scan ordered by timestamp. With 2.6M rows, takes a few seconds to load into RAM, one-time cost.

**`query_by_date_range()`:** `WHERE timestamp >= ? AND timestamp <= ?` filtering. Uses `?` placeholders to prevent SQL injection.

**`get_row_count()`:** `SELECT COUNT(*)` — quick way to check progress.

**`archive_old_data(days=90)`:** Delete readings older than 90 days. With 1Hz sampling, you accumulate ~260MB/month. Without archival, a year of data is 3.1GB. This keeps it manageable.

---

## `plotter.py` — Analysis

### Load All Data

```python
def _load_data(self):
    conn = sqlite3.connect(self.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, current FROM readings ORDER BY timestamp")
    rows = cursor.fetchall()
    conn.close()
    
    self.timestamps = [row[0] for row in rows]
    self.currents = [row[1] for row in rows]
```

Full dataset load into two lists. For 2.6M rows, this is a few seconds. Could use numpy arrays for faster math operations, but lists are sufficient here.

### Visualizations

**Daily Distribution** — Raw plot of all current values over time. Shows overall behavior.

**Hourly Average** — Group readings by hour (0-23), calculate mean for each hour. Shows daily rhythm. With 30 days of data, each hour bucket has ~30 samples.

```python
hourly_avgs = {}
for timestamp, current in zip(self.timestamps, self.currents):
    hour = datetime.fromisoformat(timestamp).hour
    if hour not in hourly_avgs:
        hourly_avgs[hour] = []
    hourly_avgs[hour].append(current)
```

### The Core Calculation

```python
p95 = np.percentile(self.currents, 95)
max_load = p95 + 48  # EV draw
if max_load <= 100:  # Breaker limit
    print(f"YES: margin {100 - max_load:.1f}A")
else:
    print(f"NO: exceeds by {max_load - 100:.1f}A")
```

**Why 95th percentile and not max?** The absolute maximum includes one-off spikes (compressor startup, oven pre-heat) that don't represent normal operation. The 95th percentile says "this is the load we normally see on bad days." Conservative estimate for planning.

**Why add 48A fixed?** EV chargers draw a set amperage. If set to 48A, it will draw that whenever active. So the question is: "At worst-case normal load, can we also draw 48A without exceeding 100A?"

---

## Design Decisions

### 1Hz Sampling

Current doesn't change rapidly on inductive loads. 1Hz captures daily patterns without massive data. 1 sec × 86,400 sec/day × 30 days = 2.6M rows ≈ 260MB. Good trade-off.

### 100-Sample Buffer

Arbitrary but reasonable. Balances efficiency with data loss risk. Could be tuned based on reliability requirements.

### SQLite, Not Postgres

Single host, single writer (reader.py), multiple readers (plotter.py). SQLite with WAL mode is simpler and sufficient. Postgres would be overkill.

### Percentile-Based Decision

More robust than absolute max (outliers dominate), more conservative than average (hides worst days). 95th is good middle ground.

### 90-Day Retention

30+ days needed for analysis. Older data doesn't affect the EV decision. Archival keeps DB manageable.

---

## Extending

**New chart:** Add method to PowerPlotter, extract data from `self.timestamps` and `self.currents`, matplotlib plot, save PNG.

**Change sampling rate:** Modify hardware connection in `reader.py`, adjust `parse_line()` if format changes, optionally adjust buffer size.

**Restrict analysis window:** Filter data before percentile calculation. Example, off-peak only (9pm-6am):

```python
offpeak_currents = [c for t, c in zip(self.timestamps, self.currents) 
                    if datetime.fromisoformat(t).hour in list(range(21,24)) + list(range(0,6))]
p95_offpeak = np.percentile(offpeak_currents, 95)
```

---

## Known Limitations

1. **Single writer** — SQLite doesn't handle concurrent writes. `reader.py` is the only writer. This is by design and acceptable.

2. **Timestamp drift** — We add timestamps at read time. If system clock drifts, timestamps are off. NTP would fix this.

3. **Silent data loss** — Malformed serial data is dropped without logging. For production, log to file.

4. **No checksum** — RPICT3V1 doesn't provide checksums. Rare but possible bit corruption on the serial line isn't detected.

5. **Power-loss durability** — Database could corrupt if power fails during write. SQLite + WAL is pretty resilient, but not crash-proof. fsync or journaled filesystem would help.

All acceptable trade-offs for a home monitoring system.
