# FaceWatch — Config Defaults

## How Config Works

1. `config_defaults.py` defines all defaults as a list of tuples
2. On first run, `database.py` seeds the `config` table with INSERT OR IGNORE
3. All runtime reads go through `ConfigStore.get(key)` — reads from DB
4. User edits via browser at `localhost:PORT/config`
5. Changes take effect immediately — no restart needed
6. `config_defaults.py` is NEVER read at runtime after seeding

---

## Full Defaults Table

```python
# config_defaults.py
# Format: (key, default_value, type, description, category)

DEFAULTS = [

    # -------------------------------------------------------------------------
    # CAMERA
    # -------------------------------------------------------------------------
    ("camera_index",                0,          "int",
     "Webcam index. 0=first camera, 1=second, etc. Override with --camera CLI arg.",
     "camera"),

    # -------------------------------------------------------------------------
    # STORAGE
    # -------------------------------------------------------------------------
    ("db_path",                     "facewatch.db", "str",
     "Path to SQLite database file.",
     "storage"),

    ("max_embeddings_per_face",     10,         "int",
     "Max embedding vectors stored per face. More = better accuracy, more memory.",
     "storage"),

    ("stats_interval_sec",          5,          "int",
     "Seconds between stats writes to DB. Lower = more granular, more I/O.",
     "storage"),

    # -------------------------------------------------------------------------
    # RECOGNITION
    # -------------------------------------------------------------------------
    ("recognition_threshold",       0.60,       "float",
     "Cosine similarity threshold to accept a known face match. Range 0–1.",
     "recognition"),

    ("unknown_match_threshold",     0.70,       "float",
     "Similarity threshold to match an unknown re-entry to existing unknown entry.",
     "recognition"),

    ("max_retry_attempts",          7,          "int",
     "How many times to retry identifying an unknown face before giving up.",
     "recognition"),

    ("retry_interval_sec",          3,          "int",
     "Seconds between re-identification retry attempts for unknown faces.",
     "recognition"),

    ("enrichment_interval_sec",     2,          "int",
     "Seconds between collecting extra embeddings for known faces.",
     "recognition"),

    # -------------------------------------------------------------------------
    # GAZE ALERT
    # -------------------------------------------------------------------------
    ("gaze_alert_sec",              10,         "int",
     "Seconds looking off-screen before gaze alert fires.",
     "gaze"),

    ("gaze_return_sec",             3,          "int",
     "Seconds looking at screen continuously required to clear gaze alert. "
     "Prevents a brief glance from resetting the off-screen timer.",
     "gaze"),

    # -------------------------------------------------------------------------
    # PROXIMITY ALERT
    # -------------------------------------------------------------------------
    ("proximity_alert_cm",          40.0,       "float",
     "Distance in cm. Closer than this triggers proximity alert.",
     "proximity"),

    ("proximity_alert_sec",         5,          "int",
     "Seconds face must be too close before alert fires.",
     "proximity"),

    ("proximity_clear_sec",         8,          "int",
     "Seconds face must be far enough to clear proximity alert. "
     "Longer than alert_sec to prevent rapid on/off toggling.",
     "proximity"),

    # -------------------------------------------------------------------------
    # EXPRESSION THRESHOLDS
    # Each expression reads its own key via ConfigStore.get()
    # -------------------------------------------------------------------------
    ("expr_threshold_blink",        0.50,       "float",
     "Blink activation threshold. eyeBlinkLeft/Right blendshape score.",
     "expressions"),

    ("expr_threshold_smile",        0.50,       "float",
     "Smile activation threshold. Average of mouthSmileLeft + mouthSmileRight.",
     "expressions"),

    ("expr_threshold_angry",        0.45,       "float",
     "Angry activation threshold. Weighted browDown + mouthFrown.",
     "expressions"),

    ("expr_threshold_surprised",    0.40,       "float",
     "Surprised activation threshold. Average of browOuterUp + browInnerUp.",
     "expressions"),

    ("expr_threshold_neutral",      0.25,       "float",
     "Max activation value across ALL expressions to count a frame as neutral.",
     "expressions"),

    ("expr_threshold_drowsy",       0.15,       "float",
     "PERCLOS threshold. Fraction of frames in rolling window with eyes >80% closed.",
     "expressions"),

    ("drowsy_window_sec",           60,         "int",
     "Rolling window size in seconds for PERCLOS drowsiness calculation.",
     "expressions"),

    # -------------------------------------------------------------------------
    # DEMOGRAPHICS
    # -------------------------------------------------------------------------
    ("demographics_refresh_days",   7,          "int",
     "Days between DeepFace demographics re-runs per face.",
     "demographics"),

    # -------------------------------------------------------------------------
    # REPORT
    # -------------------------------------------------------------------------
    ("report_times",                "18:00,21:00", "list",
     "Comma-separated times (HH:MM 24h) to generate and serve daily report.",
     "report"),

    ("report_port",                 8765,       "int",
     "Local HTTP port for report server. Access at http://localhost:PORT",
     "report"),

    # -------------------------------------------------------------------------
    # FOCUS SCORE WEIGHTS (must sum to 1.0)
    # -------------------------------------------------------------------------
    ("focus_weight_gaze",           0.40,       "float",
     "Weight of gaze-on-screen percentage in Focus Score calculation.",
     "focus"),

    ("focus_weight_drowsy",         0.30,       "float",
     "Weight of non-drowsy percentage in Focus Score calculation.",
     "focus"),

    ("focus_weight_distraction",    0.20,       "float",
     "Weight of non-distracted (not angry/surprised) in Focus Score.",
     "focus"),

    ("focus_weight_posture",        0.10,       "float",
     "Weight of good posture (distance in healthy range) in Focus Score.",
     "focus"),

    ("focus_posture_min_cm",        45.0,       "float",
     "Minimum healthy distance from camera in cm for posture score.",
     "focus"),

    ("focus_posture_max_cm",        90.0,       "float",
     "Maximum healthy distance from camera in cm for posture score.",
     "focus"),
]
```

---

## ConfigStore API

```python
# storage/config_store.py

class ConfigStore:
    def get(self, key: str) -> int | float | str | bool | list:
        """Read a config value from DB, cast to correct type."""

    def set(self, key: str, value) -> None:
        """Write a config value to DB. Logs change to audit_log."""

    def get_all_by_category(self, category: str) -> list[dict]:
        """Returns all config rows for a category. Used by config editor page."""

    def reset_to_default(self, key: str) -> None:
        """Reset a single key to its value from config_defaults.py."""
```

---

## CLI Overrides

Some config values can be overridden at launch via CLI args.
CLI args take priority over DB config for that session only — they do NOT write to DB.

```
python engine.py --camera 1          # override camera_index
python engine.py --camera 1 --port 9000   # override camera + report port
python engine.py --calibrate         # run calibration wizard
python engine.py --refresh-demographics Ibrahim   # force re-run demographics for one face
python engine.py --reset-config      # reset ALL config to defaults
```
