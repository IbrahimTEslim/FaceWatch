# Format: (key, default_value, type, description, category)
# Seeded into DB on first run via INSERT OR IGNORE — never read at runtime.

DEFAULTS = [
    ("camera_index",             0,                              "int",   "Webcam index. 0=first camera.", "camera"),
    ("face_landmarker_model_path", "models/face_landmarker.task", "str",   "Path to MediaPipe FaceLandmarker .task model file.", "models"),

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

    ("key_quit",         "q", "str", "Key to quit FaceWatch.",              "keys"),
    ("key_register",     "r", "str", "Key to register current face.",       "keys"),
    ("key_calibrate",    "c", "str", "Key to start calibration wizard.",    "keys"),
    ("key_debug",        "d", "str", "Key to toggle debug overlay.",        "keys"),
    ("key_force_stats",  "s", "str", "Key to force an immediate stats write.", "keys"),
]
