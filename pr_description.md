# feat: eyetrax gaze calibration v2

## Overview

Full replacement of the iris-ratio gaze system with the eyetrax pipeline.
Gaze tracking now uses a trained Ridge regression model with head-pose-invariant
features, Kalman + EMA smoothing, and a multi-point calibration wizard with a
tune pass — matching eyetrax accuracy end to end.

---

## What Changed

### New Files
| File | Purpose |
|---|---|
| `calibration/gaze_estimator.py` | Eyetrax feature extractor (453-float head-pose-invariant vector + yaw/pitch/roll), Ridge model, blink detector (EAR), `CalibrationDetector` (VIDEO mode MediaPipe) |
| `calibration/smoother.py` | Kalman + EMA smoother per face, `tune_from_variance()` for post-calibration noise tuning |

### Modified Files
| File | What changed |
|---|---|
| `storage/db/connection.py` | Schema v4 — replaced `face_gaze_calibration` (center_h/v floats) with `face_gaze_model` (pickle blob), migration 4 |
| `storage/db/calibration.py` | `save_gaze_model` / `load_gaze_model` / `delete_gaze_model` using pickle |
| `calibration/store.py` | New `save_gaze_model` / `load_gaze_model` / `is_gaze_calibrated` API, removed dead `gaze_center_h/v` defaults |
| `calibration/wizard.py` | Replaced single-center `GazeWizard` with full multi-phase wizard: INTRO → WAITING → PULSE → CAPTURE → TRAINING → TUNE_PULSE → TUNE_CAPTURE → DONE. Configurable rows×cols grid (default 3×3), serpentine order, ESC to cancel, VIDEO-mode detector for synchronous landmark extraction |
| `analysis/gaze.py` | Replaced iris-ratio logic with full eyetrax pipeline: `extract_features` → `model.predict` → `smoother.step` → `(screen_x, screen_y)`. `GazeState` gains `screen_x`/`screen_y`, drops `horizontal_ratio`/`vertical_ratio` |
| `ui/calibration_overlay.py` | Full black background during calibration, normalized dot positions (0–1 ratios, converted to actual screen pixels by overlay process), pulse/capture arc animation, info panel at bottom |
| `engine.py` | Full wiring: `CalibrationDetector` lazy-init, grid rows/cols input flow before wizard start, auto gaze pointer during tune phase, model cache reset after training, ESC cancels wizard |
| `ui/renderer.py` | Added `draw_calibration_grid_input` panel, updated debug card to use `is_gaze_calibrated` |
| `config_defaults.py` | Added `gaze_edge_margin_px` (50px), `screen_w_px` (1920), `screen_h_px` (1080) |
| `demographics/analyzer.py` | Fixed naive/aware datetime mismatch in refresh check |

---

## Calibration Flow

```
User clicks "Calibrate Gaze" (known face only)
  → Enter grid rows (default 3)
  → Enter grid cols (default 3)
  → Overlay goes fullscreen black
  → INTRO: 4s instruction screen
  → WAITING: waits for stable non-blinking face
  → For each dot (serpentine order):
      PULSE  1.0s — dot pulses, no samples collected
      CAPTURE 1.5s — dot holds, countdown arc, features collected (blink frames skipped)
  → TRAINING: Ridge + StandardScaler fit, model saved to DB
  → TUNE (3 points): gaze pointer shown live, user looks at each dot,
      proximity + dwell detection, variance computed → Kalman measurementNoiseCov tuned
  → DONE
```

---

## Accuracy

Full eyetrax pipeline ported verbatim:
- **Feature extraction** — 453-float head-pose-invariant vector (eye landmarks rotated into face-aligned frame, normalized by inter-eye distance, + yaw/pitch/roll)
- **Model** — Ridge regression with StandardScaler (identical to eyetrax `RidgeModel`)
- **Smoother** — Kalman filter + EMA (identical to eyetrax `KalmanEMASmoother`)
- **Calibration detector** — VIDEO mode MediaPipe (synchronous, identical to eyetrax)
- **Blink rejection** — EAR-based, samples discarded on blink frames

---

## Architecture Notes

- `CalibrationDetector` is a separate VIDEO-mode MediaPipe instance used only during calibration — main engine detector stays LIVE_STREAM, no interference
- Model stored as pickle blob in `face_gaze_model` table, one per face_id, upserted on recalibration
- `GazeSmoother` is per-face, lives inside `GazeTracker`, tuned in-place after calibration
- Dot positions sent as normalized 0–1 ratios to overlay process, converted to actual screen pixels using `primaryScreen().geometry()` — correct on any resolution regardless of config values

---

## Breaking Changes

- `face_gaze_calibration` table dropped (migration 4 handles existing DBs)
- `GazeState.horizontal_ratio` / `vertical_ratio` removed → `screen_x` / `screen_y`
- `CalibrationStore.save_gaze_center` / `get_gaze_center` removed
- `GazeWizard` constructor signature changed — requires `smoother`, `sw`, `sh`, `detector`, optional `rows`/`cols`
