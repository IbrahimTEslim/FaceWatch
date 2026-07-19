# FaceWatch — Analysis Modules

## analysis/expressions/base.py

### Expression ABC
Every expression inherits from this. The base class handles all state logic.
Subclasses only implement `compute_activation()`.

```python
class Expression(ABC):
    name:           str     # display name
    color:          tuple   # BGR color for UI bars
    threshold_key:  str     # config key to read threshold from e.g. 'expr_threshold_smile'
    cooldown_sec:   float   # min seconds between counted events
    count_events:   bool    # whether to count activations

    # Base class manages these — subclass never touches them
    _active:        bool
    _count:         int
    _current_value: float
    _last_trigger:  float
    _activation_start: float

    @abstractmethod
    def compute_activation(self, blendshapes: dict, landmarks: list) -> float:
        """Return 0.0–1.0. Base class handles threshold, state, counting."""

    def update(self, blendshapes: dict, landmarks: list, config: ConfigStore) -> None:
        """Called every frame. Reads threshold from config (live-updatable)."""

    # Properties
    @property def active(self) -> bool: ...
    @property def count(self) -> int: ...
    @property def value(self) -> float: ...
    @property def duration(self) -> float: ...  # seconds continuously active
    def reset(self) -> None: ...
    def get_interval_stats(self) -> dict: ...   # returns counts since last call, then resets
```

### Key Design: `get_interval_stats()`
Called every `stats_interval_sec`. Returns delta counts since last call, then resets internal
delta counters. This is how stats rows get their values — not cumulative totals.

```python
def get_interval_stats(self) -> dict:
    stats = {
        "count": self._interval_count,
        "active_frames": self._interval_active_frames,
        "total_frames": self._interval_total_frames,
    }
    self._interval_count = 0
    self._interval_active_frames = 0
    self._interval_total_frames = 0
    return stats
```

---

## analysis/expressions/ — Concrete Expressions

### blink.py — BlinkLeft, BlinkRight
```python
# Blendshapes: eyeBlinkLeft, eyeBlinkRight
# threshold_key: 'expr_threshold_blink'
# cooldown_sec: 0.2  (blinks are fast)
# Each eye is a separate Expression instance
```

### smile.py — Smile
```python
# Blendshapes: average(mouthSmileLeft, mouthSmileRight)
# threshold_key: 'expr_threshold_smile'
# cooldown_sec: 1.0  (don't count same smile multiple times)
```

### angry.py — Angry
```python
# Blendshapes: browDown (60%) + mouthFrown (40%) weighted
# threshold_key: 'expr_threshold_angry'
# cooldown_sec: 1.5
```

### surprised.py — Surprised
```python
# Blendshapes: average(browOuterUpLeft, browOuterUpRight, browInnerUp)
# threshold_key: 'expr_threshold_surprised'
# cooldown_sec: 1.0
```

### neutral.py — Neutral
```python
# Special: NOT a blendshape expression
# compute_activation returns 1.0 if ALL other expressions are below their thresholds
# threshold_key: 'expr_threshold_neutral' (max any-expression value to count as neutral)
# Requires reference to all other expressions in the registry
# neutral_pct in stats = (neutral_frames / total_frames) * 100
```

### drowsy.py — Drowsiness (PERCLOS)
```python
# PERCLOS = Percentage of Eye Closure
# Rolling window of `drowsy_window_sec` seconds
# Count frames where average(eyeBlinkLeft, eyeBlinkRight) > 0.8
# PERCLOS = closed_frames / total_frames_in_window
# If PERCLOS > expr_threshold_drowsy → drowsy alert
# This is the metric used in real driver monitoring systems
```

---

## analysis/expressions/registry.py

```python
# ONLY file touched to add/remove expressions
# To add: create file, import here, add to EXPRESSIONS list
# To ignore: comment out from EXPRESSIONS list

from .blink import BlinkLeft, BlinkRight
from .smile import Smile
from .angry import Angry
from .surprised import Surprised
from .neutral import Neutral
from .drowsy import Drowsy

EXPRESSIONS: list[Expression] = [
    BlinkLeft(),
    BlinkRight(),
    Smile(),
    Angry(),
    Surprised(),
    Drowsy(),
    Neutral(),   # Neutral must be last — it reads all others
]
```

---

## analysis/gaze.py

### Responsibility
Track gaze direction using iris landmark positions relative to eye corners.
Implement dual-threshold hysteresis for on/off screen state.

### Iris Landmark Indices (MediaPipe 478-point model)
```
Left eye:   outer=33,  inner=133, top=159, bottom=145, iris_center=468
Right eye:  outer=362, inner=263, top=386, bottom=374, iris_center=473
```

### Gaze Ratio Calculation
```
horizontal_ratio = (iris_x - outer_corner_x) / (inner_corner_x - outer_corner_x)
    0.0 = looking fully left (outer corner)
    0.5 = looking center
    1.0 = looking fully right (inner corner)

vertical_ratio = (iris_y - top_eyelid_y) / (bottom_eyelid_y - top_eyelid_y)
    0.0 = looking up
    0.5 = looking center
    1.0 = looking down
```

Average of both eyes for each ratio.

### Direction Classification
```
if vertical < 0.35  → "up"
if vertical > 0.65  → "down"
if horizontal < 0.35 → "left"
if horizontal > 0.65 → "right"
else                 → "center"
```

Calibration wizard sets the user's personal center baseline (stored in `calibration` table).
Thresholds are offset from that baseline, not hardcoded 0.35/0.65.

### Hysteresis State Machine
```
States: ON_SCREEN | OFF_SCREEN

ON_SCREEN:
    if direction != "center":
        off_screen_timer += dt
        if off_screen_timer >= gaze_alert_sec:
            → transition to OFF_SCREEN, fire alert
    else:
        off_screen_timer = 0   # reset immediately when looking at screen

OFF_SCREEN:
    if direction == "center":
        return_timer += dt
        if return_timer >= gaze_return_sec:
            → transition to ON_SCREEN, clear alert
    else:
        return_timer = 0   # reset if they look away again during return window
```

This is the key logic: a brief glance at the screen does NOT clear the alert.
The user must look at the screen continuously for `gaze_return_sec` seconds.

### Interface
```python
class GazeTracker:
    def update(self, landmarks: list, dt: float, config: ConfigStore) -> GazeState: ...

@dataclass
class GazeState:
    horizontal_ratio:   float
    vertical_ratio:     float
    direction:          str     # 'center'|'left'|'right'|'up'|'down'
    on_screen:          bool    # hysteresis-filtered state
    off_screen_sec:     float   # how long currently off-screen (for stats)
    alert_active:       bool    # True when gaze alert has fired
```

---

## analysis/distance.py

### Responsibility
Estimate face distance from camera using the known-size formula.
Uses per-face `face_width_cm` from demographics (not a global constant).

### Formula
```
Distance_cm = (face_width_cm * focal_length_px) / pixel_width_px

Where:
    face_width_cm    = from demographics table (personalized per face)
    focal_length_px  = from calibration table (set during calibration wizard)
    pixel_width_px   = distance between landmarks 234 (left cheekbone) and
                       454 (right cheekbone) in pixels
```

Landmarks 234 & 454 (cheekbones) are the most stable horizontal pair.
More reliable than bounding box width (which includes padding).

### Focal Length Calibration
```
focal_length_px = (pixel_width_px * known_distance_cm) / face_width_cm

During calibration wizard:
    - User sits at known distance (e.g. 60cm)
    - Wizard measures pixel_width_px from landmarks
    - Computes focal_length_px and stores in calibration table
```

### Interface
```python
class DistanceEstimator:
    def estimate(self, landmarks: list, face_width_cm: float,
                 focal_length_px: float, frame_w: int) -> float:
        """Returns distance in cm. Returns -1.0 if landmarks unavailable."""
```

### Accuracy Notes
- Strong head yaw shrinks cheekbone pixel distance → accuracy degrades at angles
- `face_width_cm` from demographics is an estimate (±2cm) — affects accuracy
- Focal length in px ≠ focal length in mm (px version is what we use)
- Children: ~10.5–12cm face width. Adults: ~13.5–14.5cm. Female: ~0.5cm less than male
