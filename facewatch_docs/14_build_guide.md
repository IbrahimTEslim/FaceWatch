# FaceWatch — Build Guide & Implementation Order

## Prerequisites

```
Python 3.10+
mediapipe==0.10.35
deepface
opencv-python
numpy
filterpy          # SORT dependency
jinja2
plyer
psutil
pywin32           # Windows only — for active window detection
```

### Install
```bash
pip install mediapipe==0.10.35 deepface opencv-python numpy filterpy jinja2 plyer psutil

# Windows only:
pip install pywin32

# macOS only:
pip install pyobjc

# Linux only (also needs system package):
# sudo apt install xdotool
```

### SORT Tracker
```bash
# Option 1: pip
pip install sort-tracker

# Option 2: clone (more reliable)
git clone https://github.com/abewley/sort
# Copy sort.py into utils/facewatch/ or add to PYTHONPATH
```

### Models
Download and place in `models/` directory:
- `face_landmarker.task` — from MediaPipe model card
  URL: https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task

---

## Implementation Order

Build in this exact order. Each step depends on the previous.
Do NOT skip ahead — later modules depend on earlier ones.

### Step 1 — Storage Foundation
```
storage/database.py
storage/config_store.py
config_defaults.py
```
Everything else reads from DB. Build this first, test with a simple script.

### Step 2 — Core Detection
```
core/detector.py
core/tracker.py
```
Get camera + MediaPipe + SORT working. Verify bounding boxes appear on screen.
Test: faces get stable track_ids across frames.

### Step 3 — Recognition
```
core/recognizer.py
```
Add DeepFace embedding + search + register.
Test: click unknown face → type name → face turns green.

### Step 4 — Expressions
```
analysis/expressions/base.py
analysis/expressions/blink.py
analysis/expressions/smile.py
analysis/expressions/angry.py
analysis/expressions/surprised.py
analysis/expressions/drowsy.py
analysis/expressions/neutral.py
analysis/expressions/registry.py
```
Test: expression bars appear, counts increment correctly.

### Step 5 — Gaze
```
analysis/gaze.py
```
Test: direction changes as you look around. Hysteresis works (brief glance doesn't reset).

### Step 6 — Distance
```
analysis/distance.py
demographics/face_width.py
demographics/analyzer.py
```
Test: distance estimate appears. Changes as you move closer/further.

### Step 7 — Alerts
```
alerts/base.py
alerts/gaze_alert.py
alerts/proximity_alert.py
alerts/registry.py
```
Test: look away for 10 sec → alert fires. Look back for 3 sec → alert clears.

### Step 8 — App Tracking
```
storage/app_tracker.py
```
Test: active app name appears in UI overlay.

### Step 9 — Stats Writing
Wire stats writing in engine.py.
Test: after 5 seconds, check DB has a stats row with correct values.

### Step 10 — Calibration Wizard
```
calibration/store.py
calibration/wizard.py
```
Test: run --calibrate, complete all steps, verify calibration table has values.

### Step 11 — UI
```
ui/renderer.py
ui/input_handler.py
```
Move all cv2 drawing from engine.py into renderer.py.
Test: all overlays appear correctly.

### Step 12 — Reporting
```
reporting/builder.py
reporting/server.py
reporting/notifier.py
reporting/reporter.py
reporting/templates/report.html.j2
reporting/templates/config.html.j2
```
Test: trigger report manually → browser opens → data is correct.

### Step 13 — Engine Cleanup
```
engine.py
```
Wire everything together cleanly. Add CLI args. Add startup sequence.
Final test: full end-to-end run.

---

## Testing Each Module

### database.py
```python
db = Database("test.db")
db.seed_config("test_key", 42, "int", "test", "test")
assert db.get_config("test_key") == "42"
db.write_stats(face_id=1, stats={...})
rows = db.query_stats(face_id=1, date="2024-01-15")
assert len(rows) > 0
```

### recognizer.py
```python
# Register a face, then search for it
recognizer.register(track_id=1, name="TestFace")
identity = recognizer.get_identity(1)
assert identity.name == "TestFace"
assert identity.status == "known"
```

### gaze.py
```python
# Simulate off-screen for 11 seconds (> gaze_alert_sec=10)
for i in range(330):   # 330 frames × 33ms = ~11 seconds
    state = gaze.update(mock_landmarks_looking_left, dt=0.033, config=config)
assert state.alert_active == True

# Simulate return for 2 seconds (< gaze_return_sec=3) — should NOT clear
for i in range(60):
    state = gaze.update(mock_landmarks_center, dt=0.033, config=config)
assert state.alert_active == True   # still active

# Simulate return for 4 seconds (> gaze_return_sec=3) — should clear
for i in range(120):
    state = gaze.update(mock_landmarks_center, dt=0.033, config=config)
assert state.alert_active == False
```

### alerts/base.py
```python
alert = GazeAlert()
# Condition true for 9 seconds — should NOT fire (< 10)
for _ in range(270): alert.update(True, 0.033, config)
assert not alert.active

# One more second — should fire
for _ in range(30): alert.update(True, 0.033, config)
assert alert.active
```

---

## File Creation Checklist

```
utils/facewatch/
├── [ ] __init__.py
├── [ ] config_defaults.py
├── core/
│   ├── [ ] __init__.py
│   ├── [ ] detector.py
│   ├── [ ] tracker.py
│   └── [ ] recognizer.py
├── analysis/
│   ├── [ ] __init__.py
│   ├── expressions/
│   │   ├── [ ] __init__.py
│   │   ├── [ ] base.py
│   │   ├── [ ] blink.py
│   │   ├── [ ] smile.py
│   │   ├── [ ] angry.py
│   │   ├── [ ] surprised.py
│   │   ├── [ ] drowsy.py
│   │   ├── [ ] neutral.py
│   │   └── [ ] registry.py
│   ├── [ ] gaze.py
│   └── [ ] distance.py
├── alerts/
│   ├── [ ] __init__.py
│   ├── [ ] base.py
│   ├── [ ] gaze_alert.py
│   ├── [ ] proximity_alert.py
│   └── [ ] registry.py
├── storage/
│   ├── [ ] __init__.py
│   ├── [ ] database.py
│   ├── [ ] config_store.py
│   └── [ ] app_tracker.py
├── demographics/
│   ├── [ ] __init__.py
│   ├── [ ] analyzer.py
│   └── [ ] face_width.py
├── calibration/
│   ├── [ ] __init__.py
│   ├── [ ] wizard.py
│   └── [ ] store.py
├── reporting/
│   ├── [ ] __init__.py
│   ├── [ ] reporter.py
│   ├── [ ] builder.py
│   ├── [ ] server.py
│   ├── [ ] notifier.py
│   └── templates/
│       ├── [ ] report.html.j2
│       └── [ ] config.html.j2
├── ui/
│   ├── [ ] __init__.py
│   ├── [ ] renderer.py
│   └── [ ] input_handler.py
└── [ ] engine.py
```

---

## Running FaceWatch

```bash
# Normal run (first run triggers calibration wizard)
python utils/facewatch/engine.py

# Specify camera
python utils/facewatch/engine.py --camera 1

# Force re-calibration
python utils/facewatch/engine.py --calibrate

# Refresh demographics for a specific face
python utils/facewatch/engine.py --refresh-demographics Ibrahim

# Reset all config to defaults
python utils/facewatch/engine.py --reset-config

# List available cameras
python utils/facewatch/engine.py --list-cameras

# Override report port
python utils/facewatch/engine.py --port 9000
```

---

## Project Root Context

```
d:\MyProjects\Python_Projects\MediaPipe\FirstTry\
├── models/
│   ├── face_landmarker.task
│   └── hand_landmarker.task
├── lessons/
│   └── 03_experiments/
│       ├── 3.2_face_recognition_v2.py   ← recognition reference
│       └── 3.4_expression_gaze_tracker.py ← expression/gaze reference
├── utils/
│   └── facewatch/                        ← build here
├── facewatch_docs/                       ← this documentation
├── facewatch.db                          ← created on first run
└── venv/
```

---

## Key Reference Files

When implementing, refer to these existing experiments:

| What you need | Reference file |
|---|---|
| SORT tracker usage | `lessons/03_experiments/3.2_face_recognition_v2.py` |
| DeepFace embedding + search | `lessons/03_experiments/3.2_face_recognition_v2.py` |
| Click-to-register UI | `lessons/03_experiments/3.2_face_recognition_v2.py` |
| Expression base class | `lessons/03_experiments/3.4_expression_gaze_tracker.py` |
| GazeTracker (pre-hysteresis) | `lessons/03_experiments/3.4_expression_gaze_tracker.py` |
| Blendshape names (all 52) | `lessons/03_experiments/3.4_expression_gaze_tracker.py` |
| Distance formula | `lessons/03_experiments/3.5_face_distance.py` |
| LIVE_STREAM async pattern | `lessons/03_experiments/3.2_face_recognition_v2.py` |
