<div align="center">

# 👁 FaceWatch

### Real-time face awareness for your desktop

**Knows who you are. Knows where you're looking. Knows when you're tired.**

*Runs entirely on your machine — no cloud, no data leaves your device.*

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)](#)
[![License](https://img.shields.io/badge/License-MIT-green)](#)
[![Privacy](https://img.shields.io/badge/Privacy-100%25%20Local-brightgreen)](#privacy)

</div>

---

FaceWatch watches your webcam, recognizes who's in front of it, tracks their expressions and gaze, measures their distance from the screen, and logs everything to a local SQLite database. At the end of the day it generates a styled HTML report and sends a desktop notification with a link to open it.

---

## What it does

| Capability | Details |
|---|---|
| **Face detection** | MediaPipe FaceLandmarker — 478 landmarks + 52 blendshapes per face |
| **Multi-face tracking** | SORT tracker — stable IDs across frames, survives brief occlusions |
| **Face recognition** | DeepFace (Facenet512) embeddings stored in SQLite — click to register |
| **Expression tracking** | Blink L/R, Smile, Angry, Surprised, Neutral, Drowsiness (PERCLOS) |
| **Gaze tracking** | ptgaze + affine calibration — maps eye direction to screen coordinates |
| **Distance estimation** | Cheekbone pixel width + focal length calibration → cm from camera |
| **Demographics** | DeepFace age/gender/race — runs once per face in background, weekly refresh |
| **Focus Score** | Composite 0–100 score: gaze + drowsiness + distraction + posture |
| **Smart alerts** | Dual-threshold hysteresis — fires only after sustained condition, clears only after sustained recovery |
| **Active app tracking** | Logs foreground app + window title at every stats interval |
| **Daily HTML report** | Chart.js charts, session timeline, app breakdown, expression stats |
| **Settings UI** | Native PyQt6 settings window — no browser needed |
| **Calibration wizard** | Focal length + 9-point gaze calibration with Kalman tune pass |

---

## Alerts

All alerts use dual-threshold hysteresis — a brief glance back at the screen won't clear a gaze alert, and moving back for one second won't clear a proximity alert.

| Alert | Fires when | Default trigger |
|---|---|---|
| **Gaze** | Looking away from screen | 10 s continuously off-screen |
| **Proximity** | Too close to camera | 5 s under 40 cm |
| **Eye Strain** | Sustained close distance | 5 min continuously under 40 cm |
| **Fatigue Onset** | PERCLOS rising over session | After 45 min, PERCLOS rises ≥ 10% in 2 min window |
| **Work Reminder** | No break taken | 90 min without a meaningful break |

All thresholds are configurable.

---

## Getting started

**Requirements:** Python 3.10+, a webcam

```bash
# Clone and run — setup.py creates the venv and installs everything
git clone https://github.com/IbrahimTEslim/FaceWatch.git
cd FaceWatch
python setup.py
```

On first launch, FaceWatch seeds the database with defaults and opens the camera. No calibration is required to start — calibrate later for better accuracy.

---

## Registering a face

When an unknown face appears, a bounding box is drawn around it labeled `pending` or `unknown`.

- **Left-click** the box → type a name → press Enter to register
- **Double-click** a known face box → rename it
- **Right-click** any face box → context menu with more options

---

## Keyboard shortcuts

| Key | Action |
|---|---|
| `H` | Toggle help overlay (shows all shortcuts) |
| `C` | Start calibration wizard |
| `D` | Toggle debug panel |
| `F` | Force re-identify unknown faces |
| `S` | Force stats write to DB |
| `O` | Open today's report in browser |
| `,` | Open settings window |
| `Q` | Quit |
| `ESC` | Cancel active calibration wizard |

---

## CLI options

```bash
python main.py                              # normal launch
python main.py --camera 1                  # use second webcam
python main.py --port 9000                 # report server on port 9000
python main.py --calibrate                 # force calibration wizard on launch
python main.py --refresh-demographics NAME # force re-run demographics for one face
python main.py --reset-config              # reset all settings to defaults
```

---

## Calibration

Two calibration wizards are available, both accessible from the right-click context menu on any face box or via the `C` key.

**Focal length** — sit at a known distance, type it in, hold still for 2 seconds. Improves distance accuracy from ±25% to ±5%.

**Gaze (9-point)** — look at each dot as it appears on screen. After the 9 points, a 3-point Kalman tune pass runs automatically. Per-face, stored in the database.

---

## Daily report

At 18:00 and 21:00 (configurable), FaceWatch:
1. Queries today's stats from SQLite
2. Renders an HTML report with Chart.js charts
3. Starts a local server at `http://localhost:8765`
4. Fires a desktop notification with a clickable link

The report includes: focus score timeline, expression stats, app breakdown by time and focus, hourly heatmap, gaze stats, distance stats, and the audit event log.

---

## Debug panel

Press `D` to open a separate debug window showing a card per tracked face with:
- Focus score bar
- Distance
- Gaze direction + off-screen timer
- Gaze calibration status
- Demographics (age, gender, race, face width)
- All expression values with live bars

---

## Privacy

- All processing is local — no internet connection required or used after setup
- No face images are ever saved to disk — only 512-dimensional embedding vectors
- Unknown faces are tracked in-session only — stats are not stored until a face is registered
- A `[H] Help` watermark is always visible in the camera window

---

## Project structure

```
utils/facewatch/
├── core/           detector, tracker, recognizer
├── analysis/       expressions, gaze, distance, focus score
├── alerts/         gaze, proximity, eye strain, fatigue, work reminder
├── calibration/    focal wizard, gaze wizard, calibration store
├── demographics/   DeepFace analyzer, face width lookup
├── storage/        SQLite database, config store, app tracker
├── ui/             renderer, input handler, mouse handler, settings, overlays
├── reporting/      Flask server, report builder, notifier
├── config_defaults.py
└── engine.py       main loop
```

---

## Documentation

Detailed technical documentation lives in the [`docs/`](docs/) directory:

| Document | Contents |
|---|---|
| [Architecture](docs/01_architecture.md) | Module layout, data flow, threading model, extensibility rules |
| [Math & Algorithms](docs/02_math_and_algorithms.md) | Distance formula, gaze ray math, PERCLOS, focus score, embedding search |
| [Database](docs/03_database.md) | Full SQLite schema, query groups, migrations |
| [Configuration Reference](docs/04_configuration.md) | Every config key with defaults and descriptions |
| [Developer Guide](docs/05_developer_guide.md) | Adding expressions/alerts, using modules as a library, HTTP API |

---

## Dependencies

| Package | Purpose |
|---|---|
| mediapipe 0.10.35 | Face landmarks + blendshapes |
| deepface | Face recognition + demographics |
| ptgaze | Gaze estimation |
| opencv-contrib-python | Camera capture + drawing |
| sort-tracker-py | Multi-face tracking |
| flask | Report HTTP server |
| PyQt6 | Settings window |
| plyer | Desktop notifications |
| psutil + pywin32/pyobjc/python-xlib | Active window detection |
| numpy, scipy, scikit-learn | Embedding math + Kalman filter |
