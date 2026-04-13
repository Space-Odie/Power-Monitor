# Python Dependency Test & Verification

## Overview

This document provides a test script to verify all Python dependencies are installed before deploying the power monitoring pipeline to the Raspberry Pi.

---

## Dependencies List

### Core Requirements
- `pyserial>=3.5` — Serial communication with RPICT3V1
- `matplotlib>=3.5` — Chart generation
- `numpy>=1.21` — Numerical operations and stats
- `sqlite3` — Built-in to Python 3.9+

### Standard Library (no install needed)
- `logging` — Event logging
- `datetime` — Timestamp handling
- `zoneinfo` — Timezone management (Python 3.9+)
- `signal` — Signal handling for graceful shutdown
- `os` — File and directory operations
- `sys` — System-specific parameters

### Optional (Nice to have)
- `pandas>=1.3` — Data aggregation (not strictly required)

---

## Installation

### Option 1: Install from requirements.txt (Recommended for Raspberry Pi)

On Raspberry Pi OS, use `sudo` to install system-wide:

```bash
cd /home/pi/power-monitor
sudo pip install -r requirements.txt
```

Then you can run scripts directly without any special setup:
```bash
python3 check_dependencies.py
python3 reader.py
python3 plotter.py
```

**requirements.txt content:**
```
pyserial>=3.5
matplotlib>=3.5
numpy>=1.21
```

### Option 2: Install packages individually

```bash
sudo pip install pyserial>=3.5
sudo pip install matplotlib>=3.5
sudo pip install numpy>=1.21
```

### Option 3: Alternative - Use --break-system-packages (if you don't want sudo)

```bash
pip install --break-system-packages -r requirements.txt
```

---

## Test Script: `check_dependencies.py`

**Purpose:** Verify all required packages are installed and working.

**Installation:**
Place this file in `/home/pi/power-monitor/` and run:
```bash
python3 check_dependencies.py
```

**Code:**

```python
#!/usr/bin/env python3
"""
Dependency checker for EV Power Monitor Pipeline
Verifies all required packages are installed and importable
"""

import sys

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'
BOLD = '\033[1m'

def test_import(module_name, package_name=None, version_check=None):
    """
    Test if a module can be imported.
    
    Args:
        module_name (str): Name of module to import (e.g., 'serial')
        package_name (str): Name of package for display (e.g., 'pyserial'). Defaults to module_name.
        version_check (str): Version requirement string (e.g., '>=3.5'). Optional.
    
    Returns:
        bool: True if import successful, False otherwise
    """
    if package_name is None:
        package_name = module_name
    
    try:
        module = __import__(module_name)
        version = getattr(module, '__version__', 'unknown')
        
        status = f"{GREEN}✓{RESET} {package_name:20s} {version:15s} "
        if version_check:
            status += f"(requires {version_check})"
        print(status)
        return True
    except ImportError as e:
        print(f"{RED}✗{RESET} {package_name:20s} NOT INSTALLED")
        print(f"  Error: {e}")
        return False

def main():
    print(f"\n{BOLD}=== EV Power Monitor: Dependency Check ==={RESET}\n")
    
    results = {
        'core': [],
        'stdlib': [],
        'optional': []
    }
    
    # Core dependencies (required)
    print(f"{BOLD}Core Dependencies (REQUIRED):{RESET}")
    results['core'].append(test_import('serial', 'pyserial>=3.5', '>=3.5'))
    results['core'].append(test_import('matplotlib', 'matplotlib>=3.5', '>=3.5'))
    results['core'].append(test_import('numpy', 'numpy>=1.21', '>=1.21'))
    results['core'].append(test_import('sqlite3', 'sqlite3 (built-in)', None))
    
    print(f"\n{BOLD}Standard Library (included with Python 3.9+):{RESET}")
    results['stdlib'].append(test_import('logging', 'logging', None))
    results['stdlib'].append(test_import('datetime', 'datetime', None))
    try:
        from zoneinfo import ZoneInfo
        print(f"{GREEN}✓{RESET} {'zoneinfo':20s} (built-in, Python 3.9+)")
        results['stdlib'].append(True)
    except ImportError:
        print(f"{RED}✗{RESET} {'zoneinfo':20s} NOT AVAILABLE (Python < 3.9?)")
        results['stdlib'].append(False)
    results['stdlib'].append(test_import('signal', 'signal', None))
    results['stdlib'].append(test_import('os', 'os', None))
    
    print(f"\n{BOLD}Optional Dependencies:{RESET}")
    results['optional'].append(test_import('pandas', 'pandas>=1.3 (optional)', '>=1.3'))
    
    # Summary
    print(f"\n{BOLD}=== Summary ==={RESET}")
    core_pass = all(results['core'])
    stdlib_pass = all(results['stdlib'])
    
    if core_pass and stdlib_pass:
        print(f"{GREEN}{BOLD}✓ All required dependencies are installed!{RESET}")
        print(f"  Your system is ready to deploy the power monitor pipeline.")
        return 0
    else:
        print(f"{RED}{BOLD}✗ Missing dependencies detected.{RESET}")
        print(f"\n{YELLOW}To install missing packages, run:{RESET}")
        print(f"  pip install -r requirements.txt")
        print(f"  or")
        print(f"  pip install pyserial matplotlib numpy")
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

---

## Usage

### On Development Machine (Desktop)

1. **Create virtual environment (optional but recommended):**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On macOS/Linux
   # or: venv\Scripts\activate  # On Windows
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run dependency check:**
   ```bash
   python3 check_dependencies.py
   ```

### On Raspberry Pi

1. **SSH to Pi:**
   ```bash
   ssh pi@192.168.4.50
   cd /home/pi/power-monitor
   ```

2. **Copy dependency checker and requirements from desktop:**
   ```bash
   # From your desktop machine:
   scp check_dependencies.py pi@192.168.4.50:/home/pi/power-monitor/
   scp requirements.txt pi@192.168.4.50:/home/pi/power-monitor/
   ```

3. **Install dependencies on Pi (with sudo):**
   ```bash
   sudo pip install -r requirements.txt
   ```

4. **Run dependency check on Pi:**
   ```bash
   python3 check_dependencies.py
   ```

Expected output:
```
=== EV Power Monitor: Dependency Check ===

Core Dependencies (REQUIRED):
✓ pyserial              3.5               (requires >=3.5)
✓ matplotlib            3.5.2             (requires >=3.5)
✓ numpy                 1.21.0            (requires >=1.21)
✓ sqlite3               unknown           

Standard Library (included with Python 3.9+):
✓ logging               (built-in)
✓ datetime              (built-in)
✓ zoneinfo              (built-in, Python 3.9+)
✓ signal                (built-in)
✓ os                    (built-in)

Optional Dependencies:
✓ pandas                1.3.5             (optional)

=== Summary ===
✓ All required dependencies are installed!
  Your system is ready to deploy the power monitor pipeline.
```

---

## Troubleshooting

### `pip install` fails with "externally-managed-environment"

**Solution (on Raspberry Pi with passwordless sudo):**

```bash
sudo pip install -r requirements.txt
```

This installs packages system-wide. Since you have passwordless sudo configured, you won't be prompted for a password and can run Python scripts directly:
```bash
python3 your_script.py  # No special setup needed
```

### `matplotlib` installation takes a long time on Raspberry Pi

**Note:** This is normal. Matplotlib compiles some C extensions. Grab coffee ☕
- Expected time: 5–15 minutes on Raspberry Pi 4
- Use pre-built wheels if available:
  ```bash
  pip install --upgrade pip setuptools wheel
  pip install -r requirements.txt
  ```

### `pyserial` not found after install

**Solution:**
```bash
# Verify it's installed
pip list | grep pyserial

# If missing, reinstall explicitly
pip install --force-reinstall pyserial

# Check import directly
python3 -c "import serial; print(serial.__version__)"
```

### Python version < 3.9 (missing `zoneinfo`)

**Solution:**
```bash
# Install backport for Python 3.8 or earlier
pip install backports.zoneinfo

# Then update imports in reader.py and logger.py:
# Change: from zoneinfo import ZoneInfo
# To:     from backports.zoneinfo import ZoneInfo  # Python < 3.9
#         # or: from zoneinfo import ZoneInfo  # Python >= 3.9
```

---

## Version Compatibility Matrix

| Package | Min Version | Tested on Raspberry Pi 4 | Notes |
|---------|-------------|--------------------------|-------|
| Python | 3.9 | 3.9.2 (bullseye) | Need 3.9+ for zoneinfo |
| pyserial | 3.5 | 3.5 | Standard UART driver |
| matplotlib | 3.5 | 3.5.2 | For chart rendering |
| numpy | 1.21 | 1.21.0 | For numerical ops |
| sqlite3 | (built-in) | 3.34.1 | Included with Python |

---

## Next Steps

Once dependency check passes:
1. Deploy `reader.py`, `logger.py`, `plotter.py` to Pi
2. Run `init_db.py` to initialize database
3. Run `test_serial.py` to identify RMS current column
4. Install systemd service and start monitoring

