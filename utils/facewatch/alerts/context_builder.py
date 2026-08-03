from .base import AlertContext
from storage.config_store import ConfigStore


def build_alert_context(
    expressions:    list,
    session_start:  float,
    last_absent:    float | None,
    gaze_on_screen: bool,
    dist_cm:        float,
    config:         ConfigStore,
    now:            float,
) -> AlertContext:
    drowsy_expr   = next((e for e in expressions if e.name == "drowsy"),     None)
    blink_l_expr  = next((e for e in expressions if e.name == "blink_left"), None)

    perclos        = drowsy_expr.value if drowsy_expr else 0.0
    session_sec    = now - session_start
    elapsed_min    = max(session_sec / 60.0, 0.01)
    blink_rate_pm  = (blink_l_expr.count / elapsed_min) if blink_l_expr else 0.0
    last_break_sec = (now - last_absent) if last_absent is not None else session_sec

    return AlertContext(
        gaze_on_screen=gaze_on_screen,
        dist_cm=dist_cm,
        config=config,
        perclos=perclos,
        blink_rate_pm=blink_rate_pm,
        session_sec=session_sec,
        last_break_sec=last_break_sec,
    )
