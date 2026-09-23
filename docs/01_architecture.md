# Architecture

FaceWatch is structured as a pipeline of independent modules wired together by a single main loop in `engine.py`. Each module has one responsibility and communicates through plain data objects — no shared mutable state except where explicitly protected by locks.

---

## Directory layout

```
utils/facewatch/
├── core/               Face detection, tracking, recognition
├── analysis/           Expressions, gaze, distance, focus score
├── alerts/             All alert types + hysteresis engine
├── calibration/        Focal wizard, gaze wizard, smoother, store
├── demographics/       DeepFace analyzer, face-width lookup table
├── storage/            SQLite schema, query groups, config store, app tracker
├── ui/                 Renderer, input handler, mouse handler, overlays, settings
├── reporting/          Flask server, report builder, notifier
├── config_defaults.py  Static seed values — never read at runtime
└── engine.py           Main loop — wires everything together
```

---

## Data flow per frame

```
Camera frame (BGR, flipped)
    │
    ├─ FaceDetector          → FaceLandmarkerResult  (478 landmarks + 52 blendshapes)
    ├─ FaceTracker           → {track_id: [x1,y1,x2,y2]}  (SORT, stable IDs)
    ├─ PtgazeEstimator       → [(face, hit), ...]  (gaze ray → Z=0 plane intersection)
    │
    per tracked face:
    ├─ FaceRecognizer        → Identity  (known / unknown / pending)
    ├─ DemographicsAnalyzer  → age, gender, race, face_width_cm  (background thread)
    ├─ Expression.update()   → blendshape activations, counts, PERCLOS
    ├─ GazeTracker.update()  → GazeState  (screen_x/y, direction, hysteresis)
    ├─ DistanceEstimator     → float cm
    ├─ AlertManager.update() → [AlertEvent, ...]
    │
    every stats_interval_sec (known faces only):
    ├─ get_active_app()      → app name + window title
    ├─ compute_focus_score() → 0–100
    └─ db.write_stats()      → INSERT into stats table
    │
    every frame:
    └─ Renderer.draw()       → annotated frame → cv2.imshow()
```

---

## Threading model

| Thread | Role |
|---|---|
| Main | Camera loop, cv2 display, all UI input |
| MediaPipe (internal) | VIDEO mode — synchronous, no extra thread needed |
| Recognizer (per new track) | DeepFace embedding — slow, must not block main loop |
| Demographics (per face) | DeepFace analyze — runs once then weekly |
| Reporter / Flask | Daemon thread — serves HTML report on localhost |
| Notifier | Daemon thread — wakes at configured report times |
| Alert overlay | PyQt6 daemon thread — fullscreen pulsing border |
| Calibration overlay | PyQt6 daemon thread — gaze dot display |

All shared state between threads is protected by `threading.Lock()`.

---

## Dependency direction

```
engine.py
    ↓
core/  analysis/  alerts/  demographics/  ui/  reporting/  calibration/
    ↓
storage/db/  storage/config_store.py
    ↓
config_defaults.py  (seed only — never imported at runtime)
```

Nothing in the lower layers imports from the upper layers. No circular imports.

---

## Extensibility rules

- **Add an expression** — new file in `analysis/expressions/`, add to `registry.py`. Touch nothing else.
- **Add an alert** — new file in `alerts/`, add to `registry.py`. Touch nothing else.
- **Add a config key** — add a tuple to `config_defaults.py`. It seeds on next launch.
- **Add a DB query group** — new file in `storage/db/`. No raw SQL anywhere else.
- **Add a report section** — new file in `reporting/builder/`. Wire into `__init__.py`.
