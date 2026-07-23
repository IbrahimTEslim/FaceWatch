from storage.config_store import ConfigStore


def compute_focus_score(
    gaze_off_sec:    float,
    interval_sec:    int,
    drowsy_pct:      float,
    angry_count:     int,
    surprised_count: int,
    distance_cm:     float,
    config:          ConfigStore,
) -> float:
    """
    Returns focus score 0–100 for a stats interval.

    Components:
        gaze_score    = 1.0 - (gaze_off_sec / interval_sec)
        drowsy_score  = 1.0 - drowsy_pct
        calm_score    = 1.0 - clamp((angry + surprised) / 5, 0, 1)
        posture_score = 1.0 if distance within [min_cm, max_cm], else scaled penalty
    """
    w_gaze     = config.get("focus_weight_gaze")
    w_drowsy   = config.get("focus_weight_drowsy")
    w_distract = config.get("focus_weight_distraction")
    w_posture  = config.get("focus_weight_posture")
    min_cm     = config.get("focus_posture_min_cm")
    max_cm     = config.get("focus_posture_max_cm")

    gaze_score = max(0.0, 1.0 - (gaze_off_sec / interval_sec)) if interval_sec > 0 else 1.0
    drowsy_score = max(0.0, 1.0 - drowsy_pct)
    calm_score = max(0.0, 1.0 - (angry_count + surprised_count) / 5.0)

    if distance_cm <= 0:
        posture_score = 0.5  # unknown distance — neutral penalty
    elif min_cm <= distance_cm <= max_cm:
        posture_score = 1.0
    else:
        deviation = min(abs(distance_cm - min_cm), abs(distance_cm - max_cm))
        posture_score = max(0.0, 1.0 - deviation / max_cm)

    score = (
        gaze_score    * w_gaze    +
        drowsy_score  * w_drowsy  +
        calm_score    * w_distract +
        posture_score * w_posture
    ) * 100.0

    return round(min(100.0, max(0.0, score)), 1)
