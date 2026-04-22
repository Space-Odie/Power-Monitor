# EV Power Monitor — Learner's Guide

A beginner-friendly walkthrough of how this project works, why it's built the way it is, and what every file and function does.

---

## What Does This Project Actually Do?

This project turns a Raspberry Pi into a power meter. A small hardware board (RPICT3V1) clamps onto your home's electrical panel and measures how many amps of current are flowing through your breaker at any given moment. The Pi reads that number once per second, stores it in a database, and over 30 days builds up a complete picture of your home's power usage.

The end goal is simple: figure out whether you have enough spare electrical capacity to charge an electric vehicle at home without overloading your panel.

---

## Why Is the Code Split Into Multiple Files?

If you've only written basic programs, you might be used to putting everything in one file. This project uses multiple files on purpose, and here's why:

Imagine a restaurant. The kitchen doesn't also seat customers, and the waiter doesn't also cook. Each person has one job. If the chef quits, you hire a new chef — the waiters don't need to change.

This project works the same way:

- `reader.py` — listens to the hardware (the "sensor guy")
- `logger.py` — saves data to the database (the "record keeper")
- `plotter.py` — reads the database and makes charts (the "analyst")

Each file can be changed, tested, or replaced without touching the others. This is called **Separation of Concerns** — one of the most important ideas in software engineering.

---

## The Big Picture: How Data Flows

```
[Your Breaker]
      |
      | (electricity flowing)
      |
[CT Clamp Hardware]
      |
      | (sends a signal)
      |
[RPICT3V1 Board on Pi GPIO]
      |
      | (serial port: /dev/serial0)
      |
[reader.py] ← reads the signal once per second
      |
      | (buffers 100 readings in memory)
      |
[logger.py] ← writes to database every 10 seconds
      |
      | (stores to SQLite file)
      |
[data/readings.db] ← the database file on your SD card
      |
      | (read when you run plotter.py)
      |
[plotter.py] ← generates 4 PNG chart files
      |
[reports/] ← your output charts
```

---

## Core Concept: What Is a Class?

Several files use something called a **class**. If you haven't seen this before, think of a class as a blueprint.

A blueprint for a house tells you how many rooms it has, where the doors go, and how the plumbing works. You can build many houses from one blueprint, and each house has its own rooms even though they follow the same design.

In Python:

```python
class SerialReader:
    def __init__(self, port="/dev/serial0"):
        self.port = port      # This house's address
        self.buffer = []      # This house's storage room
```

`SerialReader` is the blueprint. When `reader.py` runs `main()`, it builds one actual `SerialReader` object from that blueprint and uses it to do real work.

---

## Core Concept: What Is a Method?

A **method** is a function that belongs to a class. It's a specific action that the object knows how to do.

```python
class SerialReader:
    def connect(self):      # "connect" is a method
        ...
    
    def flush(self):        # "flush" is another method
        ...
```

Think of it like a dog. A dog (class) knows how to `sit()`, `fetch()`, and `bark()`. Those are its methods — actions it can perform.

---

## File-by-File Breakdown

---

### `logger.py` — The Record Keeper

**What it does:** Manages the database. Every other file that needs to save or read data goes through this file. Nothing talks to the database directly except `logger.py`.

**Why it's isolated:** If you ever wanted to switch from SQLite to a different database (like PostgreSQL), you'd only need to change `logger.py`. Everything else stays the same.

**The class: `DataLogger`**

| Method | What it does |
|---|---|
| `__init__(db_path)` | Opens (or creates) the database file when you first create a DataLogger object |
| `_init_db()` | Creates the `readings` table if it doesn't exist yet. The underscore means "internal use only" |
| `insert_batch(rows)` | Takes a list of readings and saves them all at once. Faster than saving one at a time |
| `query_all(limit, order)` | Fetches the most recent (or oldest) N readings from the database |
| `query_by_date_range(start, end)` | Fetches all readings between two timestamps — used by plotter.py |
| `get_row_count()` | Returns the total number of readings stored |
| `archive_old_data(days)` | Moves readings older than N days into a separate archive file to keep the main database lean |
| `integrity_check()` | Asks SQLite to verify the database file isn't corrupted |

**What is SQLite?**
SQLite is a database that lives in a single file (`readings.db`). You don't need to install a database server — it just works. Think of it like a very organized spreadsheet that Python can query instantly even with millions of rows.

**What is WAL mode?**
WAL stands for Write-Ahead Logging. It's a setting that makes SQLite safer on a Raspberry Pi SD card. Without it, a sudden power loss (like unplugging the Pi) could corrupt the database. WAL mode makes this much less likely.

---

### `reader.py` — The Sensor Guy

**What it does:** Runs continuously as a background process (called a daemon). It listens to the RPICT3V1 board over the serial port, reads a current value once per second, and periodically saves batches of readings to the database via `logger.py`.

**Why it buffers instead of saving immediately:**
SD cards have a limited number of write cycles. If you write to the card 86,400 times per day (once per second), you'll wear it out faster. Instead, `reader.py` collects 100 readings in memory, then saves them all at once. Same data, much less wear.

**The class: `SerialReader`**

| Method | What it does |
|---|---|
| `__init__(port, baud, buffer_size, flush_interval)` | Sets up the reader with its configuration. Does not connect yet |
| `connect()` | Opens the serial port. If it fails, it retries up to 5 times, waiting longer between each attempt (1s, 2s, 4s, 8s, 10s). This is called exponential backoff |
| `parse_line(line)` | Takes one raw line of text from the serial port and extracts the current value (in Amps). Returns None if the line is garbage |
| `run()` | The main loop. Reads lines forever, parses them, buffers them, and flushes when needed |
| `_should_flush()` | Returns True if the buffer is full OR if enough time has passed since the last flush |
| `flush()` | Sends the buffered readings to `DataLogger.insert_batch()` and clears the buffer |
| `shutdown(signum, frame)` | Called automatically when the Pi shuts down or the service stops. Flushes the remaining buffer and closes the serial port cleanly |

**What is a serial port?**
Serial ports are how computers communicate with simple hardware. The RPICT3V1 sends a line of text every second containing the current measurements. `/dev/serial0` is the name of the serial port on the Raspberry Pi's GPIO header.

**What is a signal handler?**
When you run `sudo systemctl stop power-monitor`, Linux sends a SIGTERM signal to the program — essentially a polite "please stop." The signal handler (`shutdown()`) catches that message and makes sure the buffer is flushed before the program exits, so no data is lost.

---

### `plotter.py` — The Analyst

**What it does:** Reads all the data from the database and generates four PNG chart files. You run this manually (or via a daily cron job) to see your power usage patterns and get a yes/no answer on EV charger feasibility.

**The class: `PowerPlotter`**

| Method | What it does |
|---|---|
| `__init__(db_path, output_dir, tz)` | Sets up the plotter with paths and timezone |
| `plot_daily_distribution(days)` | Chart 1: Shows average, min, and max current for each hour of the day. Highlights the overnight window in green |
| `plot_timeline(days)` | Chart 2: Shows every reading plotted over time — a full picture of your usage over the month |
| `plot_peak_analysis(days)` | Chart 3: Filters to overnight hours only, shows a histogram of how the current is distributed, and prints the EV feasibility decision |
| `plot_weekly_pattern(days)` | Chart 4: Shows average current by day of the week. Weekends are colored differently |
| `_print_ev_feasibility(p95)` | Prints the final pass/fail decision. Takes the 95th percentile overnight load, adds 48A for the EV charger, and checks if the total is under 100A |

**What is a percentile?**
If you have 1,000 readings and sort them from smallest to largest, the 95th percentile is the value at position 950. It means "95% of your readings were below this number." We use the 95th percentile instead of the maximum because we want to plan for typical worst-case behavior, not a rare one-second spike.

**What is a histogram?**
The peak analysis chart uses a histogram. Imagine sorting your readings into buckets: "how many readings were between 10–15A? Between 15–20A?" etc. The histogram shows which buckets are tallest — where your power usage spends most of its time.

---

### `init_db.py` — The Setup Script

**What it does:** A one-time setup script. Creates the `data/`, `reports/`, and `backups/` directories and initializes the database. Safe to run multiple times — it won't overwrite existing data.

**When to use it:** First time you deploy on the Pi, or to verify your setup is complete with `--check`.

| Function | What it does |
|---|---|
| `create_directories(base_path)` | Creates data/, reports/, and backups/ folders if they don't exist |
| `initialize_database(db_path)` | Creates a DataLogger object (which triggers table creation) and runs an integrity check |
| `verify_setup(base_path, db_path)` | Checks that all directories and the database file exist. Used by --check mode |
| `main()` | Orchestrates the above three functions in order |

---

### `status.py` — The Health Monitor

**What it does:** A quick diagnostic tool you can run at any time to see if the system is working. Shows when the last reading was taken, how many readings are in the database, and whether the daemon is running.

| Method | What it does |
|---|---|
| `get_database_info()` | Reads the database to get total row count, file size, and most recent reading |
| `get_daemon_status()` | Asks systemd (the Linux service manager) if power-monitor.service is running |
| `calculate_collection_rate()` | Divides total readings by days elapsed to estimate how many readings per day are being collected |
| `check_all()` | Runs all three checks above and stores results |
| `display_text(verbose)` | Prints results in a human-readable format |
| `display_json()` | Prints results as JSON, useful for scripts or dashboards |

---

### `test_serial.py` — The Hardware Diagnostic

**What it does:** A one-time diagnostic you run before deploying `reader.py`. It opens the serial port, reads 20 lines from the RPICT3V1, and displays each column labeled with its value and range. This helps you identify which column index contains the RMS current so you can configure `parse_line()` correctly.

**Why this matters:** The RPICT3V1 outputs multiple values per line (voltages, currents, etc.). Without knowing which column is which, `reader.py` might read the wrong value. This script eliminates the guesswork.

| Function | What it does |
|---|---|
| `read_serial_samples(port, baud, count, timeout)` | Opens the serial port and reads N lines, printing each one as it arrives |
| `analyze_samples(lines)` | Parses the collected lines, displays each column's range, and flags which columns look like current vs. voltage |
| `main()` | Handles command-line arguments and runs the above functions |

---

### `simulate_data.py` — The Test Data Generator

**What it does:** Generates 30 days of fake but realistic power consumption data and inserts it directly into the database. Lets you test `plotter.py` without waiting for a month of real data.

**The class: `PowerDataSimulator`**

| Method | What it does |
|---|---|
| `get_load_for_time(dt)` | Given a timestamp, returns a realistic current value based on time of day and day of week. Overnight is low, evening is high, weekends are slightly higher |
| `generate_data()` | Loops through every second of the simulation period and calls `get_load_for_time()` for each one, inserting in batches of 1000 |
| `summarize()` | After generation, prints statistics and the EV feasibility answer for the simulated data |

---

### `simulate_serial.py` — The Hardware Mock

**What it does:** Simulates the RPICT3V1 serial output without real hardware. Useful for testing `reader.py`'s serial reading and buffering logic when you don't have the board connected.

**The class: `MockRPICT3V1`**

| Method | What it does |
|---|---|
| `get_realistic_load()` | Same daily pattern logic as the data simulator — returns a current value based on the current time of day |
| `generate_line()` | Formats a fake RPICT3V1 output line with simulated voltage and current values |
| `run(duration_seconds)` | Streams fake serial lines to stdout at the specified rate indefinitely (or for a set duration) |

---

### `power-monitor.service` — The Systemd Unit

**What it does:** Not Python — this is a configuration file for Linux's service manager (systemd). It tells the Pi how to run `reader.py` as a background service that starts automatically on boot and restarts itself if it crashes.

**Key settings explained:**

| Setting | What it means |
|---|---|
| `After=network.target` | Don't start until the network is up |
| `Restart=on-failure` | If reader.py crashes, restart it after 10 seconds |
| `User=pi` | Run as the `pi` user, not as root (safer) |
| `MemoryMax=100M` | If the process uses more than 100MB of RAM, kill it (prevents runaway memory leaks) |
| `ProtectSystem=strict` | The process can't write to system directories — only the paths listed in ReadWritePaths |
| `NoNewPrivileges=true` | The process can't escalate to root-level access |

---

## Why Structure Code This Way?

Here's a summary of the design principles used, explained simply:

**Single Responsibility**
Each file does one thing. `logger.py` doesn't make charts. `plotter.py` doesn't touch the serial port. If something breaks, you know exactly where to look.

**Dependency Inversion**
`reader.py` doesn't talk to SQLite directly. It calls `DataLogger.insert_batch()`. This means you could swap out the entire database engine without touching `reader.py` at all.

**Graceful Degradation**
If the serial port disconnects, `reader.py` doesn't crash — it retries with increasing wait times. If it gets shut down, it flushes the buffer first. The system fails safely.

**Separation of Layers**
The project has four distinct layers: hardware → reader → database → plotter. Each layer only talks to the one directly below it. This mirrors how professional systems are designed — whether it's enterprise software or embedded systems.

---

## Glossary

| Term | Plain English |
|---|---|
| Class | A blueprint for creating objects with shared behavior |
| Method | A function that belongs to a class |
| Instance | One actual object built from a class blueprint |
| Buffer | Temporary memory storage before writing to disk |
| Daemon | A background process that runs continuously |
| Serial port | A communication channel between the Pi and hardware |
| SQLite | A file-based database that requires no server |
| WAL mode | A SQLite safety setting that prevents corruption on power loss |
| Percentile | A statistical threshold — "95% of values were below this" |
| Systemd | Linux's service manager — starts, stops, and monitors programs |
| Signal handler | Code that runs when the OS sends a stop/interrupt message to a program |
| Exponential backoff | Waiting longer and longer between retries after a failure |
