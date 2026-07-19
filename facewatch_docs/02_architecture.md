# FaceWatch — Architecture

## Folder Structure

```
utils/
└── facewatch/
    │
    ├── config_defaults.py              # Static defaults — seeds DB on first run only
    │
    ├── core/
    │   ├── detector.py                 # MediaPipe FaceLandmarker LIVE_STREAM wrapper
    │   ├── tracker.py                  # SORT integration + track_id lifecycle
    │   └── recognizer.py              # DeepFace embeddings, search, register, retry
    │
    ├── analysis/
    │   ├── expressions/
    │   │   ├── base.py                 # Expression ABC
    │   │   ├── blink.py                # BlinkLeft, BlinkRight
    │   │   ├── smile.py                # Smile
    │   │   ├── angry.py                # Angry
    │   │   ├── surprised.py            # Surprised (eyebrow raise)
    │   │   ├── neutral.py              # Neutral (inverse of all others)
    │   │   ├── drowsy.py               # Drowsiness via PERCLOS
    │   │   └── registry.py             # EXPRESSIONS list — ONLY file touched to add/remove
    │   ├── gaze.py                     # GazeTracker + hysteresis state machine
    │   └── distance.py                 # Cheekbone distance estimator (dynamic face width)
    │
    ├── alerts/
    │   ├── base.py                     # Alert ABC — dual-threshold hysteresis
    │   ├── gaze_alert.py               # Off-screen alert
    │   ├── proximity_alert.py          # Too-close alert
    │   └── registry.py                 # ALERTS list — ONLY file touched to add/remove
    │
    ├── storage/
    │   ├── database.py                 # ALL SQLite ops — schema, writes, reads, migrations
    │   └── config_store.py             # ConfigStore.get() / .set() — reads from DB
    │
    ├── demographics/
    │   ├── analyzer.py                 # DeepFace demographics runner, weekly re-run logic
    │   └── face_width.py               # age + gender → face_width_cm lookup
    │
    ├── reporting/
    │   ├── reporter.py                 # Background scheduler — triggers at REPORT_TIMES
    │   ├── builder.py                  # Queries DB → builds report data dict
    │   ├── server.py                   # http.server on localhost:PORT (/report + /config + /api)
    │   ├── notifier.py                 # Desktop notification + URL via plyer
    │   └── templates/
    │       ├── report.html.j2          # Jinja2 HTML report template
    │       └── config.html.j2          # Jinja2 config editor template
    │
    ├── ui/
    │   ├── renderer.py                 # ALL cv2 drawing — zero cv2 calls anywhere else
    │   └── input_handler.py            # Mouse click + keyboard handler
    │
    └── engine.py                       # Main loop — CLI args, wires all modules, <150 lines
```

---

## Coding Rules (Mandatory — Never Break These)

```
R1   Hard line limit: 150 lines per file. Split if approaching.
R2   One responsibility per file. If "and" appears in the
     description, it needs splitting.
R3   Zero magic numbers outside config_defaults.py.
R4   Dependency direction: engine → modules → storage → config.
     No circular imports. No module imports engine.
R5   Zero raw SQL outside database.py.
R6   Zero cv2 calls outside ui/renderer.py.
R7   Add expression: new file in expressions/, add to registry.py.
     Touch zero other files.
R8   Add alert: new file in alerts/, add to registry.py.
     Touch zero other files.
R9   All config reads go through ConfigStore.get(), never
     direct from config_defaults.py at runtime.
R10  DB writes happen only at STATS_INTERVAL — never per-frame.
R11  Demographics run once per face in a background thread.
     Result cached in DB. Never re-run unless forced or weekly threshold passed.
R12  Every function has a single return type. No returning
     None sometimes and a value other times.
R13  No face images ever saved to disk — embeddings only.
R14  All timestamps stored as ISO 8601 UTC strings.
```

---

## Data Flow (Per Frame)

```
Camera frame
    │
    ├─ detector.py       → face_landmarks[] (478 pts × N faces)
    ├─ tracker.py        → tracks[] (bbox + stable track_id)
    ├─ recognizer.py     → identity per track_id (name or unknown_N)
    │
    per tracked face:
    ├─ expressions/      → {expr_name: ExpressionState}
    ├─ gaze.py           → GazeState (direction, on_screen, hysteresis timer)
    ├─ distance.py       → float cm (uses per-face face_width_cm from demographics)
    ├─ alerts/           → [fired alerts list]
    │
    every STATS_INTERVAL_SEC (known faces only):
    ├─ psutil            → active app name + window title + full timestamp
    ├─ database.py       → INSERT stats row
    │
    at REPORT_TIMES:
    ├─ builder.py        → query DB → data dict
    ├─ server.py         → serve HTML on localhost:PORT
    ├─ notifier.py       → desktop notification + clickable URL
    │
    every frame:
    └─ renderer.py       → draw all overlays on frame
```

---

## Dependency Direction (No Circular Imports)

```
engine.py
    ↓
core/*, analysis/*, alerts/*, demographics/*, ui/*, reporting/*
    ↓
storage/database.py, storage/config_store.py
    ↓
config_defaults.py
```

Nothing in the lower layers imports from the upper layers.

---

## Threading Model

| Thread | What it does |
|---|---|
| Main thread | Camera loop, cv2 display, UI input |
| MediaPipe callback thread | LIVE_STREAM result callback — writes to `latest_result` under lock |
| Recognizer thread (per new track) | DeepFace embedding computation — slow, must not block main loop |
| Demographics thread (per face, weekly) | DeepFace age/gender/race — slow, runs once then sleeps |
| Reporter thread | Sleeps, wakes at REPORT_TIMES, triggers report generation |
| HTTP server thread | Serves report and config pages — daemon thread |

All shared state protected by `threading.Lock()`.

---

## File Size Budget

| File | Max Lines |
|---|---|
| engine.py | 150 |
| core/detector.py | 60 |
| core/tracker.py | 70 |
| core/recognizer.py | 150 |
| analysis/expressions/base.py | 80 |
| analysis/expressions/*.py (each) | 40 |
| analysis/expressions/registry.py | 20 |
| analysis/gaze.py | 100 |
| analysis/distance.py | 50 |
| alerts/base.py | 60 |
| alerts/*.py (each) | 40 |
| storage/database.py | 150 |
| storage/config_store.py | 60 |
| demographics/analyzer.py | 80 |
| demographics/face_width.py | 40 |
| reporting/reporter.py | 60 |
| reporting/builder.py | 80 |
| reporting/server.py | 100 |
| reporting/notifier.py | 30 |
| ui/renderer.py | 150 |
| ui/input_handler.py | 60 |
