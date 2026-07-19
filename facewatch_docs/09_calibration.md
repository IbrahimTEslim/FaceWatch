# FaceWatch — Calibration Wizard

## Purpose

Calibration personalizes FaceWatch to the specific user and camera setup.
Without calibration, FaceWatch uses population averages which can be 15–25% off.

Calibration runs automatically on first launch.
It is skipped on subsequent launches if calibration data exists in the DB.
It can be re-run at any time with `python engine.py --calibrate`.

---

## What Gets Calibrated

| Parameter | What it fixes | Stored in |
|---|---|---|
| `focal_length_px` | Distance accuracy | `calibration` table |
| `gaze_center_h` | Gaze direction accuracy (your natural center) | `calibration` table |
| `gaze_center_v` | Gaze direction accuracy (vertical) | `calibration` table |
| Expression thresholds | Per-user sensitivity | `config` table |

---

## Calibration Wizard Flow

The wizard runs as a sequence of steps inside the main camera window.
Each step shows instructions as an overlay. User presses SPACE to confirm each step.

### Step 1 — Welcome
```
overlay: "FaceWatch Calibration — First Time Setup"
         "This takes about 30 seconds."
         "Press SPACE to begin."
```

### Step 2 — Gaze Center Calibration
```
overlay: "Look directly at the center of your screen."
         "Hold still for 3 seconds."
         [progress bar counting down]

Action:
    - Collect 90 frames of gaze ratios (at ~30fps = 3 seconds)
    - Average horizontal_ratio and vertical_ratio
    - Store as calibration.gaze_center_h and calibration.gaze_center_v
    - Gaze thresholds become: center ± 0.15 (instead of hardcoded 0.35/0.65)
```

### Step 3 — Distance Calibration
```
overlay: "Sit at your normal working distance from the screen."
         "Press SPACE when ready, then hold still for 2 seconds."

         After SPACE:
         "Measuring... hold still."
         [progress bar]

         "Enter your distance from the camera in cm:"
         [number input field — default 60]
         "Press ENTER to confirm."

Action:
    - Measure pixel_width_px from landmarks 234 & 454 (cheekbones)
    - Average over 60 frames
    - Get face_width_cm from demographics if available, else use 14.0
    - focal_length_px = (pixel_width_px * known_distance_cm) / face_width_cm
    - Store in calibration.focal_length_px
```

### Step 4 — Expression Threshold Calibration (optional)
```
overlay: "Optional: Calibrate expression sensitivity."
         "Press SPACE to calibrate, or S to skip."
```

If user chooses to calibrate:

```
Sub-step 4a — Smile:
    overlay: "Smile naturally."
             [3 second countdown]
    Action: measure peak smile blendshape value
            set expr_threshold_smile = peak * 0.7 (70% of your max)
            store in config table

Sub-step 4b — Blink:
    overlay: "Blink normally a few times."
             [3 second countdown]
    Action: measure peak blink value
            set expr_threshold_blink = peak * 0.6

Sub-step 4c — Neutral baseline:
    overlay: "Relax your face. Look neutral."
             [3 second countdown]
    Action: measure all blendshape values at rest
            set expr_threshold_neutral = max_resting_value * 1.5
            (anything above 1.5x your resting max = an expression)
```

### Step 5 — Complete
```
overlay: "Calibration complete!"
         "focal_length: {value}px"
         "gaze_center: H={h:.2f} V={v:.2f}"
         "Press SPACE to start FaceWatch."
```

---

## Calibration Data Storage

```sql
-- calibration table rows written by wizard
INSERT OR REPLACE INTO calibration (key, value, calibrated_at) VALUES
    ('focal_length_px',  847.3,  '2024-01-15T10:00:00Z'),
    ('gaze_center_h',    0.52,   '2024-01-15T10:00:00Z'),
    ('gaze_center_v',    0.48,   '2024-01-15T10:00:00Z');

-- config table rows updated by expression calibration
UPDATE config SET value = '0.43' WHERE key = 'expr_threshold_smile';
UPDATE config SET value = '0.38' WHERE key = 'expr_threshold_blink';
```

---

## How Calibration Values Are Used at Runtime

### Gaze (analysis/gaze.py)
```python
# Instead of hardcoded thresholds:
center_h = calibration.get("gaze_center_h", default=0.5)
center_v = calibration.get("gaze_center_v", default=0.5)
margin   = 0.15   # ± from center

looking_left   = horizontal_ratio < center_h - margin
looking_right  = horizontal_ratio > center_h + margin
looking_up     = vertical_ratio   < center_v - margin
looking_down   = vertical_ratio   > center_v + margin
looking_center = not any of the above
```

### Distance (analysis/distance.py)
```python
focal_length_px = calibration.get("focal_length_px", default=None)
if focal_length_px is None:
    # Not calibrated — use rough estimate
    focal_length_px = 600.0   # reasonable default for most webcams
```

### Expressions (analysis/expressions/base.py)
```python
# Threshold read from config table (which was updated by calibration wizard)
threshold = config.get(self.threshold_key)
```

---

## Calibration Module Location

```
utils/facewatch/
└── calibration/
    ├── wizard.py       # Step sequencer, UI overlay, collects measurements
    └── store.py        # Read/write calibration table (thin wrapper over database.py)
```

`wizard.py` is called from `engine.py` on first run or when `--calibrate` flag is passed.
It uses `renderer.py` for all overlays (R6 — no cv2 calls outside renderer).
