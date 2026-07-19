# FaceWatch — Active App Tracking

## Purpose

At every stats write interval, FaceWatch captures what application the user is
currently focused on. This enables powerful insights like:

- "You are most focused when using VS Code"
- "You blink 40% less when playing games (eye strain risk)"
- "You appear angry most often when using email"
- "Your average camera distance is 35cm when using your phone (too close)"
- "You spend 3.2 hours/day in your browser with focus score averaging 61"

---

## What Gets Captured

Per stats row (every `stats_interval_sec`):

| Field | Example | Notes |
|---|---|---|
| `active_app` | `code.exe` | Process name of foreground window |
| `active_window_title` | `engine.py — FaceWatch — VS Code` | Full window title |
| `app_category` | `editor` | Derived from process name |
| `timestamp` | `2024-01-15T14:32:07Z` | Full ISO 8601 UTC — enables hour-of-day analysis |

---

## Implementation

### psutil + platform-specific foreground window

```python
# storage/app_tracker.py  (single responsibility — R2)

import psutil
import sys

def get_active_app() -> tuple[str, str]:
    """
    Returns (process_name, window_title) of the current foreground window.
    Cross-platform: Windows, macOS, Linux.
    Returns ('unknown', '') if detection fails.
    """
    if sys.platform == "win32":
        return _get_active_app_windows()
    elif sys.platform == "darwin":
        return _get_active_app_macos()
    else:
        return _get_active_app_linux()
```

### Windows
```python
import ctypes
import win32gui   # pip install pywin32
import win32process

def _get_active_app_windows() -> tuple[str, str]:
    hwnd = win32gui.GetForegroundWindow()
    title = win32gui.GetWindowText(hwnd)
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    try:
        proc = psutil.Process(pid)
        return proc.name(), title
    except Exception:
        return "unknown", title
```

### macOS
```python
from AppKit import NSWorkspace   # pip install pyobjc

def _get_active_app_macos() -> tuple[str, str]:
    app = NSWorkspace.sharedWorkspace().activeApplication()
    name = app.get("NSApplicationName", "unknown")
    # Window title requires Accessibility API — use app name only on macOS
    return name, ""
```

### Linux
```python
import subprocess

def _get_active_app_linux() -> tuple[str, str]:
    # Requires xdotool: sudo apt install xdotool
    try:
        wid = subprocess.check_output(["xdotool", "getactivewindow"]).strip()
        title = subprocess.check_output(["xdotool", "getwindowname", wid]).decode().strip()
        pid = subprocess.check_output(["xdotool", "getwindowpid", wid]).strip()
        proc = psutil.Process(int(pid))
        return proc.name(), title
    except Exception:
        return "unknown", ""
```

---

## App Category Lookup

```python
# storage/app_tracker.py

APP_CATEGORIES = {
    # Browsers
    "chrome.exe":       "browser",
    "firefox.exe":      "browser",
    "msedge.exe":       "browser",
    "safari":           "browser",
    "brave.exe":        "browser",

    # Editors / IDEs
    "code.exe":         "editor",
    "pycharm64.exe":    "editor",
    "idea64.exe":       "editor",
    "sublime_text.exe": "editor",
    "notepad++.exe":    "editor",
    "vim":              "editor",
    "nvim":             "editor",

    # Communication
    "slack.exe":        "communication",
    "teams.exe":        "communication",
    "discord.exe":      "communication",
    "zoom.exe":         "communication",
    "outlook.exe":      "communication",
    "thunderbird.exe":  "communication",

    # Games
    "steam.exe":        "game",
    "epicgameslauncher.exe": "game",

    # Media
    "vlc.exe":          "media",
    "spotify.exe":      "media",

    # Terminals
    "windowsterminal.exe": "terminal",
    "cmd.exe":          "terminal",
    "powershell.exe":   "terminal",
    "bash":             "terminal",
    "zsh":              "terminal",

    # Documents
    "winword.exe":      "document",
    "excel.exe":        "document",
    "powerpnt.exe":     "document",
    "acrobat.exe":      "document",
}

def get_app_category(process_name: str) -> str:
    """Returns category string. Falls back to 'other' if unknown."""
    return APP_CATEGORIES.get(process_name.lower(), "other")
```

---

## Timestamp Design

Full ISO 8601 UTC timestamp stored with every stats row:
```
2024-01-15T14:32:07Z
```

This enables queries like:

```sql
-- Which hour of day is user most focused?
SELECT substr(timestamp, 12, 2) as hour,
       AVG(focus_score) as avg_focus,
       COUNT(*) as intervals
FROM stats
WHERE face_id = ?
GROUP BY hour
ORDER BY avg_focus DESC;

-- Emotion by time of day
SELECT substr(timestamp, 12, 2) as hour,
       SUM(angry_count), SUM(smile_count)
FROM stats
WHERE face_id = ?
GROUP BY hour;

-- App usage by day of week
SELECT
    CASE CAST(strftime('%w', timestamp) AS INTEGER)
        WHEN 0 THEN 'Sunday'
        WHEN 1 THEN 'Monday'
        -- etc.
    END as weekday,
    active_app,
    SUM(interval_sec) as total_sec
FROM stats
WHERE face_id = ?
GROUP BY weekday, active_app;
```

---

## Privacy Note

Window titles can contain sensitive information (e.g. email subjects, document names).
In v1.1, add a config option `store_window_titles = false` that captures only the
process name and category, not the full title.
Default: `true` (store full title) — user can disable.
