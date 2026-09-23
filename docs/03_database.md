# Database

FaceWatch uses a single local SQLite file (`facewatch.db`) with WAL journal mode for concurrent read/write access between the main loop and background threads.

All SQL lives in `storage/db/` — one file per query group. No raw SQL anywhere else in the codebase.

---

## Schema

### `faces`
```sql
CREATE TABLE faces (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT UNIQUE NOT NULL,      -- normalized lowercase key
    display_name TEXT NOT NULL,             -- original casing shown in UI
    status       TEXT NOT NULL DEFAULT 'unknown',  -- 'known' | 'unknown'
    created_at   TEXT NOT NULL,
    last_seen    TEXT
)
```

### `embeddings`
```sql
CREATE TABLE embeddings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    face_id    INTEGER NOT NULL REFERENCES faces(id) ON DELETE CASCADE,
    data       BLOB NOT NULL,   -- np.save() serialized float32 array (512D)
    created_at TEXT NOT NULL
)
```

Embeddings are stored as raw numpy bytes via `np.save` / `np.load` with `io.BytesIO` — never pickle.

### `demographics`
```sql
CREATE TABLE demographics (
    face_id       INTEGER PRIMARY KEY REFERENCES faces(id) ON DELETE CASCADE,
    age_estimate  INTEGER,
    gender        TEXT,
    race          TEXT,
    face_width_cm REAL,
    confidence    REAL,
    last_updated  TEXT
)
```

### `stats`
```sql
CREATE TABLE stats (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    face_id             INTEGER NOT NULL REFERENCES faces(id) ON DELETE CASCADE,
    timestamp           TEXT NOT NULL,
    interval_sec        INTEGER NOT NULL,
    blink_left          INTEGER DEFAULT 0,
    blink_right         INTEGER DEFAULT 0,
    smile_count         INTEGER DEFAULT 0,
    angry_count         INTEGER DEFAULT 0,
    surprised_count     INTEGER DEFAULT 0,
    neutral_pct         REAL DEFAULT 0.0,
    drowsy_pct          REAL DEFAULT 0.0,
    distance_cm         REAL,
    gaze_off_sec        REAL DEFAULT 0.0,
    proximity_alerts    INTEGER DEFAULT 0,
    focus_score         REAL DEFAULT 0.0,
    active_app          TEXT,
    active_window_title TEXT,
    app_category        TEXT
)
```

Indexed on `face_id`, `timestamp`, and `active_app` for fast report queries.

### `config`
```sql
CREATE TABLE config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    type        TEXT NOT NULL,      -- 'int' | 'float' | 'str' | 'bool' | 'list'
    description TEXT,
    category    TEXT
)
```

All runtime config reads go through `ConfigStore.get(key)` which casts the stored string to the correct Python type.

### `calibration`
```sql
CREATE TABLE calibration (
    key           TEXT PRIMARY KEY,
    value         REAL NOT NULL,
    calibrated_at TEXT NOT NULL
)
```

Stores `focal_length_px` and any other scalar calibration values.

### `face_gaze_model`
```sql
CREATE TABLE face_gaze_model (
    face_id       INTEGER PRIMARY KEY REFERENCES faces(id) ON DELETE CASCADE,
    model_blob    BLOB NOT NULL,    -- pickle-serialized affine matrix (2x3 float64)
    calibrated_at TEXT NOT NULL
)
```

Per-face affine gaze model fitted during the 9-point calibration wizard.

### `audit_log`
```sql
CREATE TABLE audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  TEXT NOT NULL,
    event_type TEXT NOT NULL,
    details    TEXT            -- JSON string
)
```

Records: `face_registered`, `face_renamed`, `face_deleted`, `config_changed`, `alert_fired`, `alert_cleared`, `session_end`.

---

## Migrations

Schema version is tracked via `PRAGMA user_version`. Migrations run automatically on startup:

| Version | Change |
|---|---|
| 2 | Added `display_name` column to `faces` |
| 3 | Added `face_gaze_calibration` table (later replaced) |
| 4 | Replaced `face_gaze_calibration` with `face_gaze_model` (affine matrix) |

---

## Query groups (`storage/db/`)

| File | Responsibility |
|---|---|
| `connection.py` | Schema creation, migrations, numpy blob helpers |
| `faces.py` | CRUD for faces table |
| `stats.py` | Write and query stats rows |
| `config.py` | Seed, get, set config values |
| `demographics.py` | Upsert and read demographics |
| `calibration.py` | Read/write calibration values and gaze models |
| `audit.py` | Append to audit log |
