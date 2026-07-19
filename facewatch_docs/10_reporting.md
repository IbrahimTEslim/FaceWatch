# FaceWatch — Reporting System

## Overview

At configured times (default 18:00 and 21:00), FaceWatch:
1. Queries today's stats from SQLite
2. Builds a data dict via `builder.py`
3. Renders an HTML report via Jinja2
4. Starts a local HTTP server on `localhost:PORT`
5. Fires a desktop notification with a clickable link
6. User clicks link → browser opens the report

---

## reporting/reporter.py

### Responsibility
Background thread that sleeps and wakes at REPORT_TIMES.

```python
class Reporter(threading.Thread):
    def run(self):
        while True:
            now = datetime.now()
            next_trigger = self._next_trigger_time(now)
            sleep_sec = (next_trigger - now).total_seconds()
            time.sleep(max(sleep_sec, 1))
            self._generate_and_serve()

    def _next_trigger_time(self, now: datetime) -> datetime:
        """Find the next upcoming time from REPORT_TIMES config."""

    def _generate_and_serve(self):
        data = builder.build_report(date.today())
        html = render_template("report.html.j2", data)
        server.serve(html)
        notifier.notify(port=config.get("report_port"))
```

---

## reporting/builder.py

### Responsibility
Query SQLite for today's data → return a structured dict for the template.

### Report Data Structure
```python
{
    "date": "Monday, January 15 2024",
    "generated_at": "18:00",

    "faces": [
        {
            "name": "Ibrahim",
            "demographics": {
                "age": 28, "gender": "Male", "race": "Middle Eastern"
            },
            "summary": {
                "total_tracked_sec": 14400,    # 4 hours
                "avg_focus_score": 73.2,
                "peak_focus_score": 91.0,
                "avg_distance_cm": 58.3,
                "total_gaze_off_sec": 1240,
                "proximity_alert_count": 3,
            },
            "expressions": {
                "blink_left_total": 842,
                "blink_right_total": 839,
                "smile_total": 47,
                "angry_total": 12,
                "surprised_total": 8,
                "neutral_avg_pct": 68.4,
                "drowsy_avg_pct": 2.1,
            },
            "focus_timeline": [
                # One entry per stats interval — for Chart.js timeline
                {"timestamp": "09:00:05", "focus_score": 82, "app": "code.exe"},
                {"timestamp": "09:00:10", "focus_score": 79, "app": "code.exe"},
                ...
            ],
            "app_breakdown": [
                # Sorted by time spent
                {"app": "code.exe",    "category": "editor",  "total_sec": 7200,
                 "avg_focus": 78.1, "smile_count": 23, "angry_count": 4},
                {"app": "chrome.exe",  "category": "browser", "total_sec": 3600,
                 "avg_focus": 61.2, "smile_count": 12, "angry_count": 6},
                ...
            ],
            "hourly_breakdown": [
                # One entry per hour — for heatmap/bar chart
                {"hour": "09", "avg_focus": 81.2, "intervals": 720},
                {"hour": "10", "avg_focus": 74.5, "intervals": 720},
                ...
            ],
            "session_timeline": [
                # Contiguous blocks of same state — for visual timeline bar
                {"start": "09:00", "end": "10:30", "state": "focused",   "app": "code.exe"},
                {"start": "10:30", "end": "11:00", "state": "distracted","app": "chrome.exe"},
                {"start": "11:00", "end": "11:15", "state": "away",      "app": None},
                ...
            ],
        }
    ],

    "events_today": [
        # From audit_log
        {"time": "09:15", "event": "face_registered", "details": "Registered 'Ibrahim'"},
        {"time": "14:32", "event": "alert_fired",      "details": "Gaze alert — 45 sec away"},
    ],
}
```

---

## reporting/server.py

### Routes

| Route | Method | Description |
|---|---|---|
| `/` | GET | Redirect to `/report` |
| `/report` | GET | Today's HTML report |
| `/report?date=2024-01-14` | GET | Historical report for a date |
| `/config` | GET | Config editor page |
| `/config` | POST | Save config changes to DB |
| `/api/stats` | GET | JSON stats (query params: face, from, to) |
| `/api/faces` | GET | JSON list of known faces |

### Implementation
```python
# Uses Python built-in http.server — no Flask/FastAPI needed
# Runs as daemon thread — dies when main process exits
# Serves pre-rendered HTML string (not files on disk)
# Config editor page uses a simple HTML form with POST
```

---

## reporting/notifier.py

```python
import webbrowser
from plyer import notification

def notify(port: int) -> None:
    url = f"http://localhost:{port}/report"
    notification.notify(
        title="FaceWatch — Daily Report Ready",
        message=f"Today's summary is available. Click to open.",
        app_name="FaceWatch",
        timeout=10,
    )
    # Also open browser automatically after short delay
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
```

---

## reporting/templates/report.html.j2

### Sections

1. **Header** — date, FaceWatch logo, "PRIVATE — Local Only" badge
2. **Face Cards** — one card per known face with photo placeholder + demographics
3. **Focus Score** — large number, color-coded, daily average
4. **Session Timeline** — horizontal color bar (focused/distracted/away/unknown)
5. **Expression Stats** — blink rates, smile/angry/surprised counts, drowsiness %
6. **App Breakdown** — table: app name, category, time spent, avg focus, emotions
7. **Hourly Heatmap** — bar chart of focus score by hour (Chart.js)
8. **Gaze Stats** — total off-screen time, alert count
9. **Distance Stats** — average distance, proximity alert count
10. **Events Log** — audit_log entries for today
11. **Config Editor Link** — "Edit Settings →" button

### Charts
All charts use **Chart.js** loaded from CDN — no server-side chart rendering needed.
Data injected as JSON in `<script>` tags by Jinja2.

```html
<script>
const focusData = {{ focus_timeline | tojson }};
// Chart.js renders this client-side
</script>
```

### Styling
- Dark theme (easier on eyes, looks professional)
- CSS variables for colors — easy to theme
- Responsive layout (works on any screen size)
- Embedded CSS in the template — single self-contained HTML file
- No external CSS files needed (report works offline)

---

## reporting/templates/config.html.j2

### Layout
- Grouped by category (camera, storage, recognition, gaze, proximity, expressions, report)
- Each row: key | current value | input field | description | reset button
- Save button at bottom of each category group
- Changes POST to `/config` and redirect back with success message

### Expression Threshold Section
Special section showing each expression with:
- Current threshold value (editable)
- Live preview bar showing current activation (requires WebSocket — v1.1 feature)
- Reset to default button
- Reset to calibrated value button (if calibration was run)
