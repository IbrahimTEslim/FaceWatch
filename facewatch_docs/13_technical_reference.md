# FaceWatch — Technical Reference & Known Gotchas

## MediaPipe Technical Notes

These are hard-won discoveries — do not re-discover them.

### Version & Import
```python
# mediapipe 0.10.35
# NO mp.solutions — that's the old API
# Correct import:
from mediapipe.tasks.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode
from mediapipe.tasks import BaseOptions

# NOT:
# import mediapipe.tasks.python.vision  ← wrong
# mp.solutions.face_mesh                ← old API, not available
```

### Model Files
```
face_landmarker.task    — face landmarks + blendshapes + iris (bundled)
hand_landmarker.task    — hand landmarks (not used in FaceWatch)
```
Model files go in `models/` directory. Download from MediaPipe model card.

### LIVE_STREAM Mode Rules
```python
# 1. Timestamps must be monotonically increasing — never reuse or decrement
timestamp_ms += 33   # ~30fps increment

# 2. Callback runs on MediaPipe's thread — protect shared state with Lock
result_lock = threading.Lock()

def on_result(result, output_image, timestamp_ms):
    with result_lock:
        latest_result = result

# 3. detect_async() is non-blocking — result arrives later via callback
# 4. Never call detect_async() faster than the model can process
#    (33ms per frame is safe for face_landmarker on CPU)
```

### GPU on Windows
```
GPU delegate does NOT work on Windows.
OpenGL ES (MediaPipe) vs CUDA (Windows GPU) mismatch.
CPU is fine for learning and production use at 30fps.
Do not attempt to enable GPU on Windows — it will crash silently.
```

### Frame Flip & Handedness
```python
# Always flip frame before detection for mirror effect
frame = cv2.flip(frame, 1)
# Note: flipping BEFORE detection causes hand handedness labels to invert
# Fix: swap Left/Right labels after detection
# For face detection: flip has no effect on landmark positions (symmetric)
```

### Face Landmark Count
```
478 landmarks total:
    0–467:  face mesh
    468–472: left iris (468 = center)
    473–477: right iris (473 = center)
```

### Blendshapes
```
52 blendshapes total
output_face_blendshapes=True must be set in options
Access: result.face_blendshapes[face_index][blendshape_index].score
Parse to dict: {bs.category_name: bs.score for bs in result.face_blendshapes[0]}
```

### Key Landmark Indices
```python
# Cheekbones (distance estimation)
LEFT_CHEEKBONE  = 234
RIGHT_CHEEKBONE = 454

# Iris (gaze tracking)
LEFT_IRIS_CENTER  = 468
RIGHT_IRIS_CENTER = 473

# Eye corners (gaze tracking)
LEFT_EYE_OUTER  = 33
LEFT_EYE_INNER  = 133
RIGHT_EYE_OUTER = 362
RIGHT_EYE_INNER = 263

# Eye top/bottom (vertical gaze)
LEFT_EYE_TOP    = 159
LEFT_EYE_BOTTOM = 145
RIGHT_EYE_TOP   = 386
RIGHT_EYE_BOTTOM = 374
```

### Face Connections (for drawing)
```python
# Available sets — FaceLandmarksConnections has NO combined "IRISES"
# Must use LEFT_IRIS and RIGHT_IRIS separately
mp.tasks.vision.FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION
mp.tasks.vision.FaceLandmarksConnections.FACE_LANDMARKS_CONTOURS
mp.tasks.vision.FaceLandmarksConnections.FACE_LANDMARKS_FACE_OVAL
mp.tasks.vision.FaceLandmarksConnections.FACE_LANDMARKS_LEFT_EYE
mp.tasks.vision.FaceLandmarksConnections.FACE_LANDMARKS_RIGHT_EYE
mp.tasks.vision.FaceLandmarksConnections.FACE_LANDMARKS_LEFT_IRIS
mp.tasks.vision.FaceLandmarksConnections.FACE_LANDMARKS_RIGHT_IRIS
mp.tasks.vision.FaceLandmarksConnections.FACE_LANDMARKS_LEFT_EYEBROW
mp.tasks.vision.FaceLandmarksConnections.FACE_LANDMARKS_RIGHT_EYEBROW
mp.tasks.vision.FaceLandmarksConnections.FACE_LANDMARKS_LIPS
mp.tasks.vision.FaceLandmarksConnections.FACE_LANDMARKS_NOSE
```

---

## DeepFace Technical Notes

### Embedding
```python
result = DeepFace.represent(
    img_path=face_crop,         # numpy BGR array (cv2 format)
    model_name="Facenet",       # 128D embedding
    detector_backend="skip",    # CRITICAL: MediaPipe already detected face
    enforce_detection=False,    # don't crash if face not perfectly detected
)
embedding = np.array(result[0]["embedding"])
# Always L2-normalize before storing:
norm = np.linalg.norm(embedding)
embedding = embedding / norm if norm > 0 else embedding
```

### Demographics
```python
result = DeepFace.analyze(
    img_path=face_crop,
    actions=["age", "gender", "race"],
    detector_backend="skip",
    enforce_detection=False,
    silent=True,                # suppress DeepFace console output
)
age    = result[0]["age"]               # int
gender = result[0]["dominant_gender"]   # "Man" or "Woman"
race   = result[0]["dominant_race"]     # "asian", "white", "middle eastern", etc.
conf   = result[0]["gender"][gender]    # confidence 0–100
```

### Performance
- DeepFace.represent() takes ~200–500ms on CPU — MUST run in background thread
- DeepFace.analyze() takes ~300–800ms on CPU — MUST run in background thread
- Never call either in the main loop — will drop to 1–2 FPS

### Face Crop Quality
```python
# Good crop = tight around face, no padding
# Bad crop = too much background, too small, blurry
# Minimum crop size: 48×48 pixels (Facenet requirement)
# Recommended: 160×160 pixels

face_crop = frame[y1:y2, x1:x2]
if face_crop.size == 0:
    return None   # skip — empty crop
if face_crop.shape[0] < 48 or face_crop.shape[1] < 48:
    return None   # skip — too small
```

---

## SORT Tracker Notes

### Import
```python
from sort_tracker import Sort   # pip install sort-tracker
# OR clone https://github.com/abewley/sort and import directly
```

### Usage
```python
tracker = Sort(
    max_age=30,         # frames to keep track alive without detection
    min_hits=3,         # detections needed to confirm new track
    iou_threshold=0.3,  # IoU overlap for matching
)

# Input: numpy array shape (N, 5) — [x1, y1, x2, y2, confidence]
# Output: numpy array shape (M, 6) — [x1, y1, x2, y2, confidence, track_id]
det_array = np.array([[x1, y1, x2, y2, 0.9], ...])
tracked = tracker.update(det_array)

# When no detections:
tracked = tracker.update(np.empty((0, 5)))
```

### Track ID Lifecycle
```
New face appears → min_hits=3 frames later → track_id assigned
Face disappears  → max_age=30 frames later → track_id retired
Same face returns → NEW track_id assigned (SORT has no re-ID)
    → recognizer.py handles re-identification via embeddings
```

---

## SQLite Notes

### Connection
```python
import sqlite3

# Use check_same_thread=False for multi-threaded access
# Use WAL mode for better concurrent read/write performance
conn = sqlite3.connect(db_path, check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys=ON")
```

### Thread Safety
```python
# SQLite in WAL mode: multiple readers, one writer at a time
# Use a threading.Lock() for all writes
# Reads can happen without lock in WAL mode
write_lock = threading.Lock()

def write(sql, params):
    with write_lock:
        conn.execute(sql, params)
        conn.commit()
```

### Numpy BLOB Storage
```python
import io
import numpy as np

def array_to_blob(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    np.save(buf, arr)
    return buf.getvalue()

def blob_to_array(blob: bytes) -> np.ndarray:
    buf = io.BytesIO(blob)
    return np.load(buf)
```

---

## Camera Notes

### Backend
```python
# Windows USB cameras: use CAP_DSHOW for better compatibility
cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)

# macOS / Linux / virtual cameras: plain index
cap = cv2.VideoCapture(index)

# Cross-platform approach: try CAP_DSHOW first, fall back
cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
if not cap.isOpened():
    cap = cv2.VideoCapture(index)
```

### Camera Index Discovery
```python
# List available cameras (engine.py --list-cameras)
def list_cameras(max_index=5):
    available = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            available.append(i)
            cap.release()
    return available
```

---

## Distance Formula Reference

```
Distance_cm = (face_width_cm × focal_length_px) / pixel_width_px

Rearranged for calibration:
focal_length_px = (pixel_width_px × known_distance_cm) / face_width_cm

Where pixel_width_px = distance between landmarks 234 and 454 in pixels:
    lm234 = landmarks[234]
    lm454 = landmarks[454]
    pixel_width_px = abs(lm454.x - lm234.x) * frame_width
```

---

## Suppress Noisy Logs

```python
# At top of engine.py — before any imports
import os
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"]  = "3"
os.environ["GRPC_VERBOSITY"]        = "ERROR"
os.environ["GLOG_minloglevel"]      = "3"
```

---

## Common Pitfalls

| Pitfall | Fix |
|---|---|
| DeepFace called in main loop | Always use threading.Thread(daemon=True) |
| Timestamp not incrementing | `timestamp_ms += 33` every frame, never reset |
| Face crop is empty | Check `face_crop.size > 0` before passing to DeepFace |
| SORT returns float track_ids | Always cast: `track_id = int(track[5])` |
| Normalized landmarks used for pixel distance | Multiply by frame_w/frame_h first |
| Config read from config_defaults.py at runtime | Always use ConfigStore.get() |
| Raw SQL outside database.py | All SQL in database.py only (R5) |
| cv2 call outside renderer.py | All drawing in renderer.py only (R6) |
| Pickle for numpy arrays | Use np.save/np.load with BytesIO (pickle breaks across versions) |
| face_width_cm hardcoded | Read from demographics table per face_id |
