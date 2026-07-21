import numpy as np
from deepface import DeepFace

from storage.db import Database
from storage.db.connection import Connection
from storage.config_store import ConfigStore


def _embed(crop_bgr: np.ndarray) -> np.ndarray:
    result = DeepFace.represent(
        crop_bgr,
        model_name="Facenet512",
        detector_backend="skip",
        enforce_detection=False,
    )
    vec = np.array(result[0]["embedding"], dtype=np.float32)
    return vec / np.linalg.norm(vec)


def _decode(blob: bytes) -> np.ndarray:
    arr = Connection.blob_to_array(blob)
    norm = np.linalg.norm(arr)
    return arr / norm if norm > 0 else arr


class FaceRecognizer:
    def __init__(self, db: Database, config: ConfigStore):
        self._db = db
        self._config = config

    def identify(self, crop_bgr: np.ndarray) -> tuple[int, float] | None:
        threshold: float = self._config.get("recognition_threshold")
        strategy: str = self._config.get("recognition_match_strategy")

        embedding = _embed(crop_bgr)

        # Group embeddings by face_id
        known_faces = self._db.get_all_known_faces()
        best_face_id: int | None = None
        best_sim: float = -1.0

        for face in known_faces:
            face_id = face["id"]
            blobs = self._db.get_embeddings(face_id)
            if not blobs:
                continue

            vecs = [_decode(b) for b in blobs]

            if strategy == "average":
                mean = np.mean(vecs, axis=0)
                norm = np.linalg.norm(mean)
                candidate = mean / norm if norm > 0 else mean
                sim = float(np.dot(embedding, candidate))
            else:  # best_single
                sim = float(max(np.dot(embedding, v) for v in vecs))

            if sim > best_sim:
                best_sim = sim
                best_face_id = face_id

        if best_face_id is None or best_sim < threshold:
            return None
        return best_face_id, best_sim

    def store_embedding(self, face_id: int, embedding: np.ndarray) -> None:
        norm = np.linalg.norm(embedding)
        vec = embedding / norm if norm > 0 else embedding

        cap: int = self._config.get("max_embeddings_per_face")
        rows = self._db.get_embeddings_with_ids(face_id)

        if len(rows) < cap:
            self._db.add_embedding(face_id, self._db.array_to_blob(vec))
            return
        vecs = [_decode(blob) for _, blob in rows]
        mean = np.mean(vecs, axis=0)
        mean_norm = np.linalg.norm(mean)
        mean = mean / mean_norm if mean_norm > 0 else mean

        dists = [float(1.0 - np.dot(v, mean)) for v in vecs]
        new_dist = float(1.0 - np.dot(vec, mean))

        farthest_idx = int(np.argmax(dists))
        if new_dist >= dists[farthest_idx]:
            return  # new embedding is the outlier — drop it

        self._db.delete_embedding_by_id(rows[farthest_idx][0])
        self._db.add_embedding(face_id, self._db.array_to_blob(vec))
