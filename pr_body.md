## What
- **ui/alert_overlay.py** — fullscreen pulsing border overlay via PyQt6 in a separate process. Priority-based colors, all settings configurable. Process is a pure renderer — no decisions, just draws what it receives via pipe.
- **alerts/base.py** — `AlertPriority` enum (`LOW`, `MEDIUM`, `HIGH`), abstract `priority` property on `Alert`
- **alerts/gaze_alert.py** — `priority = AlertPriority.MEDIUM`
- **alerts/proximity_alert.py** — `priority = AlertPriority.HIGH`
- **alerts/manager.py** — `active_priorities()` returns `set[AlertPriority]` across all active tracks
- **config_defaults.py** — `alert_overlay_enabled`, `alert_border_width`, `alert_cycle_sec`, `alert_max_alpha`, `alert_color_low/medium/high`
- **core/recognizer.py** — `rename_track(track_id, face_id)` refetches from DB and updates cache instantly
- **ui/input_handler.py** — `TEST_OVERLAY` action for development testing
- **engine.py** — wires overlay start/stop/update, rename_track after db.rename_face
- **requirements.txt** — added `PyQt6`, `plyer`

## Design Decisions
- Overlay runs as a separate process (not thread) — PyQt6/Qt requires QApplication on main thread
- Engine communicates via `multiprocessing.Pipe` — sends `set[AlertPriority]` each frame
- Colors keyed by `AlertPriority` not `AlertType` — new alert types just need a priority, no new color config
- `DrawConfig` dataclass carries all visual settings — process has zero hardcoded values

## Tests
- 10/10 step-7 alert tests passed
