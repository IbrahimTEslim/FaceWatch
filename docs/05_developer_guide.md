# Developer Guide

This document covers how to extend FaceWatch, use it as a library, and integrate with it from external code.

---

## Adding a custom expression

Create a new file in `utils/facewatch/analysis/expressions/`:

```python
# analysis/expressions/wink.py
from .base import Expression

class Wink(Expression):
    name          = "wink"
    color         = (0, 200, 255)   # BGR
    threshold_key = "expr_threshold_wink"   # add this key to config_defaults.py
    cooldown_sec  = 0.5

    def compute_activation(self, blendshapes: dict, landmarks: list) -> float:
        left  = blendshapes.get("eyeBlinkLeft",  0.0)
        right = blendshapes.get("eyeBlinkRight", 0.0)
        # Wink = one eye closed, other open
        return max(left * (1 - right), right * (1 - left))
```

Then register it in `analysis/expressions/registry.py`:

```python
from .wink import Wink

def build_expressions() -> list[Expression]:
    others = [..., Wink()]
    return others + [Neutral(others)]
```

Add the config key to `config_defaults.py`:

```python
("expr_threshold_wink", 0.60, "float", "Wink activation threshold.", "expressions"),
```

That's it. The expression will appear in the debug panel, be counted in stats, and be available in the report.

---

## Adding a custom alert

Create a new file in `utils/facewatch/alerts/`:

```python
# alerts/blink_rate_alert.py
from .base import Alert, AlertType, AlertPriority, AlertContext

class LowBlinkRateAlert(Alert):
    enter_sec_key      = "blink_alert_sec"
    exit_sec_key       = "blink_clear_sec"
    alert_type         = AlertType.EYE_STRAIN   # reuse or add a new AlertType enum value
    priority           = AlertPriority.LOW
    notification_title = "FaceWatch — Low Blink Rate"

    def is_condition_met(self, ctx: AlertContext) -> bool:
        return ctx.blink_rate_pm < 10.0   # fewer than 10 blinks/min

    def _fired_message(self) -> str:
        return "Low blink rate detected. Remember to blink."

    def _cleared_message(self) -> str:
        return "Blink rate back to normal."
```

Register it in `alerts/registry.py`:

```python
from .blink_rate_alert import LowBlinkRateAlert

def build_alerts() -> list[Alert]:
    return [..., LowBlinkRateAlert()]
```

Add config keys to `config_defaults.py`:

```python
("blink_alert_sec",  30, "int", "Seconds of low blink rate before alert fires.", "wellness"),
("blink_clear_sec",  60, "int", "Seconds of normal blink rate to clear alert.",  "wellness"),
```

The `AlertContext` available to every alert:

```python
@dataclass
class AlertContext:
    gaze_on_screen: bool
    dist_cm:        float
    config:         ConfigStore
    perclos:        float    # current PERCLOS value (0–1)
    blink_rate_pm:  float    # blinks per minute (left eye)
    session_sec:    float    # seconds since face first appeared
    last_break_sec: float    # seconds since last meaningful absence
```

---

## Reading data from the database directly

The SQLite database is at `facewatch.db` in the project root. It's a standard SQLite file — any SQLite client can read it.

Useful queries:

```sql
-- Today's stats for all known faces
SELECT f.display_name, s.*
FROM stats s
JOIN faces f ON f.id = s.face_id
WHERE s.timestamp >= date('now')
ORDER BY s.timestamp;

-- Average focus score per app today
SELECT active_app, AVG(focus_score) as avg_focus, COUNT(*) as intervals
FROM stats
WHERE timestamp >= date('now')
GROUP BY active_app
ORDER BY avg_focus DESC;

-- All known faces with demographics
SELECT f.display_name, d.age_estimate, d.gender, d.race, d.face_width_cm
FROM faces f
LEFT JOIN demographics d ON d.face_id = f.id
WHERE f.status = 'known';

-- Audit log for today
SELECT timestamp, event_type, details
FROM audit_log
WHERE timestamp >= date('now')
ORDER BY timestamp;
```

---

## Using FaceWatch modules as a library

The individual modules are importable independently. Add the `utils/` directory to your Python path:

```python
import sys
sys.path.insert(0, "path/to/FaceWatch/utils/facewatch")
```

### Face recognition only

```python
from storage.db import Database
from storage.config_store import ConfigStore
from core.recognizer import FaceRecognizer
import cv2

db     = Database("facewatch.db")
config = ConfigStore(db)
rec    = FaceRecognizer(db, config)

frame = cv2.imread("photo.jpg")
rec.submit(track_id=1, crop_bgr=frame)

# After a moment (runs async):
identity = rec.get_identity(1)
print(identity.display_name, identity.status, identity.similarity)
```

### Distance estimation only

```python
from analysis.distance import DistanceEstimator

estimator = DistanceEstimator()

# landmarks: list of MediaPipe NormalizedLandmark objects
# face_width_cm: 14.0 for adult average
# focal_length_px: from calibration, or ~600 as rough default
dist = estimator.estimate(landmarks, face_width_cm=14.0, focal_length_px=600.0, frame_w=640)
print(f"{dist:.1f} cm")
```

### Expression tracking only

```python
from analysis.expressions.registry import build_expressions

expressions = build_expressions()

# blendshapes: dict of {name: score} from MediaPipe
# landmarks: list of NormalizedLandmark
for expr in expressions:
    expr.update(blendshapes, landmarks, config)
    if expr.active:
        print(f"{expr.name}: {expr.value:.2f}")
```

### Focus score computation

```python
from analysis.focus import compute_focus_score

score = compute_focus_score(
    gaze_off_sec=2.5,
    interval_sec=5,
    drowsy_pct=0.03,
    angry_count=0,
    surprised_count=1,
    distance_cm=62.0,
    config=config,
)
print(f"Focus: {score}/100")
```

---

## HTTP API

When FaceWatch is running, the report server exposes a small API at `http://localhost:8765`:

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Redirect to dashboard |
| `/face/<name>` | GET | Per-face report page |
| `/history` | GET | Historical report browser |

The server is Flask-based. You can extend it by adding routes in `reporting/server.py`.

---

## WebSocket / real-time integration (roadmap)

A WebSocket broadcast of per-frame face state is planned for v2.0. It will allow any language or game engine to subscribe to live face events:

```json
{
  "timestamp": "2024-01-15T14:32:07",
  "faces": [
    {
      "name": "Ibrahim",
      "expression": "smile",
      "focus_score": 73.2,
      "distance_cm": 58.3,
      "gaze": "center",
      "is_drowsy": false,
      "alerts": []
    }
  ]
}
```

Until then, the database is the integration point — poll `stats` at your desired interval.

---

## Running tests

```bash
# From project root, with venv activated:
venv\Scripts\python.exe tests\test_step1_storage.py
venv\Scripts\python.exe tests\test_step4_expressions.py
# etc.
```

Each test file is self-contained and covers one build step. All tests passed at the time of the last commit — see `progress.md` for the full record.
