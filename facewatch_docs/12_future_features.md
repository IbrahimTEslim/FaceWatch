# FaceWatch — Future Features (v1.1 and v2.0)

## v1.1 Features

---

### Sound Alerts
- Library: `plyer` (cross-platform) — same lib used for desktop notifications
- Config key: `sound_alerts_enabled` (bool, default false)
- Config key: `sound_alert_volume` (float 0.0–1.0)
- Each alert type has its own sound file (short WAV)
- Sound files bundled in `assets/sounds/`
- Falls back silently if audio device unavailable

---

### Multi-Face Privacy Alert
- Fires when a second face enters the frame that is NOT the registered primary user
- Alert message: "Someone is looking at your screen"
- Config key: `privacy_alert_enabled` (bool, default true)
- Config key: `privacy_alert_sec` (int, default 2) — how long before alert fires
- Useful for remote workers, sensitive work environments
- Implementation: count known faces vs total tracked faces each frame

---

### Streak System
- A "streak" = consecutive calendar days where daily avg focus score > threshold
- Config key: `streak_threshold` (float, default 70.0)
- Stored in DB: new table `streaks (face_id, current_streak, best_streak, last_streak_date)`
- Shown in report header: "🔥 5-day streak!"
- Shown in UI overlay: small flame icon + streak count
- Streak breaks if user doesn't appear on camera for a full day

---

### Gaze Heatmap
- Accumulate gaze (horizontal_ratio, vertical_ratio) samples throughout the day
- At report time, render a 2D heatmap image using numpy + matplotlib (or pure numpy)
- Overlay on a screen diagram in the HTML report
- Shows where the user actually looks during work
- Stored as: `gaze_samples` table with (face_id, timestamp, h_ratio, v_ratio)
- Sampled at 1Hz (not every frame) to keep DB size reasonable

---

### Export API
```
GET /api/stats?face_id=1&from=2024-01-01&to=2024-01-31
→ JSON array of stats rows

GET /api/faces
→ JSON list of known faces with demographics

GET /api/summary?face_id=1&date=2024-01-15
→ JSON daily summary (same data as HTML report, machine-readable)
```

Enables integration with:
- Notion (via Notion API)
- Obsidian (via local REST plugin)
- Custom dashboards
- Any tool that can consume JSON

---

### Plugin System for Expressions
- Drop a `.py` file into `facewatch/analysis/expressions/plugins/`
- File must define a class inheriting from `Expression`
- `registry.py` auto-discovers and loads all files in `plugins/` on startup
- Community can share expression detectors as single files
- Example plugin: `wink.py`, `cheek_puff.py`, `tongue_out.py`

```python
# registry.py addition
import importlib
import glob

def _load_plugins() -> list[Expression]:
    plugins = []
    for path in glob.glob("analysis/expressions/plugins/*.py"):
        module = importlib.import_module(path_to_module(path))
        for name, cls in inspect.getmembers(module, inspect.isclass):
            if issubclass(cls, Expression) and cls is not Expression:
                plugins.append(cls())
    return plugins
```

---

### Anonymized Benchmarks
Built-in population averages for comparison:
```python
BENCHMARKS = {
    "blink_rate_per_min":   17,     # average adult: 15–20 blinks/min
    "focus_score_avg":      65,     # estimated population average
    "gaze_off_pct":         0.15,   # 15% of work time looking away
    "drowsy_pct":           0.05,   # 5% of work time drowsy
    "smile_per_hour":       12,     # average smiles per hour
}
```

Shown in report: "Your blink rate: 14/min. Average: 17/min. ⚠️ Possible eye strain."

---

## v2.0 Features — Game Dev Bridge

---

### FaceWatch SDK

FaceWatch runs as a background service. Games/apps import the SDK and query it.

```python
# In your game:
from facewatch import FaceWatchClient

client = FaceWatchClient()   # connects to running FaceWatch instance

# Get current state (blocking, returns latest)
state = client.get_state()

print(state.faces[0].name)           # "Ibrahim"
print(state.faces[0].expression)     # "smile"
print(state.faces[0].focus_score)    # 73.2
print(state.faces[0].distance_cm)    # 58.3
print(state.faces[0].gaze_direction) # "center"
print(state.faces[0].is_drowsy)      # False

# Subscribe to events (non-blocking callback)
@client.on("expression_change")
def on_expression(face, old_expr, new_expr):
    if new_expr == "angry":
        game.fire_ability()
```

Communication: Unix socket (macOS/Linux) or named pipe (Windows) for low latency.
Fallback: shared memory via `mmap`.

---

### Emotion-to-Game-Event YAML Mapping

```yaml
# facewatch_events.yaml — user configures this, no code changes needed

mappings:
  - expression: angry
    event: fire_ability
    cooldown_sec: 2.0

  - expression: surprised
    event: dodge_roll
    cooldown_sec: 0.5

  - expression: smile
    event: heal
    cooldown_sec: 5.0

  - gaze: left
    event: camera_left
    continuous: true    # fires every frame while active, not just on transition

  - blink_both: true    # both eyes blink simultaneously
    event: pause_game
    cooldown_sec: 1.0

  - focus_score_below: 40
    event: slow_motion  # game slows down when player is unfocused
```

FaceWatch reads this file and fires events via the SDK/WebSocket.

---

### WebSocket Broadcast

```python
# FaceWatch broadcasts face state as JSON over WebSocket
# Any language can connect — Unity, Godot, web games, etc.

# Message format (sent every frame):
{
    "timestamp": "2024-01-15T14:32:07.123Z",
    "faces": [
        {
            "id": 1,
            "name": "Ibrahim",
            "expression": "smile",
            "focus_score": 73.2,
            "distance_cm": 58.3,
            "gaze": "center",
            "is_drowsy": false,
            "blink_left": false,
            "blink_right": false,
            "alerts": []
        }
    ]
}
```

Unity example:
```csharp
// In Unity game
var ws = new WebSocket("ws://localhost:8766");
ws.OnMessage += (sender, e) => {
    var state = JsonUtility.FromJson<FaceWatchState>(e.Data);
    if (state.faces[0].expression == "angry") {
        FireAbility();
    }
};
```

---

### Multiplayer Face Sync

Two players, two cameras, one game:
- Player 1: FaceWatch instance on their machine, broadcasts on port 8766
- Player 2: FaceWatch instance on their machine, broadcasts on port 8766
- Game connects to both WebSocket streams
- Competitive focus tracking: "Your opponent's focus score: 81 vs yours: 67"
- Emotion reactions visible to both players

---

## Feature Priority Matrix

```
Impact × Effort:

HIGH IMPACT, LOW EFFORT (do first):
    ✅ Sound alerts
    ✅ Streak system
    ✅ Export API (/api/stats)

HIGH IMPACT, MEDIUM EFFORT:
    ✅ Plugin system
    ✅ Gaze heatmap
    ✅ WebSocket broadcast

HIGH IMPACT, HIGH EFFORT:
    ✅ FaceWatch SDK
    ✅ Emotion-to-event YAML
    ✅ Multiplayer face sync

LOW IMPACT, LOW EFFORT:
    ✅ Anonymized benchmarks
    ✅ Privacy alert
```
