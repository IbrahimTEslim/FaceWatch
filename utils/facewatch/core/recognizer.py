import threading
import time
import uuid
from dataclasses import dataclass

import numpy as np
from deepface import DeepFace

from storage.db import Database
from storage.db.connection import Connection
from storage.config_store import ConfigStore


@dataclass
class Identity:
    face_id:    int   | None = None
    name:       str          = "unknown"
    display_name: str        = "Unknown"
    status:     str          = "pending"   # pending | known | unknown
    similarity: float        = 0.0


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


def _normalize_name(display_name: str) -> str:
    return display_name.strip().lower()


def _unknown_name() -> str:
    return f"unknown_{uuid.uuid4().hex[:8]}"


class FaceRecognizer:
    def __init__(self, db: Database, config: ConfigStore):
        self._db     = db
        self._config = config
        self._identities:   dict[int, Identity] = {}
        self._pending:      set[int]             = set()
        self._attempts:     dict[int, int]       = {}
        self._last_attempt: dict[int, float]     = {}
        self._lock = threading.Lock()

    def get_identity(self, track_id: int) -> Identity:
        with self._lock:
            return self._identities.get(track_id, Identity())

    def submit(self, track_id: int, crop_bgr: np.ndarray) -> None:
        with self._lock:
            if track_id in self._pending:
                return
            identity = self._identities.get(track_id)
            if identity is not None and identity.status == "known":
                return
            if identity is not None and identity.status == "unknown":
                max_attempts:   int   = self._config.get("max_retry_attempts")
                retry_interval: float = self._config.get("retry_interval_sec")
                attempts = self._attempts.get(track_id, 0)
                if attempts >= max_attempts:
                    return
                if time.monotonic() - self._last_attempt.get(track_id, 0.0) < retry_interval:
                    return
            self._pending.add(track_id)
            self._attempts[track_id]     = self._attempts.get(track_id, 0) + 1
            self._last_attempt[track_id] = time.monotonic()
        t = threading.Thread(target=self._identify_async, args=(track_id, crop_bgr), daemon=True)
        t.start()

    def drop_track(self, track_id: int) -> None:
        with self._lock:
            self._identities.pop(track_id, None)
            self._pending.discard(track_id)
            self._attempts.pop(track_id, None)
            self._last_attempt.pop(track_id, None)

    def force_reidentify(self, track_id: int) -> None:
        with self._lock:
            self._attempts[track_id]     = 0
            self._last_attempt[track_id] = 0.0
            self._identities.pop(track_id, None)
            self._pending.discard(track_id)

    def hard_reassign(self, track_id: int, target_face_id: int, target_display_name: str) -> None:
        """Move current track's unknown embeddings to target_face_id, update identity."""
        identity = self.get_identity(track_id)
        if identity.face_id and identity.status == "unknown":
            # Move embeddings from unknown record to target face
            blobs = self._db.get_embeddings(identity.face_id)
            for blob in blobs:
                vec = _decode(blob)
                self.store_embedding(target_face_id, vec)
            self._db.delete_face(identity.face_id)

        face = self._db.get_face_by_id(target_face_id)
        with self._lock:
            self._identities[track_id] = Identity(
                face_id=target_face_id,
                name=face["name"] if face else _normalize_name(target_display_name),
                display_name=target_display_name,
                status="known",
                similarity=1.0,
            )
            self._attempts.pop(track_id, None)
            self._last_attempt.pop(track_id, None)

    def register(self, track_id: int, display_name: str, live_crop: np.ndarray) -> int:
        """
        Register current track as a known face.
        If track already has an unknown record, rename it.
        Runs live_crop through store_embedding — algorithm keeps or drops it.
        Returns face_id.
        """
        name = _normalize_name(display_name)
        identity = self.get_identity(track_id)

        if identity.face_id and identity.status == "unknown":
            self._db.rename_face(identity.face_id, name, display_name)
            self._db.update_face_status(identity.face_id, "known")
            face_id = identity.face_id
        else:
            face_id = self._db.upsert_face(name, display_name, "known")

        try:
            vec = _embed(live_crop)
            self.store_embedding(face_id, vec)
        except Exception:
            pass

        with self._lock:
            self._identities[track_id] = Identity(
                face_id=face_id,
                name=name,
                display_name=display_name,
                status="known",
                similarity=1.0,
            )
            self._attempts.pop(track_id, None)
            self._last_attempt.pop(track_id, None)

        return face_id

    def _identify_async(self, track_id: int, crop_bgr: np.ndarray) -> None:
        try:
            embedding = _embed(crop_bgr)
            identity  = self._resolve(track_id, embedding)
        except Exception:
            identity = self._get_or_create_unknown(track_id, None)
        with self._lock:
            self._identities[track_id] = identity
            self._pending.discard(track_id)

    def _resolve(self, track_id: int, embedding: np.ndarray) -> Identity:
        known_threshold:   float = self._config.get("recognition_threshold")
        unknown_threshold: float = self._config.get("unknown_match_threshold")

        best_known_id:  int   | None = None
        best_known_sim: float        = -1.0
        best_unknown_id:  int   | None = None
        best_unknown_sim: float        = -1.0

        # One pass — all faces
        for face in self._db.get_all_known_faces() + self._db.get_all_unknown_faces():
            face_id = face["id"]
            blobs   = self._db.get_embeddings(face_id)
            if not blobs:
                continue

            strategy: str = self._config.get("recognition_match_strategy")
            vecs = [_decode(b) for b in blobs]

            if strategy == "average":
                mean = np.mean(vecs, axis=0)
                norm = np.linalg.norm(mean)
                candidate = mean / norm if norm > 0 else mean
                sim = float(np.dot(embedding, candidate))
            else:
                sim = float(max(np.dot(embedding, v) for v in vecs))

            if face["status"] == "known":
                if sim > best_known_sim:
                    best_known_sim = sim
                    best_known_id  = face_id
            else:
                if sim > best_unknown_sim:
                    best_unknown_sim = sim
                    best_unknown_id  = face_id

        # Known wins if it clears threshold — regardless of unknown score
        if best_known_id is not None and best_known_sim >= known_threshold:
            face = self._db.get_face_by_id(best_known_id)
            # Merge unknown record if this track had one
            self._merge_unknown(track_id, best_known_id)
            return Identity(
                face_id=best_known_id,
                name=face["name"],
                display_name=face.get("display_name", face["name"]),
                status="known",
                similarity=best_known_sim,
            )

        # Returning unknown
        if best_unknown_id is not None and best_unknown_sim >= unknown_threshold:
            face = self._db.get_face_by_id(best_unknown_id)
            self._db.add_embedding(best_unknown_id, Connection.array_to_blob(embedding))
            return Identity(
                face_id=best_unknown_id,
                name=face["name"],
                display_name=face.get("display_name", face["name"]),
                status="unknown",
                similarity=best_unknown_sim,
            )

        # New unknown — create record, save embedding immediately
        return self._get_or_create_unknown(track_id, embedding)

    def _get_or_create_unknown(self, track_id: int, embedding: np.ndarray | None) -> Identity:
        identity = self._identities.get(track_id)
        if identity and identity.face_id and identity.status == "unknown":
            face_id = identity.face_id
        else:
            uname   = _unknown_name()
            face_id = self._db.upsert_face(uname, "Unknown", "unknown")

        if embedding is not None:
            self.store_embedding(face_id, embedding)

        face = self._db.get_face_by_id(face_id)
        return Identity(
            face_id=face_id,
            name=face["name"] if face else "unknown",
            display_name="Unknown",
            status="unknown",
        )

    def _merge_unknown(self, track_id: int, known_face_id: int) -> None:
        """If this track had an unknown record, move its embeddings to known face and delete it."""
        identity = self._identities.get(track_id)
        if not identity or identity.status != "unknown" or not identity.face_id:
            return
        blobs = self._db.get_embeddings(identity.face_id)
        for blob in blobs:
            self.store_embedding(known_face_id, _decode(blob))
        self._db.delete_face(identity.face_id)

    def identify(self, crop_bgr: np.ndarray) -> tuple[int, float] | None:
        """Direct identification — used in tests and manual flows."""
        known_threshold: float = self._config.get("recognition_threshold")
        strategy: str          = self._config.get("recognition_match_strategy")
        embedding = _embed(crop_bgr)

        best_face_id: int   | None = None
        best_sim:     float        = -1.0

        for face in self._db.get_all_known_faces():
            face_id = face["id"]
            blobs   = self._db.get_embeddings(face_id)
            if not blobs:
                continue
            vecs = [_decode(b) for b in blobs]
            if strategy == "average":
                mean = np.mean(vecs, axis=0)
                norm = np.linalg.norm(mean)
                candidate = mean / norm if norm > 0 else mean
                sim = float(np.dot(embedding, candidate))
            else:
                sim = float(max(np.dot(embedding, v) for v in vecs))
            if sim > best_sim:
                best_sim     = sim
                best_face_id = face_id

        if best_face_id is None or best_sim < known_threshold:
            return None
        return best_face_id, best_sim

    def store_embedding(self, face_id: int, vec: np.ndarray) -> None:
        norm = np.linalg.norm(vec)
        vec  = vec / norm if norm > 0 else vec

        cap: int = self._config.get("max_embeddings_per_face")
        rows     = self._db.get_embeddings_with_ids(face_id)

        if len(rows) < cap:
            self._db.add_embedding(face_id, Connection.array_to_blob(vec))
            return

        vecs      = [_decode(blob) for _, blob in rows]
        mean      = np.mean(vecs, axis=0)
        mean_norm = np.linalg.norm(mean)
        mean      = mean / mean_norm if mean_norm > 0 else mean

        dists         = [float(1.0 - np.dot(v, mean)) for v in vecs]
        new_dist      = float(1.0 - np.dot(vec, mean))
        farthest_idx  = int(np.argmax(dists))

        if new_dist >= dists[farthest_idx]:
            return

        self._db.delete_embedding_by_id(rows[farthest_idx][0])
        self._db.add_embedding(face_id, Connection.array_to_blob(vec))
