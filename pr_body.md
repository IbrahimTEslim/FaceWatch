## What
- **alerts/notifier.py** — OS desktop notification via plyer, guarded by `notifications_enabled` config
- **alerts/manager.py** — `AlertManager` owns per-track alert instances, fixes cross-face alert contamination bug
- **alerts/base.py** — `AlertStatus` enum (`FIRED`, `CLEARED`, `NONE`), `ALERT_LOGGABLE` uses enum members, `notify()` called on `FIRED`, module-level import
- **alerts/gaze_alert.py** — added `notification_title` property
- **alerts/proximity_alert.py** — added `notification_title` property
- **config_defaults.py** — added `notifications_enabled = True`
- **engine.py** — uses `AlertManager` instead of shared alerts list, `AlertStatus` enum for audit log

## Bug Fixed
Alerts were shared across all tracks — one list for all faces. If face 1 fired an alert but face 2 was on-screen, face 2's update immediately cleared it. Each track now has its own independent alert state via `AlertManager`.

## Tests
- 10/10 step-7 alert tests passed
