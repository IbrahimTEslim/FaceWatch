import threading
import time
import webbrowser
from datetime import datetime


def _parse_times(report_times) -> list[tuple[int, int]]:
    """Accepts a comma string or a list of HH:MM strings."""
    if isinstance(report_times, str):
        items = [t.strip() for t in report_times.split(",") if t.strip()]
    else:
        items = list(report_times)
    result = []
    for t in items:
        try:
            h, m = t.split(":")
            result.append((int(h), int(m)))
        except Exception:
            pass
    return result


def _notify(port: int) -> None:
    try:
        from plyer import notification
        notification.notify(
            title="FaceWatch",
            message="Your focus report is ready.",
            app_name="FaceWatch",
            timeout=6,
        )
    except Exception:
        pass
    webbrowser.open(f"http://localhost:{port}")


def start_notifier(port: int, report_times_str: str) -> threading.Thread:
    """
    Starts a background thread that fires at each time in report_times_str.
    Returns the thread (daemon=True, no need to join).
    """
    times = _parse_times(report_times_str)

    def _loop():
        fired: set[tuple[int, int]] = set()
        while True:
            now = datetime.now()
            key = (now.hour, now.minute)
            if key in times and key not in fired:
                fired.add(key)
                _notify(port)
            # Reset fired set at midnight
            if now.hour == 0 and now.minute == 0:
                fired.clear()
            time.sleep(30)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t
