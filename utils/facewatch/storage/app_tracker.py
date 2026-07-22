import sys
import psutil

APP_CATEGORIES: dict[str, str] = {
    # Browsers
    "chrome.exe":            "browser",
    "firefox.exe":           "browser",
    "msedge.exe":            "browser",
    "safari":                "browser",
    "brave.exe":             "browser",
    # Editors / IDEs
    "code.exe":              "editor",
    "pycharm64.exe":         "editor",
    "idea64.exe":            "editor",
    "sublime_text.exe":      "editor",
    "notepad++.exe":         "editor",
    "vim":                   "editor",
    "nvim":                  "editor",
    # Communication
    "slack.exe":             "communication",
    "teams.exe":             "communication",
    "discord.exe":           "communication",
    "zoom.exe":              "communication",
    "outlook.exe":           "communication",
    "thunderbird.exe":       "communication",
    # Games
    "steam.exe":             "game",
    "epicgameslauncher.exe": "game",
    # Media
    "vlc.exe":               "media",
    "spotify.exe":           "media",
    # Terminals
    "windowsterminal.exe":   "terminal",
    "cmd.exe":               "terminal",
    "powershell.exe":        "terminal",
    "bash":                  "terminal",
    "zsh":                   "terminal",
    # Documents
    "winword.exe":           "document",
    "excel.exe":             "document",
    "powerpnt.exe":          "document",
    "acrobat.exe":           "document",
}


def get_app_category(process_name: str) -> str:
    """Returns category string. Falls back to 'other' if unknown."""
    return APP_CATEGORIES.get(process_name.lower(), "other")


def get_active_app() -> tuple[str, str]:
    """
    Returns (process_name, window_title) of the current foreground window.
    Cross-platform: Windows, macOS, Linux (X11). Wayland falls back to ('unknown', '').
    Returns ('unknown', '') if detection fails.
    """
    if sys.platform == "win32":
        return _get_active_app_windows()
    if sys.platform == "darwin":
        return _get_active_app_macos()
    return _get_active_app_linux()


def _get_active_app_windows() -> tuple[str, str]:
    try:
        import win32gui
        import win32process
        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return psutil.Process(pid).name(), title
    except Exception:
        return "unknown", ""


def _get_active_app_macos() -> tuple[str, str]:
    try:
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().activeApplication()
        return app.get("NSApplicationName", "unknown"), ""
    except Exception:
        return "unknown", ""


def _get_active_app_linux() -> tuple[str, str]:
    try:
        from ewmh import EWMH
        ew  = EWMH()
        win = ew.getActiveWindow()
        title = ew.getWmName(win).decode()
        pid   = ew.getWmPid(win)
        return psutil.Process(pid).name(), title
    except Exception:
        return "unknown", ""
