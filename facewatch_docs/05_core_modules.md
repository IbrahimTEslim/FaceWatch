# FaceWatch — Core Modules

## core/detector.py

### Responsibility
Wraps MediaPipe FaceLandmarker in LIVE_STREAM mode.
Exposes a simple `detect(frame, timestamp_ms)` method and a `get_result()` method.
All MediaPipe setup lives here — nothing else touches MediaPipe options.

### Key Decisions
- LIVE_STREAM mode: non-blocking, async callback, never stalls the main loop
- `output_face_blendshapes=True` — required for expression tracking
- `output_facial_transformation_matrixes=False` — not needed, saves compute
- Result stored under a threading.Lock — callback runs on MediaPipe's thread

### Interface
```python
class FaceDetector:
    def __init__(self, num_faces: int, model_path: str): ...
    def detect(self, frame_rgb: np.ndarray, timestamp_ms: int) -> None:
        """Send frame to MediaPipe. Non-blocking."""
    def get_result(self) -> FaceLandmarkerResult | None:
        """Get latest result. Returns None if no result yet."""
    def close(self) -> None: ...
```

### MediaPipe Notes (from progress.md — do not re-discover)
- MediaPipe v0.10.35 — NO `mp.solutions` — only `mp.tasks.vision`
- Import: `from mediapipe.tasks.vision` (NOT `mp.tasks.python.vision`)
- Model file: `face_landmarker.task` (bundled model, includes blendshapes + iris)
- GPU delegate does NOT work on Windows — CPU only
- LIVE_STREAM requires monotonically increasing timestamps — never reuse or decrement

---

## core/tracker.py

### Responsibility
Wraps the SORT tracker. Converts MediaPipe face landmarks into bounding boxes,
feeds them to SORT, returns stable track_ids per face across frames.
Also manages track lifecycle — knows when a track_id is new vs seen before.

### Key Decisions
- SORT needs `[x1, y1, x2, y2, confidence]` arrays — tracker.py does this conversion
- `min_hits=3` — need 3 detections to confirm a new track (avoids false tracks)
- `max_age=30` — keep track alive 30 frames (~1 sec) without detection
- `iou_threshold=0.3` — IoU overlap for matching detections to existing tracks

### Interface
```python
class FaceTracker:
    def __init__(self): ...
    def update(self, landmarks_list: list, frame_w: int, frame_h: int) -> list[Track]:
        """
        landmarks_list: list of face_landmarks from MediaPipe result
        Returns: list of Track(id, bbox, is_new)
        """
    def get_bbox(self, landmarks, frame_w: int, frame_h: int,
                 padding: float = 0.2) -> tuple[int,int,int,int]:
        """Convert 478 landmarks to padded pixel bounding box."""

@dataclass
class Track:
    id:     int
    bbox:   tuple[int,int,int,int]   # x1,y1,x2,y2
    is_new: bool                      # True on first appearance
```

---

## core/recognizer.py

### Responsibility
- Compute DeepFace embeddings from face crops
- Search face DB (embeddings in SQLite) for matches
- Manage known/unknown status
- Handle retry logic for unknowns
- Handle click-to-register flow

### Key Decisions
- Embeddings stored in SQLite as numpy BLOBs (np.save, not pickle)
- Centroid comparison: average all stored embeddings per face → compare against single centroid
- Diverse embedding selection: greedy max-distance algorithm keeps most varied embeddings
- Search order for new track: (1) known faces → (2) unknown faces → (3) create new unknown
- Retry: unknowns re-identified every `retry_interval_sec`, up to `max_retry_attempts`
- All DB ops delegated to `database.py` — recognizer never writes SQL directly

### Interface
```python
class Recognizer:
    def __init__(self, db: Database, config: ConfigStore): ...

    def on_new_track(self, track_id: int, face_crop: np.ndarray) -> None:
        """Called when SORT reports a new track_id. Runs in background thread."""

    def on_track_update(self, track_id: int, face_crop: np.ndarray, now: float) -> None:
        """Called every frame for existing tracks. Handles retry timing."""

    def register(self, track_id: int, name: str) -> bool:
        """Register an unknown face with a name. Returns False if name exists."""

    def get_identity(self, track_id: int) -> Identity:
        """Get current identity for a track_id."""

    def rename(self, face_id: int, new_name: str) -> bool:
        """Rename a known face. Updates faces.name only — all FKs use id."""

@dataclass
class Identity:
    face_id:      int | None    # None = still identifying
    name:         str           # 'Ibrahim' or 'unknown_3' or 'Identifying...'
    status:       str           # 'known' | 'unknown' | 'identifying'
    retries_left: int
    confidence:   float
```

### Embedding Math
```python
# L2 normalization (applied to every embedding before storage)
norm = np.linalg.norm(emb)
emb = emb / norm if norm > 0 else emb

# Cosine similarity (range -1 to 1, higher = more similar)
similarity = np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b))

# Centroid comparison
centroid = np.mean(all_embeddings_for_face, axis=0)
score = cosine_similarity(new_embedding, centroid)

# Diverse selection (greedy)
# Start with first embedding, then always pick the one
# most different from all already selected
```

### DeepFace Call
```python
result = DeepFace.represent(
    img_path=face_crop,         # numpy BGR array
    model_name="Facenet",       # 128D embedding space
    detector_backend="skip",    # MediaPipe already detected the face
    enforce_detection=False,    # don't crash if face not found
)
embedding = np.array(result[0]["embedding"])
```
