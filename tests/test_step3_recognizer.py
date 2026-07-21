"""
Smoke tests for Step 3: core/recognizer.py
Run from project root:
    venv/Scripts/python.exe tests/test_step3_recognizer.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils", "facewatch"))

import io
import numpy as np
from unittest.mock import MagicMock
from storage.db.connection import Connection
from core.recognizer import FaceRecognizer, _embed, _decode


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_unit(dim: int = 512, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.random(dim).astype(np.float32)
    return v / np.linalg.norm(v)


def _to_blob(vec: np.ndarray) -> bytes:
    buf = io.BytesIO()
    np.save(buf, vec)
    return buf.getvalue()


def _make_recognizer(known_faces, embeddings_by_id, config_overrides=None):
    db = MagicMock()
    config = MagicMock()

    cfg = {
        "recognition_threshold": 0.60,
        "recognition_match_strategy": "best_single",
        "max_embeddings_per_face": 3,
    }
    if config_overrides:
        cfg.update(config_overrides)
    config.get.side_effect = lambda k: cfg[k]

    db.get_all_known_faces.return_value = known_faces
    db.get_embeddings.side_effect = lambda fid: [
        _to_blob(v) for v in embeddings_by_id.get(fid, [])
    ]
    db.get_embeddings_with_ids.side_effect = lambda fid: [
        (i, _to_blob(v)) for i, v in enumerate(embeddings_by_id.get(fid, []))
    ]
    db.array_to_blob.side_effect = _to_blob

    return FaceRecognizer(db, config), db


# ── tests ─────────────────────────────────────────────────────────────────────

def test_identify_returns_none_when_no_faces():
    r, _ = _make_recognizer([], {})
    crop = np.zeros((100, 100, 3), dtype=np.uint8)
    # DeepFace will fail on blank crop — expect None or exception handled upstream
    # We test the no-known-faces short-circuit by patching _embed
    import core.recognizer as mod
    orig = mod._embed
    mod._embed = lambda _: _make_unit(seed=1)
    result = r.identify(crop)
    mod._embed = orig
    assert result is None
    print("  [OK] identify returns None when no known faces")


def test_identify_matches_similar_embedding():
    vec = _make_unit(seed=42)
    r, _ = _make_recognizer(
        known_faces=[{"id": 1}],
        embeddings_by_id={1: [vec]},
    )
    import core.recognizer as mod
    orig = mod._embed
    mod._embed = lambda _: vec  # identical → sim=1.0
    result = r.identify(np.zeros((100, 100, 3), dtype=np.uint8))
    mod._embed = orig
    assert result is not None
    face_id, sim = result
    assert face_id == 1
    assert sim > 0.99
    print(f"  [OK] identify matches correct face (sim={sim:.4f})")


def test_identify_rejects_below_threshold():
    vec_stored = _make_unit(seed=1)
    vec_query = _make_unit(seed=99)  # unrelated vector
    r, _ = _make_recognizer(
        known_faces=[{"id": 1}],
        embeddings_by_id={1: [vec_stored]},
        config_overrides={"recognition_threshold": 0.99},  # very high threshold
    )
    import core.recognizer as mod
    orig = mod._embed
    mod._embed = lambda _: vec_query
    result = r.identify(np.zeros((100, 100, 3), dtype=np.uint8))
    mod._embed = orig
    assert result is None
    print("  [OK] identify rejects match below threshold")


def test_store_embedding_adds_when_under_cap():
    r, db = _make_recognizer(
        known_faces=[],
        embeddings_by_id={1: []},
        config_overrides={"max_embeddings_per_face": 3},
    )
    db.get_embeddings_with_ids.return_value = []
    vec = _make_unit(seed=5)
    r.store_embedding(1, vec)
    db.add_embedding.assert_called_once()
    db.delete_embedding_by_id.assert_not_called()
    print("  [OK] store_embedding adds when under cap")


def test_store_embedding_evicts_farthest_not_new():
    # Build controlled vectors: v0 and v1 point in same direction, v_far is orthogonal
    dim = 512
    v0 = np.zeros(dim, dtype=np.float32); v0[0] = 1.0
    v1 = np.zeros(dim, dtype=np.float32); v1[0] = 0.9; v1[1] = 0.1
    v1 /= np.linalg.norm(v1)
    v_far = np.zeros(dim, dtype=np.float32); v_far[1] = 1.0  # orthogonal to v0
    v_new = np.zeros(dim, dtype=np.float32); v_new[0] = 0.95; v_new[1] = 0.05
    v_new /= np.linalg.norm(v_new)  # close to cluster

    existing = [(0, _to_blob(v0)), (1, _to_blob(v1)), (2, _to_blob(v_far))]

    db = MagicMock()
    config = MagicMock()
    config.get.side_effect = lambda k: {"max_embeddings_per_face": 3}.get(k, None)
    db.get_embeddings_with_ids.return_value = existing
    db.array_to_blob.side_effect = _to_blob

    r = FaceRecognizer(db, config)
    r.store_embedding(1, v_new)

    db.delete_embedding_by_id.assert_called_once_with(2)  # v_far's id
    db.add_embedding.assert_called_once()
    print("  [OK] store_embedding evicts farthest existing, keeps new")


def test_store_embedding_drops_new_if_it_is_outlier():
    base = _make_unit(seed=0)
    close1 = _make_unit(seed=1)
    close2 = _make_unit(seed=2)
    outlier_new = _make_unit(seed=99)

    existing = [(0, _to_blob(base)), (1, _to_blob(close1)), (2, _to_blob(close2))]

    db = MagicMock()
    config = MagicMock()
    config.get.side_effect = lambda k: {"max_embeddings_per_face": 3}.get(k, None)
    db.get_embeddings_with_ids.return_value = existing
    db.array_to_blob.side_effect = _to_blob

    r = FaceRecognizer(db, config)
    r.store_embedding(1, outlier_new)

    db.delete_embedding_by_id.assert_not_called()
    db.add_embedding.assert_not_called()
    print("  [OK] store_embedding drops new embedding when it is the outlier")


def test_decode_normalizes_blob():
    vec = np.array([3.0, 4.0], dtype=np.float32)  # norm=5, not unit
    blob = _to_blob(vec)
    result = _decode(blob)
    assert abs(np.linalg.norm(result) - 1.0) < 1e-6
    print("  [OK] _decode normalizes to unit vector")


# ── runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\nStep 3 — Recognizer Smoke Tests\n")

    tests = [
        test_identify_returns_none_when_no_faces,
        test_identify_matches_similar_embedding,
        test_identify_rejects_below_threshold,
        test_store_embedding_adds_when_under_cap,
        test_store_embedding_evicts_farthest_not_new,
        test_store_embedding_drops_new_if_it_is_outlier,
        test_decode_normalizes_blob,
    ]

    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {t.__name__}: {e}")

    print(f"\n{passed}/{len(tests)} tests passed")
