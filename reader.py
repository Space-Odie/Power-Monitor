#!/usr/bin/env python3
"""
reader.py — Serial reader daemon for RPICT3V1 current transformer board.

Continuously reads power consumption data from RPICT3V1 via serial port,
buffers readings in memory, and flushes to database periodically.

Usage:
    # Manual testing (run in foreground)
    python3 reader.py
    
    # With systemd (runs as daemon on startup)
    sudo systemctl start power-monitor.service

Environment variables:
    SERIAL_PORT — Serial port path (default: /dev/serial0)
    SERIAL_BAUD — Baud rate (default: 38400)
    BUFFER_SIZE — Batch size before flushing (default: 100)
    FLUSH_INTERVAL — Seconds between flushes (default: 10)

Configuration:
    Edit main() function to customize port, baud rate, buffer settings.
"""

try:
    import serial
except ImportError:
    serial = None  # Allow testing without hardware

import signal
import time
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from logger import DataLogger

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)


class SerialReader:
    """Continuously reads current measurements from RPICT3V1 serial port."""
    
    def __init__(self, port="/dev/serial0", baud=38400, buffer_size=100, flush_interval=10):
        """
        Initialize serial reader.
        
        Args:
            port: Serial port path (default: /dev/serial0)
            baud: Baud rate (default: 38400)
            buffer_size: Flush buffer after N rows (default: 100)
            flush_interval: Flush buffer after N seconds (default: 10)
        """
        self.port = port
        self.baud = baud
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        self.buffer = []
        self.last_flush = datetime.now()
        self.logger_db = DataLogger()
        self.tz = ZoneInfo("America/Los_Angeles")
        self.ser = None
        self.running = True
        self.error_count = 0
        self.last_error_time = None
        self.error_log_interval = 30  # Max 1 error per 30 seconds
    
    def connect(self):
        """
        Open serial connection with exponential backoff retry logic.
        
        Raises:
            RuntimeError: If connection fails after multiple retries
        """
        if serial is None:
            logger.warning("pyserial not installed - connection will fail on real hardware")
            return
        
        retry_delay = 1
        max_delay = 10
        max_retries = 5
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                self.ser = serial.Serial(self.port, self.baud, timeout=2)
                logger.info(f"Serial connection established: {self.port} @ {self.baud} baud")
                self.error_count = 0
                return
            
            except serial.SerialException as e:
                retry_count += 1
                logger.warning(
                    f"Serial connection failed (attempt {retry_count}/{max_retries}): {e}. "
                    f"Retrying in {retry_delay}s..."
                )
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_delay)
        
        raise RuntimeError(f"Failed to connect to {self.port} after {max_retries} attempts")
    
    def parse_line(self, line):
        """
        Extract RMS current (Amps) from RPICT3V1 output line.
        
        RPICT3V1 outputs space-delimited values. The RMS current column index
        depends on the device configuration. Run test_serial.py to identify it.
        
        Common format: V1 V2 V3 I1 I2 I3 (where I1 = RMS current in Amps)
        
        Args:
            line: Raw serial output line (string)
        
        Returns:
            float: RMS current in Amps, or None if parse fails
        """
        try:
            tokens = line.strip().split()
            if not tokens:
                return None
            
            # Index 3 is RMS current (verified with test_serial.py)
            # CUSTOMIZE THIS based on test_serial.py output
            amps = float(tokens[3])
            return amps
        
        except (IndexError, ValueError) as e:
            # Log parse errors but don't spam
            now = datetime.now()
            if (self.last_error_time is None or 
                (now - self.last_error_time).total_seconds() > self.error_log_interval):
                logger.debug(f"Failed to parse line '{line.strip()}': {e}")
                self.last_error_time = now
            return None
    
    def run(self):
        """
        Main loop: continuously read serial data, buffer, and flush periodically.
        
        Runs until shutdown signal received (SIGTERM, SIGINT).
        """
        logger.info("Starting serial reader loop...")
        self.connect()
        
        try:
            while self.running:
                try:
                    # Read one line from serial port (blocks with timeout)
                    raw_line = self.ser.readline()
                    if not raw_line:
                        continue
                    
                    # Decode and parse
                    line = raw_line.decode("utf-8", errors="ignore")
                    amps = self.parse_line(line)
                    
                    if amps is not None and amps >= 0:
                        # Timestamp with timezone
                        timestamp = datetime.now(self.tz).isoformat()
                        self.buffer.append((timestamp, amps))
                        
                        # Flush if buffer is full or time exceeded
                        if self._should_flush():
                            self.flush()
                
                except serial.SerialException as e:
                    # Reconnect on serial error
                    self.error_count += 1
                    logger.error(f"Serial read error: {e}")
                    self.flush()  # Save buffered data before reconnecting
                    time.sleep(2)
                    try:
                        self.connect()
                    except RuntimeError as re:
                        logger.error(f"Reconnection failed: {re}")
                        raise
                
                except Exception as e:
                    logger.error(f"Unexpected error in read loop: {e}", exc_info=True)
                    self.flush()
                    raise
        
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            self.shutdown(None, None)
    
    def _should_flush(self):
        """Check if buffer should be flushed based on size or time."""
        if len(self.buffer) >= self.buffer_size:
            return True
        
        elapsed = (datetime.now() - self.last_flush).total_seconds()
        if elapsed >= self.flush_interval:
            return True
        
        return False
    
    def flush(self):
        """
        Write buffered readings to database.
        
        Called periodically or on shutdown to ensure no data loss.
        """
        if not self.buffer:
            return
        
        try:
            count = self.logger_db.insert_batch(self.buffer)
            logger.debug(f"Flushed {count} readings to database")
            self.buffer.clear()
            self.last_flush = datetime.now()
        
        except Exception as e:
            logger.error(f"Failed to flush buffer: {e}", exc_info=True)
            # Don't clear buffer on error — retry next flush
    
    def shutdown(self, signum, frame):
        """
        Graceful shutdown handler for SIGTERM/SIGINT.
        
        Flushes remaining buffer, closes serial port, exits cleanly.
        
        Args:
            signum: Signal number (SIGTERM=15, SIGINT=2)
            frame: Stack frame
        """
        logger.info("Shutting down gracefully...")
        self.running = False
        
        # Flush any remaining data
        if self.buffer:
            logger.info(f"Flushing {len(self.buffer)} remaining readings...")
            self.flush()
        
        # Close serial port
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
                logger.info("Serial port closed")
            except Exception as e:
                logger.error(f"Error closing serial port: {e}")
        
        logger.info("Shutdown complete")


def main():
    """Entry point — orchestrates serial reader startup and lifecycle."""
    logger.info("=" * 60)
    logger.info("Power Monitor Serial Reader")
    logger.info("=" * 60)
    
    # Configuration (customize as needed)
    port = os.getenv("SERIAL_PORT", "/dev/serial0")
    baud = int(os.getenv("SERIAL_BAUD", "38400"))
    buffer_size = int(os.getenv("BUFFER_SIZE", "100"))
    flush_interval = int(os.getenv("FLUSH_INTERVAL", "10"))
    
    logger.info(f"Configuration:")
    logger.info(f"  Port: {port}")
    logger.info(f"  Baud: {baud}")
    logger.info(f"  Buffer size: {buffer_size} rows")
    logger.info(f"  Flush interval: {flush_interval}s")
    logger.info("=" * 60)
    
    # Create reader instance
    reader = SerialReader(
        port=port,
        baud=baud,
        buffer_size=buffer_size,
        flush_interval=flush_interval
    )
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, reader.shutdown)
    signal.signal(signal.SIGINT, reader.shutdown)
    
    # Start main read loop
    try:
        reader.run()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        exit(1)


if __name__ == "__main__":
    main()
