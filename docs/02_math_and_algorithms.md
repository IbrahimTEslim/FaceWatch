# Math & Algorithms

This document explains the mathematical foundations behind every measurement FaceWatch makes.

---

## Face detection — MediaPipe FaceLandmarker

FaceWatch uses MediaPipe's FaceLandmarker in **VIDEO mode** (synchronous, one result per frame). It outputs:

- **478 3D landmarks** — normalized `(x, y, z)` coordinates in `[0, 1]` relative to frame size
- **52 blendshape scores** — each a float in `[0, 1]` representing facial muscle activation

Key landmark indices used throughout the codebase:

| Index | Location |
|---|---|
| 234 | Left cheekbone |
| 454 | Right cheekbone |
| 33 | Left eye outer corner |
| 133 | Left eye inner corner |
| 263 | Right eye outer corner |
| 362 | Right eye inner corner |
| 159 | Left eye top |
| 145 | Left eye bottom |
| 386 | Right eye top |
| 374 | Right eye bottom |
| 468 | Left iris center |
| 473 | Right iris center |

---

## Multi-face tracking — SORT

SORT (Simple Online and Realtime Tracking) assigns stable integer IDs to faces across frames using:

1. **Kalman filter** — predicts where each tracked face will be next frame
2. **Hungarian algorithm** — matches predictions to new detections by IoU overlap
3. **Track lifecycle** — `min_hits=3` (3 detections to confirm), `max_age=30` (30 frames without detection before dropping)

FaceWatch feeds SORT bounding boxes derived from MediaPipe landmarks:

```
x1 = min(landmark.x * frame_w)
y1 = min(landmark.y * frame_h)
x2 = max(landmark.x * frame_w)
y2 = max(landmark.y * frame_h)
confidence = 1.0
```

SORT returns `[x1, y1, x2, y2, track_id]`. The `track_id` is a float — always cast to `int`.

---

## Face recognition — DeepFace Facenet512

### Embedding

Each face crop is passed to DeepFace with `detector_backend="skip"` (MediaPipe already detected it):

```python
result = DeepFace.represent(crop_bgr, model_name="Facenet512", detector_backend="skip")
embedding = np.array(result[0]["embedding"], dtype=np.float32)
embedding = embedding / np.linalg.norm(embedding)  # L2 normalize
```

Facenet512 produces a **512-dimensional unit vector**. After L2 normalization, cosine similarity equals the dot product:

```
similarity = dot(vec_a, vec_b)   # range [-1, 1], higher = more similar
```

### Matching

Two strategies (configurable via `recognition_match_strategy`):

**best_single** — compare new embedding against every stored embedding, take the max:
```
sim = max(dot(new_vec, stored_vec) for stored_vec in face_embeddings)
```

**average** — compare against the mean of all stored embeddings:
```
centroid = mean(all_embeddings)
centroid = centroid / norm(centroid)
sim = dot(new_vec, centroid)
```

A match is accepted if `sim >= recognition_threshold` (default `0.60`).

### Embedding diversity — greedy eviction

Each face stores up to `max_embeddings_per_face` (default 10) embeddings. When the cap is reached and a new embedding arrives, the algorithm keeps the most diverse set:

1. Compute the mean of all stored embeddings (the centroid)
2. Find the stored embedding **farthest** from the centroid (highest cosine distance)
3. If the new embedding is **closer** to the centroid than the farthest one, replace it
4. Otherwise, drop the new embedding (it's an outlier)

This ensures the stored set represents the full range of the face's appearance.

---

## Distance estimation

Uses the **known-size formula** (pinhole camera model):

```
distance_cm = (face_width_cm × focal_length_px) / pixel_width_px
```

Where:
- `pixel_width_px` = pixel distance between landmarks 234 (left cheekbone) and 454 (right cheekbone)
- `face_width_cm` = personalized estimate from demographics (see below)
- `focal_length_px` = calibrated value stored in DB (see Calibration)

Cheekbones are used instead of bounding box width because they are the most stable horizontal pair — less affected by expression changes or head tilt.

**Focal length calibration:**
```
focal_length_px = (pixel_width_px × known_distance_cm) / face_width_cm
```
The user sits at a known distance, FaceWatch measures `pixel_width_px` over 30 stable frames and stores the result.

---

## Gaze tracking — ptgaze + affine calibration

### Ray estimation (ptgaze)

ptgaze uses a pre-trained MPIIFaceGaze model to estimate a **3D gaze ray** from the face region. The ray is defined by:
- `face.center` — 3D face center in camera coordinates (meters)
- `face.gaze_vector` — unit direction vector

### Ray-plane intersection

The gaze ray is intersected with the `Z=0` plane (the screen plane in camera space):

```python
fc = face.center * 100.0   # convert to cm
gv = face.gaze_vector

t = -fc[2] / gv[2]         # parameter along ray where Z=0
hit_x = fc[0] + t * gv[0]
hit_y = fc[1] + t * gv[1]
```

This gives a raw `(x_cm, y_cm)` hit point. Returns `None` if the ray points away from the screen (`gv[2] >= 0`).

### Affine calibration

The raw hit point is in camera space and doesn't map directly to screen pixels. A **2×3 affine matrix** is fitted during the 9-point calibration wizard using RANSAC:

```python
M, _ = cv2.estimateAffine2D(
    raw_pts,   # shape (N, 2) — raw hit points collected at each calibration dot
    scr_pts,   # shape (N, 2) — screen pixel coordinates of each dot
    method=cv2.RANSAC,
)
```

At runtime, the affine transform maps raw hits to screen pixels:

```python
uv = M @ [hit_x, hit_y, 1.0]   # homogeneous multiply
screen_x, screen_y = uv[0], uv[1]
```

### Kalman + EMA smoothing

Raw gaze predictions are noisy. A two-stage smoother is applied per face:

**Kalman filter** (constant-velocity model):
```
State:       [x, y, vx, vy]
Transition:  [[1,0,1,0],[0,1,0,1],[0,0,1,0],[0,0,0,1]]
Measurement: [x, y]
```

**EMA** (exponential moving average) on top of Kalman output:
```
ema_x = alpha * ema_x + (1 - alpha) * kalman_x
```
Default `alpha=0.25`. The tune pass after calibration adjusts `measurementNoiseCov` based on observed variance at the tune points.

### On-screen detection with hysteresis

```
looking_at_screen = (
    -margin_x <= screen_x <= screen_w + margin_x  AND
    -margin_y <= screen_y <= screen_h + margin_y
)
```

Margins (default 100px horizontal, 200px vertical) prevent false off-screen triggers at screen edges.

The hysteresis state machine:
```
IDLE → ALERT:   off-screen continuously for gaze_alert_sec (default 10s)
ALERT → IDLE:   on-screen continuously for gaze_return_sec (default 3s)
```

---

## Expression tracking — blendshapes

Each expression reads one or more of MediaPipe's 52 blendshape scores and computes an activation value in `[0, 1]`.

| Expression | Blendshapes used | Formula |
|---|---|---|
| Blink L/R | `eyeBlinkLeft`, `eyeBlinkRight` | direct score |
| Smile | `mouthSmileLeft`, `mouthSmileRight` | average |
| Angry | `browDownLeft`, `browDownRight`, `mouthFrownLeft`, `mouthFrownRight` | 60% brow + 40% frown |
| Surprised | `browOuterUpLeft`, `browOuterUpRight`, `browInnerUp` | average |
| Neutral | all others | `1.0` if all expressions below threshold |

An expression is **active** when its activation exceeds its threshold (configurable per expression). Events are counted with a cooldown to avoid counting the same expression multiple times.

---

## Drowsiness — PERCLOS

PERCLOS (Percentage of Eye Closure) is the standard metric used in driver monitoring systems (SAE J3016).

```
closed_frames = frames where avg(eyeBlinkLeft, eyeBlinkRight) > 0.8
PERCLOS = closed_frames / total_frames_in_rolling_window
```

The rolling window is `drowsy_window_sec` seconds (default 60s). The threshold of `0.8` captures slow drowsy closure — a normal blink peaks at ~0.9–1.0 but lasts only ~150ms, so it contributes minimally to PERCLOS.

Drowsiness is flagged when `PERCLOS > expr_threshold_drowsy` (default `0.15`, i.e. eyes closed >15% of the time).

---

## Focus Score

A composite 0–100 score computed every `stats_interval_sec`:

```
focus_score = (
    gaze_score    × weight_gaze      +   # default 0.40
    drowsy_score  × weight_drowsy    +   # default 0.30
    calm_score    × weight_distract  +   # default 0.20
    posture_score × weight_posture       # default 0.10
) × 100
```

Component formulas:

```
gaze_score    = max(0, 1 - gaze_off_sec / interval_sec)

drowsy_score  = max(0, 1 - drowsy_pct)

calm_score    = max(0, 1 - (angry_count + surprised_count) / 5)

posture_score = 1.0                          if focus_posture_min_cm ≤ dist ≤ focus_posture_max_cm
              = max(0, 1 - deviation/max_cm) otherwise
              = 0.5                          if distance unknown
```

All weights are configurable and stored in the DB. The score is stored per stats interval and aggregated in the daily report.

---

## Demographics — face width estimation

DeepFace estimates age, gender, and race from a face crop. The age and gender are used to look up an anthropometric face width estimate:

| Age range | Base width |
|---|---|
| < 5 years | 10.5 cm |
| 5–9 years | 11.5 cm |
| 10–12 years | 12.5 cm |
| 13–17 years | 13.2 cm |
| 18+ years | 14.0 cm |

Female faces are estimated 0.5 cm narrower. This personalized width feeds directly into the distance formula, improving accuracy compared to a fixed adult average.

---

## Alert hysteresis

Every alert uses the same dual-threshold state machine:

```
IDLE:
    condition=True  → enter_timer += dt
                      if enter_timer >= enter_sec → fire → ACTIVE
    condition=False → enter_timer = 0

ACTIVE:
    condition=False → exit_timer += dt
                      if exit_timer >= exit_sec → clear → IDLE
    condition=True  → exit_timer = 0
```

`exit_sec >= enter_sec` always — this prevents rapid toggling. A brief recovery doesn't clear the alert; the condition must be resolved for the full `exit_sec` duration.
