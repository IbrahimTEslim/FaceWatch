# FaceWatch — Alerts, Demographics, Focus Score

## alerts/base.py — Alert ABC

### Dual-Threshold Hysteresis Pattern
Every alert uses the same pattern:
- Enter alert: condition true for `ENTER_SEC` continuously
- Exit alert: condition false for `EXIT_SEC` continuously
- `EXIT_SEC` is always >= `ENTER_SEC` to prevent rapid toggling

```python
class Alert(ABC):
    @property
    @abstractmethod
    def enter_sec_key(self) -> str:
        """Config key for how long condition must be true to fire."""

    @property
    @abstractmethod
    def exit_sec_key(self) -> str:
        """Config key for how long condition must be false to clear."""

    def update(self, condition: bool, dt: float, config: ConfigStore) -> AlertEvent:
        """
        condition: True = bad thing is happening right now
        dt: seconds since last call
        Returns AlertEvent with fired/cleared/none status
        """

    @property
    def active(self) -> bool:
        """True if alert is currently in fired state."""

@dataclass
class AlertEvent:
    status:  str    # 'fired' | 'cleared' | 'none'
    message: str    # human-readable message for UI/log
```

### State Machine (same for all alerts)
```
IDLE:
    condition=True  → enter_timer += dt
                      if enter_timer >= ENTER_SEC → fire, → ACTIVE
    condition=False → enter_timer = 0

ACTIVE:
    condition=False → exit_timer += dt
                      if exit_timer >= EXIT_SEC → clear, → IDLE
    condition=True  → exit_timer = 0
```

---

## alerts/gaze_alert.py

```python
class GazeAlert(Alert):
    enter_sec_key = "gaze_alert_sec"    # default 10
    exit_sec_key  = "gaze_return_sec"   # default 3

    # condition = not gaze_state.on_screen
    # message when fired: "You've been looking away for {n} seconds"
    # message when cleared: "Gaze returned to screen"
```

---

## alerts/proximity_alert.py

```python
class ProximityAlert(Alert):
    enter_sec_key = "proximity_alert_sec"   # default 5
    exit_sec_key  = "proximity_clear_sec"   # default 8

    # condition = distance_cm < config.get("proximity_alert_cm")
    # message when fired: "Too close to camera ({n}cm). Move back."
    # message when cleared: "Distance OK"
```

---

## alerts/registry.py

```python
# ONLY file touched to add/remove alerts
from .gaze_alert import GazeAlert
from .proximity_alert import ProximityAlert

ALERTS: list[Alert] = [
    GazeAlert(),
    ProximityAlert(),
]
```

---

## demographics/face_width.py

### Face Width Lookup Table
```python
def estimate_face_width_cm(age: int, gender: str) -> float:
    """
    Returns estimated face width in cm based on age and gender.
    Used by distance.py for personalized distance calculation.

    Sources: anthropometric studies on facial dimensions.
    """
    if age < 5:
        base = 10.5
    elif age < 10:
        base = 11.5
    elif age < 13:
        base = 12.5
    elif age < 18:
        base = 13.2
    else:
        base = 14.0   # adult average

    # Female faces average ~0.5cm narrower than male
    if gender and gender.lower() in ("woman", "female", "f"):
        base -= 0.5

    return base
```

---

## demographics/analyzer.py

### Responsibility
Run DeepFace demographics analysis on a face crop.
Decide when to run (first time + weekly refresh).
Store results in `demographics` table via database.py.

### When to Run
```
On first identification of a face:
    → run immediately in background thread
    → store result

On subsequent sessions:
    → check demographics.last_updated for this face_id
    → if (now - last_updated) > demographics_refresh_days * 86400:
        → run in background thread
        → update stored result
    → else: use cached result

On --refresh-demographics NAME CLI flag:
    → force re-run regardless of last_updated
```

### DeepFace Call
```python
result = DeepFace.analyze(
    img_path=face_crop,
    actions=["age", "gender", "race"],
    detector_backend="skip",
    enforce_detection=False,
    silent=True,
)
age    = result[0]["age"]
gender = result[0]["dominant_gender"]
race   = result[0]["dominant_race"]
conf   = result[0]["gender"][gender]   # confidence score
face_width_cm = estimate_face_width_cm(age, gender)
```

### Interface
```python
class DemographicsAnalyzer:
    def __init__(self, db: Database, config: ConfigStore): ...

    def maybe_run(self, face_id: int, face_crop: np.ndarray) -> None:
        """Check if re-run needed. If yes, run in background thread."""

    def force_run(self, face_id: int, face_crop: np.ndarray) -> None:
        """Force re-run regardless of last_updated."""

    def get_face_width(self, face_id: int) -> float:
        """Get stored face_width_cm. Returns global default if not yet analyzed."""
```

---

## Focus Score

### What It Is
A single 0–100 composite score per stats interval.
Represents how focused/present the user was during that interval.

### Formula
```
focus_score = (
    gaze_score      * weight_gaze       +   # default 0.40
    drowsy_score    * weight_drowsy     +   # default 0.30
    calm_score      * weight_distract   +   # default 0.20
    posture_score   * weight_posture        # default 0.10
) * 100

Where:
    gaze_score    = 1.0 - (gaze_off_sec / interval_sec)
                  # 1.0 = always looking at screen, 0.0 = never

    drowsy_score  = 1.0 - drowsy_pct
                  # 1.0 = never drowsy, 0.0 = always drowsy

    calm_score    = 1.0 - ((angry_count + surprised_count) / max_expected_per_interval)
                  # clamped to [0, 1]

    posture_score = 1.0 if focus_posture_min_cm <= distance_cm <= focus_posture_max_cm
                  # else scaled by how far outside the range
```

All weights configurable in DB. Must sum to 1.0 (validated on write).

### Computed In
`engine.py` at each stats write interval, using data from all analysis modules.
Stored in `stats.focus_score`.

### Display
- Shown in UI overlay as a colored number (green > 70, yellow 40–70, red < 40)
- Shown in HTML report as a daily average with trend chart
- Streak system (v1.1): consecutive days with daily avg > 70

---

## PERCLOS — Drowsiness Detection

### What It Is
PERCLOS = Percentage of Eye Closure over a rolling time window.
Used in real driver monitoring systems (SAE standard).

### Calculation
```
rolling_window = last drowsy_window_sec seconds of frames (default 60)
closed_frames  = frames where avg(eyeBlinkLeft, eyeBlinkRight) > 0.8
PERCLOS        = closed_frames / total_frames_in_window

If PERCLOS > expr_threshold_drowsy (default 0.15):
    → drowsy = True
    → ProximityAlert-style alert fires (via alerts/registry)
```

### Why 0.8 threshold for "closed"
A normal blink peaks at ~0.9–1.0 and lasts ~150ms.
Drowsy eye closure is slower and stays above 0.8 for longer.
The PERCLOS metric captures this by looking at the fraction of time, not individual blinks.

### Implementation
`drowsy.py` maintains a `collections.deque` of recent blink values with a maxlen
calculated from `drowsy_window_sec * fps_estimate`. FPS estimated from frame timestamps.
