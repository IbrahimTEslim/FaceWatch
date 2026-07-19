# FaceWatch — Database Schema

## Engine
SQLite — built into Python, zero setup, single file, atomic transactions, cross-platform.

## File Location
Configured via `db_path` in config table. Default: `facewatch.db` in the tool root.

## Serialization Rule
Embeddings are stored as raw bytes using `numpy.save()` into a `BytesIO` buffer — NOT pickle.
This is Python-version-safe and numpy-version-safe.

```python
# Store
buf = io.BytesIO()
np.save(buf, embedding_array)
blob = buf.getvalue()   # store this BLOB in DB

# Load
buf = io.BytesIO(blob_from_db)
embedding_array = np.load(buf)
```

---

## Tables

### `faces` — Identity Registry

```sql
CREATE TABLE IF NOT EXISTS faces (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    status      TEXT NOT NULL DEFAULT 'unknown',  -- 'known' | 'unknown'
    created_at  TEXT NOT NULL,                    -- ISO 8601 UTC
    last_seen   TEXT                              -- ISO 8601 UTC
);
```

- `id` is the foreign key used by ALL other tables — never `name`
- `name` can be renamed freely without breaking any other table
- `status` = 'unknown' until user clicks to register the face

---

### `embeddings` — Face Embedding Vectors

```sql
CREATE TABLE IF NOT EXISTS embeddings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    face_id     INTEGER NOT NULL REFERENCES faces(id) ON DELETE CASCADE,
    data        BLOB NOT NULL,      -- numpy array via np.save(), NOT pickle
    created_at  TEXT NOT NULL       -- ISO 8601 UTC
);
```

- Multiple embeddings per face (up to `max_embeddings_per_face` config value)
- Diverse embeddings selected via greedy max-distance algorithm (see recognizer.py)
- On DELETE CASCADE — deleting a face removes all its embeddings automatically

---

### `demographics` — DeepFace Estimates Per Face

```sql
CREATE TABLE IF NOT EXISTS demographics (
    face_id         INTEGER PRIMARY KEY REFERENCES faces(id) ON DELETE CASCADE,
    age_estimate    INTEGER,
    gender          TEXT,
    race            TEXT,
    face_width_cm   REAL,       -- computed from age + gender via face_width.py
    confidence      REAL,       -- DeepFace confidence score
    last_updated    TEXT        -- ISO 8601 UTC — weekly re-run check uses this
);
```

- One row per face
- `face_width_cm` is what distance.py uses — personalized per face
- `last_updated` checked on each session: if > `demographics_refresh_days` ago → re-run

---

### `stats` — Time-Series Behavioral Data

```sql
CREATE TABLE IF NOT EXISTS stats (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    face_id             INTEGER NOT NULL REFERENCES faces(id) ON DELETE CASCADE,
    timestamp           TEXT NOT NULL,      -- ISO 8601 UTC full timestamp (date + time)
    interval_sec        INTEGER NOT NULL,   -- actual interval length (may vary)

    -- Expression counts (delta since last write, not cumulative)
    blink_left          INTEGER DEFAULT 0,
    blink_right         INTEGER DEFAULT 0,
    smile_count         INTEGER DEFAULT 0,
    angry_count         INTEGER DEFAULT 0,
    surprised_count     INTEGER DEFAULT 0,
    neutral_pct         REAL    DEFAULT 0.0,  -- % of frames in interval that were neutral
    drowsy_pct          REAL    DEFAULT 0.0,  -- PERCLOS value for this interval

    -- Physical state
    distance_cm         REAL,               -- average distance over interval
    gaze_off_sec        REAL    DEFAULT 0.0, -- seconds looking away in this interval
    proximity_alerts    INTEGER DEFAULT 0,   -- how many proximity alerts fired

    -- Focus
    focus_score         REAL    DEFAULT 0.0, -- 0–100 composite score for this interval

    -- Active app (what the user was doing)
    active_app          TEXT,               -- process name e.g. "chrome.exe", "code.exe"
    active_window_title TEXT,               -- window title e.g. "FaceWatch - VS Code"
    app_category        TEXT                -- 'browser','editor','game','other' (derived)
);
```

- Written every `stats_interval_sec` (default 5) for known faces only
- `timestamp` is full ISO 8601 with time — enables "which hour of day" queries
- `active_app` + `active_window_title` captured via psutil at write time
- `app_category` derived from `active_app` name using a simple lookup table
- Unknown faces: no stats written until registered

---

### `config` — Runtime Configuration

```sql
CREATE TABLE IF NOT EXISTS config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    type        TEXT NOT NULL,      -- 'int' | 'float' | 'str' | 'bool' | 'list'
    description TEXT,
    category    TEXT                -- 'camera'|'storage'|'recognition'|'gaze'|
                                    -- 'proximity'|'expressions'|'demographics'|'report'
);
```

- Seeded from `config_defaults.py` on first run (INSERT OR IGNORE — never overwrites user changes)
- All runtime reads go through `ConfigStore.get(key)` — never read `config_defaults.py` directly
- Editable via browser at `localhost:PORT/config`
- Expression thresholds stored here as `expr_threshold_blink`, `expr_threshold_smile`, etc.

---

### `calibration` — Per-User Calibration Data

```sql
CREATE TABLE IF NOT EXISTS calibration (
    key         TEXT PRIMARY KEY,   -- 'focal_length_px', 'gaze_center_h', 'gaze_center_v',
                                    -- 'expr_smile_personal', etc.
    value       REAL NOT NULL,
    calibrated_at TEXT NOT NULL     -- ISO 8601 UTC
);
```

- Written by the Calibration Wizard on first run
- Overrides config defaults for physical measurements
- `focal_length_px` — calibrated from known distance, replaces population estimate
- `gaze_center_h/v` — user's natural resting gaze position (not always dead center)

---

### `audit_log` — Immutable Event Log

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,      -- ISO 8601 UTC
    event_type  TEXT NOT NULL,      -- 'face_registered'|'face_renamed'|'config_changed'|
                                    --  'alert_fired'|'session_start'|'session_end'
    details     TEXT                -- JSON string with event-specific data
);
```

- Append-only — never updated or deleted
- Every face registration, rename, config change, alert fire is logged here
- Used in report for "events today" section

---

## Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_stats_face_id   ON stats(face_id);
CREATE INDEX IF NOT EXISTS idx_stats_timestamp ON stats(timestamp);
CREATE INDEX IF NOT EXISTS idx_stats_app       ON stats(active_app);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
```

---

## Migration Strategy

- Schema version stored in SQLite `PRAGMA user_version`
- `database.py` checks version on startup and runs migration functions if needed
- Each migration is a numbered function: `_migrate_v1_to_v2()`, etc.
- Never DROP columns — only ADD (SQLite limitation + safety)

---

## Key Query Examples

```sql
-- Today's stats for a known face
SELECT * FROM stats
WHERE face_id = ? AND timestamp LIKE '2024-01-15%'
ORDER BY timestamp;

-- Which app was used most today
SELECT active_app, SUM(interval_sec) as total_sec
FROM stats
WHERE face_id = ? AND timestamp LIKE '2024-01-15%'
GROUP BY active_app
ORDER BY total_sec DESC;

-- Average focus score by hour of day
SELECT substr(timestamp, 12, 2) as hour, AVG(focus_score)
FROM stats
WHERE face_id = ?
GROUP BY hour
ORDER BY hour;

-- Emotion breakdown for a specific app
SELECT active_app,
       SUM(smile_count), SUM(angry_count), SUM(surprised_count)
FROM stats
WHERE face_id = ?
GROUP BY active_app;

-- Days with focus score > 70 (for streak calculation)
SELECT DATE(timestamp) as day, AVG(focus_score) as daily_avg
FROM stats
WHERE face_id = ?
GROUP BY day
HAVING daily_avg > 70
ORDER BY day;
```
