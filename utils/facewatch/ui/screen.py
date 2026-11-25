"""
Primary screen size detection.

All gaze coordinates (calibration targets, predicted gaze, on-screen checks)
live in the pixel space the overlays draw in: Qt's logical geometry of the
primary screen. On a scaled display this differs from the physical resolution
(e.g. 1920x1200 at 125% -> 1536x960).

The calibration overlay process reports that geometry directly. tkinter is the
fallback, normalised to logical pixels on Windows.
"""

import sys

from ui.calibration_overlay import CalibrationOverlay

_LAST_RESORT = (1920, 1080)
_OVERLAY_TIMEOUT_SEC = 30.0


def _tk_screen_size() -> tuple[int, int] | None:
    try:
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        try:
            w, h = root.winfo_screenwidth(), root.winfo_screenheight()
            dpi  = root.winfo_fpixels("1i")
        finally:
            root.destroy()
    except Exception:
        return None
    if sys.platform == "win32":
        # tkinter reports physical pixels if anything has made this process
        # DPI-aware (Qt does). Convert to logical pixels to match the overlay.
        # Windows scale factors come in 25% steps; tk's DPI is only approximate.
        scale = round(dpi / 96.0 * 4) / 4
        if scale > 0:
            w, h = round(w / scale), round(h / scale)
    return (w, h) if w > 0 and h > 0 else None


def detect_screen_size(overlay: CalibrationOverlay,
                       timeout: float = _OVERLAY_TIMEOUT_SEC) -> tuple[int, int]:
    """Screen size in overlay (Qt logical) pixels. Never raises."""
    size = overlay.screen_size(timeout)
    if size:
        return size

    size = _tk_screen_size()
    if size:
        print(f"[WARN] Calibration overlay did not report screen size; using {size[0]}x{size[1]} from tkinter.")
        return size

    print(f"[WARN] Could not detect screen size; assuming {_LAST_RESORT[0]}x{_LAST_RESORT[1]}.")
    return _LAST_RESORT
