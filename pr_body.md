## What
- `engine.py` — main loop skeleton: module init, per-track analysis, stats writing at interval
- `analysis/focus.py` — compute_focus_score() pure function
- `core/recognizer.py` — Identity dataclass + per-track recognition state (submit, get_identity, drop_track)
- `alerts/base.py` — AlertType enum, AlertContext dataclass, ALERT_LOGGABLE constant
- `alerts/gaze_alert.py` + `alerts/proximity_alert.py` — updated with alert_type + is_condition_met(ctx)
- `demographics/face_width.py` — DEFAULT_FACE_WIDTH_CM as single source of truth
- `demographics/analyzer.py` — imports DEFAULT_FACE_WIDTH_CM from face_width

## Design decisions
- Per-track expressions and gaze: `dict[int, list[Expression]]` and `dict[int, GazeTracker]` — each face has isolated state
- AlertContext dataclass passed to all alerts — type-safe, extensible, engine stays decoupled from alert internals
- AlertType enum — no magic strings for alert type comparisons
- ALERT_LOGGABLE frozenset — single place to define which events get audit-logged
- DEFAULT_FACE_WIDTH_CM in face_width.py — used by estimate_face_width_cm, analyzer.py, and engine.py
- _DEFAULT_FOCAL_LENGTH_PX = 600.0 in engine.py with TODO for step 11 calibration wiring

## Tests
8/8 smoke tests passed
