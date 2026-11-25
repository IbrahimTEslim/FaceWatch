# Configuration Reference

All config is stored in the SQLite `config` table and seeded from `config_defaults.py` on first launch via `INSERT OR IGNORE`. Changes made in the settings window take effect when the window closes. A few values are read once at startup and need a restart: camera index, face landmarker model, max faces, face box colors, key bindings, and the alert overlay style.

Edit config via the settings window (`,` key) or directly in the DB.

---

## Camera

| Key | Default | Description |
|---|---|---|
| `camera_index` | `0` | Webcam index. `0` = first camera. Override with `--camera` CLI arg. |
| `face_landmarker_model_path` | `models/face_landmarker.task` | Path to MediaPipe model file. |
| `max_faces` | `10` | Maximum simultaneous faces to detect. |

## Storage

| Key | Default | Description |
|---|---|---|
| `max_embeddings_per_face` | `10` | Max embedding vectors per face. More = better accuracy, more memory. |
| `stats_interval_sec` | `5` | Seconds between stats writes. Lower = more granular data, more I/O. |

The database file itself is chosen with `python main.py --db PATH` (default `facewatch.db`; relative paths resolve against the FaceWatch folder). The old `db_path` config key could never take effect — it was stored inside the database it named — and is removed by DB migration 6.

## Recognition

| Key | Default | Description |
|---|---|---|
| `recognition_threshold` | `0.60` | Cosine similarity threshold to accept a known face match. |
| `recognition_match_strategy` | `best_single` | `best_single` or `average` — how stored embeddings are compared. |
| `unknown_match_threshold` | `0.70` | Similarity threshold to match an unknown re-entry to an existing unknown record. |
| `max_retry_attempts` | `7` | Max retries to identify an unknown face before giving up. |
| `retry_interval_sec` | `3` | Seconds between re-identification retries. |
| `enrichment_interval_sec` | `2` | Seconds between collecting extra embeddings for known faces. |

## Gaze

| Key | Default | Description |
|---|---|---|
| `gaze_alert_sec` | `10` | Seconds off-screen before gaze alert fires. |
| `gaze_return_sec` | `3` | Seconds on-screen continuously to clear gaze alert. |
| `gaze_edge_margin_x_px` | `100` | Pixel margin outside screen left/right still counted as on-screen. |
| `gaze_edge_margin_y_px` | `200` | Pixel margin outside screen top/bottom still counted as on-screen. |

Screen size is not configurable: it is detected at startup from the primary screen's logical (DPI-scaled) geometry, reported by the calibration overlay process with a tkinter fallback. See `ui/screen.py`. The `screen_w_px` / `screen_h_px` keys from earlier versions are removed by DB migration 5.

## Proximity

| Key | Default | Description |
|---|---|---|
| `proximity_alert_cm` | `40.0` | Distance threshold in cm. Closer triggers proximity alert. |
| `proximity_alert_sec` | `5` | Seconds too close before alert fires. |
| `proximity_clear_sec` | `8` | Seconds at safe distance to clear proximity alert. |
| `eye_strain_alert_sec` | `300` | Seconds continuously too close before eye strain alert fires. |
| `eye_strain_clear_sec` | `30` | Seconds at safe distance to clear eye strain alert. |

## Fatigue

| Key | Default | Description |
|---|---|---|
| `fatigue_onset_window_sec` | `120` | Window in seconds to measure PERCLOS rise. |
| `fatigue_onset_min_rise` | `0.10` | Minimum PERCLOS rise within window to trigger fatigue onset. |
| `fatigue_onset_min_session` | `2700` | Minimum session seconds (45 min) before fatigue alert can fire. |
| `fatigue_onset_alert_sec` | `10` | Seconds condition must hold before alert fires. |
| `fatigue_onset_clear_sec` | `60` | Seconds condition must clear before alert clears. |

## Wellness

| Key | Default | Description |
|---|---|---|
| `work_reminder_interval_sec` | `5400` | Seconds without a break before work reminder fires (90 min). |
| `work_reminder_break_sec` | `300` | Minimum seconds away to count as a meaningful break (5 min). |
| `work_reminder_alert_sec` | `10` | Seconds condition must hold before alert fires. |
| `work_reminder_clear_sec` | `30` | Seconds after break detected to clear work reminder. |

## Expressions

| Key | Default | Description |
|---|---|---|
| `expr_threshold_blink` | `0.50` | Blink activation threshold. |
| `expr_threshold_smile` | `0.50` | Smile activation threshold. |
| `expr_threshold_angry` | `0.45` | Angry activation threshold. |
| `expr_threshold_surprised` | `0.40` | Surprised activation threshold. |
| `expr_threshold_neutral` | `0.25` | Max any-expression value to count a frame as neutral. |
| `expr_threshold_drowsy` | `0.15` | PERCLOS threshold for drowsiness. |
| `drowsy_window_sec` | `60` | Rolling window size in seconds for PERCLOS calculation. |

## Demographics

| Key | Default | Description |
|---|---|---|
| `demographics_refresh_days` | `7` | Days between DeepFace demographics re-runs per face. |

## Report

| Key | Default | Description |
|---|---|---|
| `report_times` | `18:00,21:00` | Comma-separated HH:MM times to generate and serve the daily report. |
| `report_port` | `8765` | Local HTTP port for the report server. |

## Focus Score

| Key | Default | Description |
|---|---|---|
| `focus_weight_gaze` | `0.40` | Weight of gaze-on-screen in Focus Score. |
| `focus_weight_drowsy` | `0.30` | Weight of non-drowsy in Focus Score. |
| `focus_weight_distraction` | `0.20` | Weight of non-distracted in Focus Score. |
| `focus_weight_posture` | `0.10` | Weight of good posture in Focus Score. |
| `focus_posture_min_cm` | `45.0` | Minimum healthy camera distance in cm. |
| `focus_posture_max_cm` | `90.0` | Maximum healthy camera distance in cm. |

## UI

| Key | Default | Description |
|---|---|---|
| `box_color_known` | `0,220,0` | BGR box color for known faces. |
| `box_color_identifying` | `220,220,0` | BGR box color for identifying faces. |
| `box_color_unknown` | `0,165,255` | BGR box color for unknown faces. |
| `notifications_enabled` | `true` | Fire OS desktop notifications on alerts. |
| `alert_overlay_enabled` | `true` | Show fullscreen pulsing border on alert. |

## Key bindings

| Key | Default | Action |
|---|---|---|
| `key_quit` | `q` | Quit FaceWatch |
| `key_register` | `r` | Register face under cursor |
| `key_calibrate` | `c` | Start calibration wizard |
| `key_debug` | `d` | Toggle debug panel |
| `key_force_stats` | `s` | Force immediate stats write |
| `key_force_reidentify` | `f` | Force re-identify unknown faces |
| `key_settings` | `,` | Open settings window |
| `key_report` | `o` | Open report in browser |
| `key_help` | `h` | Toggle help overlay |
