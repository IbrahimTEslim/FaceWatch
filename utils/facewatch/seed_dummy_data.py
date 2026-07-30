"""
Seed facewatch.db with dummy data for dashboard testing.
Run from project root:
    venv/Scripts/python.exe utils/facewatch/seed_dummy_data.py
"""
import sqlite3
import random
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "facewatch.db"
FACE_NAME = "test_user"
FACE_DISPLAY = "Test User"

APPS = [
    ("Code.exe",      "editor"),
    ("chrome.exe",    "browser"),
    ("slack.exe",     "communication"),
    ("WindowsTerminal.exe", "terminal"),
    ("msedge.exe",    "browser"),
    ("spotify.exe",   "media"),
    ("winword.exe",   "document"),
]

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys=ON")

# ── Face ──────────────────────────────────────────────────────────────────────
now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# Reuse existing test face if present, otherwise create
existing = conn.execute("SELECT id FROM faces WHERE name=?", (FACE_NAME,)).fetchone()
if not existing:
    conn.execute("""
        INSERT INTO faces (name, display_name, status, created_at, last_seen)
        VALUES (?, ?, 'known', ?, ?)
    """, (FACE_NAME, FACE_DISPLAY, now_str, now_str))
    conn.commit()

face_id = conn.execute("SELECT id FROM faces WHERE name=?", (FACE_NAME,)).fetchone()["id"]

# ── Demographics ──────────────────────────────────────────────────────────────
conn.execute("""
    INSERT OR REPLACE INTO demographics
        (face_id, age_estimate, gender, race, face_width_cm, confidence, last_updated)
    VALUES (?, 28, 'Male', 'Middle Eastern', 14.2, 0.91, ?)
""", (face_id, now_str))
conn.commit()

# ── Stats — 14 days, every 5 seconds from 09:00 to 18:00 ──────────────────────
random.seed(42)
today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

# Clear existing seeded stats for this face
conn.execute("DELETE FROM stats WHERE face_id=?", (face_id,))
conn.execute("DELETE FROM audit_log WHERE event_type LIKE 'alert_%'")
conn.commit()

for day_offset in range(14):
    day = today - timedelta(days=day_offset)
    # Simulate a 9-hour workday
    t = day.replace(hour=9)
    end = day.replace(hour=18)
    while t < end:
        hour = t.hour
        # Simulate lunch break (13:00-13:30) and short breaks
        if t.hour == 13 and t.minute < 30:
            t += timedelta(minutes=30)
            continue
        if t.hour in (11, 15) and t.minute == 0:
            t += timedelta(minutes=random.randint(5, 15))
            continue

        # Focus varies by hour — morning high, post-lunch dip, afternoon recovery
        if 9 <= hour < 12:
            base_focus = random.uniform(70, 92)
        elif 12 <= hour < 14:
            base_focus = random.uniform(40, 65)
        else:
            base_focus = random.uniform(60, 85)

        # Drowsiness spikes in post-lunch and late afternoon
        if 13 <= hour < 15:
            drowsy = round(random.uniform(10, 35), 1)
        elif hour >= 16:
            drowsy = round(random.uniform(5, 25), 1)
        else:
            drowsy = round(random.uniform(0, 10), 1)

        app, cat = random.choice(APPS)
        gaze_off = random.uniform(0, 8) if random.random() > 0.7 else 0.0
        dist = random.uniform(45, 85)
        prox = 1 if dist < 42 else 0

        conn.execute("""
            INSERT INTO stats (
                face_id, timestamp, interval_sec,
                blink_left, blink_right, smile_count, angry_count, surprised_count,
                neutral_pct, drowsy_pct, distance_cm, gaze_off_sec,
                proximity_alerts, focus_score, active_app, active_window_title, app_category
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            face_id,
            t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            5,
            random.randint(0, 2), random.randint(0, 2),
            random.randint(0, 1), random.randint(0, 1), random.randint(0, 1),
            round(random.uniform(60, 90), 1),
            round(drowsy, 1),
            round(dist, 1),
            round(gaze_off, 2),
            prox,
            round(base_focus, 1),
            app,
            f"{app} — window",
            cat,
        ))
        t += timedelta(seconds=5)

conn.commit()

# ── Audit log — some alert events ────────────────────────────────────────────
for day_offset in range(14):
    day = today - timedelta(days=day_offset)
    for _ in range(random.randint(2, 8)):
        event_t = day.replace(
            hour=random.randint(9, 17),
            minute=random.randint(0, 59),
            second=random.randint(0, 59),
        )
        event_type = random.choice(["alert_fired", "alert_cleared"])
        alert_kind = random.choice(["gaze", "proximity"])
        conn.execute("""
            INSERT INTO audit_log (timestamp, event_type, details)
            VALUES (?, ?, ?)
        """, (
            event_t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            event_type,
            json.dumps({"message": f"{alert_kind} alert {event_type.split('_')[1]}"}),
        ))

conn.commit()
conn.close()
print(f"Done. Seeded face_id={face_id} ({FACE_DISPLAY}) with 14 days of data.")
