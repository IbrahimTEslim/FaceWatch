# FaceWatch — Project Overview

## What Is FaceWatch

FaceWatch is a local, privacy-first, real-time face awareness tool built on MediaPipe and DeepFace.
It runs entirely on the user's machine — no cloud, no data leaves the device.

It detects faces, tracks them across frames, recognizes known people, analyzes expressions,
tracks gaze, measures camera distance, logs everything to a local SQLite database, and generates
a styled HTML daily report.

It is also designed as a game dev SDK — a running background service that any game or app
can query in real-time to get face state, emotions, focus score, and fire game events from
facial expressions.

---

## Tool Name
**FaceWatch**

---

## Core Goals

1. Know WHO is in front of the camera (face recognition)
2. Know HOW they feel (expression tracking)
3. Know WHERE they are looking (gaze tracking)
4. Know HOW FAR they are (distance estimation)
5. Know WHAT app they are focused on (active app tracking)
6. Store all of this over time (SQLite DB)
7. Report insights daily (HTML report, local HTTP server)
8. Alert the user when something needs attention (gaze away, too close, drowsy)
9. Be extensible — new expressions, new alerts, new features with minimal code changes
10. Be a game dev bridge — expose a Python SDK and WebSocket stream

---

## Non-Goals (v1.0)

- No cloud sync
- No PDF export (cross-platform complexity — deferred)
- No sound alerts (deferred to v1.1)
- No multiplayer face sync (v2.0)
- No mobile support

---

## Target Platforms

- Windows (primary)
- macOS
- Linux

All three must work. No OS-specific dependencies in core logic.

---

## Python Version
3.10+

---

## Key Dependencies

| Package | Purpose |
|---|---|
| mediapipe 0.10.35 | Face landmarks, blendshapes, iris tracking |
| deepface | Face recognition embeddings + demographics |
| opencv-python | Camera capture, frame drawing |
| numpy | Embedding math |
| filterpy / sort | SORT multi-object tracker |
| jinja2 | HTML report templating |
| plyer | Cross-platform desktop notifications |
| psutil | Active window / foreground app detection |
| sqlite3 | Built-in Python, no install needed |

---

## Version Roadmap

### v1.0 — Core Tool
- Face detection, tracking, recognition
- Expression stats: blink L/R, smile, angry, surprised, neutral, drowsiness (PERCLOS)
- Focus Score (composite 0–100)
- Gaze alert with hysteresis
- Proximity alert with hysteresis
- Dynamic face width via DeepFace demographics
- Active app tracking per stats interval (with full timestamp)
- HTML report + local HTTP server + desktop notification
- Config stored in DB, editable via browser
- Calibration wizard (gaze baseline + focal length + per-expression thresholds)
- Session timeline in report

### v1.1 — Polish
- Sound alerts (cross-platform via plyer)
- Multi-face privacy alert (second unknown face enters frame)
- Streak system (consecutive high-focus days)
- Gaze heatmap in report
- Export API (`/api/stats` JSON endpoint)
- Plugin system for expressions (drop `.py` into plugins/, auto-loads)
- Anonymized benchmarks (compare stats to population averages)

### v2.0 — Game Dev Bridge
- FaceWatch SDK (`from facewatch import FaceWatchClient`)
- Emotion-to-game-event YAML mapping
- WebSocket broadcast of face state
- Multiplayer face sync (two cameras, one game)

---

## Privacy Principles

- All processing is local — no internet connection required or used
- No face images are ever saved to disk — only embeddings (mathematical vectors)
- Unknown faces are tracked in-session only — stats not stored until face is registered
- A visible "PRIVATE — Local Only" badge is shown in the UI at all times
- Audit log records every registration, config change, and alert
