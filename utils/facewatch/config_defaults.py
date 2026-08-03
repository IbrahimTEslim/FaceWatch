# Format: (key, default_value, type, description, category)
# Seeded into DB on first run via INSERT OR IGNORE — never read at runtime.

DEFAULTS = [
    ("camera_index",             0,                              "int",   "Webcam index. 0=first camera.", "camera"),
    ("face_landmarker_model_path", "models/face_landmarker.task", "str",   "Path to MediaPipe FaceLandmarker .task model file.", "models"),
    ("max_faces",                  10,                            "int",   "Maximum number of faces to detect simultaneously.", "models"),

    ("db_path",                  "facewatch.db","str",   "Path to SQLite database file.", "storage"),
    ("max_embeddings_per_face",  10,            "int",   "Max embeddings stored per face.", "storage"),
    ("stats_interval_sec",       5,             "int",   "Seconds between stats writes to DB.", "storage"),

    ("recognition_threshold",    0.60,          "float", "Cosine similarity threshold for known face match.", "recognition"),
    ("recognition_match_strategy", "best_single", "str",   "Embedding match strategy: best_single or average.", "recognition"),
    ("unknown_match_threshold",  0.70,          "float", "Similarity threshold to match unknown re-entry.", "recognition"),
    ("max_retry_attempts",       7,             "int",   "Max retries to identify unknown face.", "recognition"),
    ("retry_interval_sec",       3,             "int",   "Seconds between re-identification retries.", "recognition"),
    ("enrichment_interval_sec",  2,             "int",   "Seconds between extra embedding collection.", "recognition"),

    ("gaze_alert_sec",           10,            "int",   "Seconds off-screen before gaze alert fires.", "gaze"),
    ("gaze_return_sec",          3,             "int",   "Seconds on-screen continuously to clear gaze alert.", "gaze"),

    ("proximity_alert_cm",       40.0,          "float", "Distance in cm that triggers proximity alert.", "proximity"),
    ("proximity_alert_sec",      5,             "int",   "Seconds too close before alert fires.", "proximity"),
    ("proximity_clear_sec",      8,             "int",   "Seconds far enough to clear proximity alert.", "proximity"),
    ("eye_strain_alert_sec",     300,           "int",   "Seconds continuously too close before eye strain alert fires.", "proximity"),
    ("eye_strain_clear_sec",     30,            "int",   "Seconds at safe distance to clear eye strain alert.", "proximity"),

    ("fatigue_onset_window_sec", 120,           "int",   "Window in seconds to measure PERCLOS rise for fatigue onset.", "fatigue"),
    ("fatigue_onset_min_rise",   0.10,          "float", "Minimum PERCLOS rise within window to trigger fatigue onset.", "fatigue"),
    ("fatigue_onset_min_session",2700,          "int",   "Minimum session seconds before fatigue onset alert can fire.", "fatigue"),
    ("fatigue_onset_alert_sec",  10,            "int",   "Seconds condition must hold before fatigue onset alert fires.", "fatigue"),
    ("fatigue_onset_clear_sec",  60,            "int",   "Seconds condition must clear before fatigue onset alert clears.", "fatigue"),

    ("work_reminder_interval_sec", 5400,         "int",   "Seconds without a break before work reminder fires.", "wellness"),
    ("work_reminder_break_sec",    300,          "int",   "Minimum seconds away to count as a meaningful break.", "wellness"),
    ("work_reminder_alert_sec",    10,           "int",   "Seconds condition must hold before work reminder fires.", "wellness"),
    ("work_reminder_clear_sec",    30,           "int",   "Seconds after break detected to clear work reminder.", "wellness"),

    ("expr_threshold_blink",     0.50,          "float", "Blink activation threshold.", "expressions"),
    ("expr_threshold_smile",     0.50,          "float", "Smile activation threshold.", "expressions"),
    ("expr_threshold_angry",     0.45,          "float", "Angry activation threshold.", "expressions"),
    ("expr_threshold_surprised", 0.40,          "float", "Surprised activation threshold.", "expressions"),
    ("expr_threshold_neutral",   0.25,          "float", "Max any-expression value to count as neutral.", "expressions"),
    ("expr_threshold_drowsy",    0.15,          "float", "PERCLOS threshold for drowsiness.", "expressions"),
    ("drowsy_window_sec",        60,            "int",   "Rolling window size in seconds for PERCLOS.", "expressions"),

    ("demographics_refresh_days",7,             "int",   "Days between DeepFace demographics re-runs.", "demographics"),

    ("report_times",             "18:00,21:00", "list",  "Comma-separated HH:MM times to generate report.", "report"),
    ("report_port",              8765,          "int",   "Local HTTP port for report server.", "report"),

    ("focus_weight_gaze",        0.40,          "float", "Weight of gaze-on-screen in Focus Score.", "focus"),
    ("focus_weight_drowsy",      0.30,          "float", "Weight of non-drowsy in Focus Score.", "focus"),
    ("focus_weight_distraction", 0.20,          "float", "Weight of non-distracted in Focus Score.", "focus"),
    ("focus_weight_posture",     0.10,          "float", "Weight of good posture in Focus Score.", "focus"),
    ("focus_posture_min_cm",     45.0,          "float", "Minimum healthy camera distance in cm.", "focus"),
    ("focus_posture_max_cm",     90.0,          "float", "Maximum healthy camera distance in cm.", "focus"),

    ("box_color_known",       "0,220,0",   "str", "BGR box color for known faces.",       "ui"),
    ("box_color_identifying",  "220,220,0", "str", "BGR box color for identifying faces.",  "ui"),
    ("box_color_unknown",      "0,165,255", "str", "BGR box color for unknown faces.",      "ui"),
    ("notifications_enabled",  True,        "bool",  "Fire OS desktop notifications on alerts.",          "ui"),
    ("alert_overlay_enabled",   True,        "bool",  "Show fullscreen pulsing border on alert.",          "ui"),
    ("alert_border_width",      8,           "int",   "Alert border thickness in pixels.",                 "ui"),
    ("alert_cycle_sec",         3.0,         "float", "Alert pulse cycle length in seconds.",              "ui"),
    ("alert_max_alpha",         180,         "int",   "Alert border max opacity (0-255).",                 "ui"),
    ("alert_color_low",         "0,220,0",   "str",   "BGR border color for low priority alerts.",         "ui"),
    ("alert_color_medium",      "0,165,255", "str",   "BGR border color for medium priority alerts.",      "ui"),
    ("alert_color_high",        "0,0,220",   "str",   "BGR border color for high priority alerts.",        "ui"),

    ("key_quit",              "q", "str", "Key to quit FaceWatch.",                    "keys"),
    ("key_register",          "r", "str", "Key to register current face.",             "keys"),
    ("key_calibrate",         "c", "str", "Key to start calibration wizard.",          "keys"),
    ("key_debug",             "d", "str", "Key to toggle debug overlay.",              "keys"),
    ("key_force_stats",       "s", "str", "Key to force an immediate stats write.",    "keys"),
    ("key_force_reidentify",  "f", "str", "Key to force re-identify unknown faces.",   "keys"),
    ("key_settings",           ",", "str", "Key to open settings window.",              "keys"),
    ("key_report",             "o", "str", "Key to open report in browser.",            "keys"),
]
