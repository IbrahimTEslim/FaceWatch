# FaceWatch — UI & Engine

## ui/renderer.py

### Responsibility
ALL cv2 drawing lives here. Zero cv2 calls anywhere else in the codebase (R6).
Receives a `FrameState` data object and draws everything onto the frame.

### FrameState — What Gets Drawn
```python
@dataclass
class FrameState:
    frame:          np.ndarray
    tracks:         list[Track]
    identities:     dict[int, Identity]         # track_id → Identity
    expressions:    dict[int, dict]             # track_id → {expr_name: ExpressionState}
    gaze_states:    dict[int, GazeState]        # track_id → GazeState
    distances:      dict[int, float]            # track_id → cm
    alerts:         list[AlertEvent]            # currently active alerts
    focus_scores:   dict[int, float]            # track_id → 0–100
    active_app:     str
    active_title:   str
    debug_mode:     bool
```

### What Gets Drawn Per Face
```
┌─────────────────────────────────────────────────────┐
│  [Name / unknown_3 / Identifying...]                │  ← above bbox
│  Focus: 73  |  58cm  |  →center                    │  ← below name
│                                                     │
│         [face bounding box]                         │
│                                                     │
│  😊 Smile  😠 Angry  😲 Surprised  😴 Drowsy       │  ← expression icons
└─────────────────────────────────────────────────────┘
```

### Bounding Box Colors
```
Identifying...  → yellow  (0, 255, 255)
Known face      → green   (0, 255, 0)
Unknown face    → orange  (0, 165, 255)
Alert active    → red     (0, 0, 255)   (overrides other colors)
```

### Global Overlays
```
Top-left:     "FaceWatch  |  PRIVATE — Local Only"
Top-right:    active app name + category icon
Bottom-left:  active alerts (stacked, color-coded)
Bottom-right: gaze direction indicator (crosshair box)
              Focus score (large, color-coded)
```

### Debug Mode (toggled with 'd' key)
When debug_mode=True, additionally draws:
- All 478 face landmarks as dots
- Iris landmark highlights
- Landmark 234 and 454 (cheekbone distance points)
- Raw blendshape values for active expressions
- SORT track bounding boxes (raw, before identity lookup)

---

## ui/input_handler.py

### Responsibility
Handle all keyboard and mouse input. Returns `InputEvent` objects to engine.py.

### Keyboard Controls
```
'q'         → quit
'd'         → toggle debug overlay
'r'         → reset all expression counters
'c'         → open config in browser (localhost:PORT/config)
'h'         → show/hide help overlay
SPACE       → confirm (used during calibration wizard)
's'         → skip (used during calibration wizard)
ESC         → cancel current action (typing mode, calibration)
```

### Mouse Controls
```
Left-click on unknown face bbox → enter typing mode (register face)
```

### Typing Mode
When user clicks an unknown face:
```
- Bottom overlay appears: "Name: [cursor]_"
- Keyboard input captured for name entry
- ENTER → confirm registration
- ESC   → cancel
- BACKSPACE → delete last char
- Printable ASCII → append to name
- Duplicate name check before confirming
```

### Interface
```python
class InputHandler:
    def process(self, key: int, mouse_event: MouseEvent | None,
                current_boxes: list) -> InputEvent: ...

@dataclass
class InputEvent:
    action:     str     # 'quit'|'toggle_debug'|'reset'|'register'|'none'|...
    data:       dict    # action-specific data e.g. {'track_id': 3, 'name': 'Ibrahim'}
```

---

## engine.py

### Responsibility
Main loop. Wires all modules together. Handles CLI args. Runs calibration wizard if needed.

### CLI Args
```python
parser.add_argument("--camera",    type=int, default=None)
parser.add_argument("--calibrate", action="store_true")
parser.add_argument("--refresh-demographics", type=str, metavar="NAME")
parser.add_argument("--reset-config", action="store_true")
parser.add_argument("--port",      type=int, default=None)
```

### Startup Sequence
```
1. Parse CLI args
2. Init database (create tables, run migrations)
3. Seed config from config_defaults.py (INSERT OR IGNORE)
4. Init ConfigStore
5. Apply CLI overrides to config (session-only, no DB write)
6. Init all modules (detector, tracker, recognizer, expressions, gaze, distance, alerts, demographics)
7. Start reporter thread (background)
8. Start HTTP server thread (background)
9. Check if calibration needed → run wizard if yes
10. Open camera
11. Enter main loop
12. On exit: cleanup, log session_end to audit_log
```

### Main Loop (simplified)
```python
while cap.isOpened():
    ret, frame = cap.read()
    frame = cv2.flip(frame, 1)
    now = time.time()
    dt = now - last_time
    last_time = now

    # 1. Detect
    detector.detect(rgb(frame), timestamp_ms)
    result = detector.get_result()

    # 2. Track
    tracks = tracker.update(result.face_landmarks, frame_w, frame_h)

    # 3. Per-track analysis
    for track in tracks:
        recognizer.on_track_update(track.id, crop(frame, track.bbox), now)
        identity = recognizer.get_identity(track.id)

        if track.is_new:
            demographics.maybe_run(identity.face_id, crop(frame, track.bbox))

        for expr in expressions:
            expr.update(blendshapes[track.id], landmarks[track.id], config)

        gaze_states[track.id] = gaze.update(landmarks[track.id], dt, config)
        distances[track.id]   = distance.estimate(landmarks[track.id], ...)

    # 4. Alerts
    for alert in alerts:
        event = alert.update(condition(alert), dt, config)
        if event.status == "fired":
            db.log_audit("alert_fired", event.message)

    # 5. Stats write (interval)
    if now - last_stats_write >= config.get("stats_interval_sec"):
        for track in tracks:
            identity = recognizer.get_identity(track.id)
            if identity.status == "known":
                app, title = app_tracker.get_active_app()
                stats_row = build_stats_row(track.id, expressions, gaze_states,
                                            distances, alerts, app, title, now)
                db.write_stats(identity.face_id, stats_row)
        last_stats_write = now

    # 6. Draw
    frame_state = FrameState(frame, tracks, identities, ...)
    renderer.draw(frame_state)

    # 7. Input
    key = cv2.waitKey(1) & 0xFF
    event = input_handler.process(key, mouse_event, current_boxes)
    handle_event(event)

    cv2.imshow(WINDOW_NAME, frame)
    timestamp_ms += 33
```

---

## Module Init Order (dependency-safe)

```python
# engine.py startup — in this exact order

db      = Database(config_store.get("db_path"))
config  = ConfigStore(db)
# seed defaults
for row in DEFAULTS:
    db.seed_config(*row)

detector    = FaceDetector(...)
tracker     = FaceTracker()
recognizer  = Recognizer(db, config)
expressions = EXPRESSIONS          # from registry.py
gaze        = GazeTracker()
distance    = DistanceEstimator()
alerts      = ALERTS               # from registry.py
demographics = DemographicsAnalyzer(db, config)
app_tracker  = AppTracker()
renderer     = Renderer()
input_handler = InputHandler()

reporter = Reporter(db, config)
reporter.daemon = True
reporter.start()

server = ReportServer(db, config)
server.daemon = True
server.start()
```
