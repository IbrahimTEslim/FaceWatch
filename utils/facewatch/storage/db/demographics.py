from .connection import Connection, now_utc


class DemographicsQueries:
    def __init__(self, cx: Connection):
        self._cx = cx

    def upsert_demographics(self, face_id: int, age: int, gender: str, race: str,
                            face_width_cm: float, confidence: float) -> None:
        with self._cx.lock:
            self._cx.conn.execute(
                """INSERT INTO demographics
                       (face_id, age_estimate, gender, race, face_width_cm, confidence, last_updated)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(face_id) DO UPDATE SET
                       age_estimate=excluded.age_estimate,
                       gender=excluded.gender,
                       race=excluded.race,
                       face_width_cm=excluded.face_width_cm,
                       confidence=excluded.confidence,
                       last_updated=excluded.last_updated""",
                (face_id, age, gender, race, face_width_cm, confidence, now_utc()),
            )
            self._cx.conn.commit()

    def get_demographics(self, face_id: int) -> dict | None:
        row = self._cx.conn.execute(
            "SELECT * FROM demographics WHERE face_id=?", (face_id,)
        ).fetchone()
        return dict(row) if row else None
