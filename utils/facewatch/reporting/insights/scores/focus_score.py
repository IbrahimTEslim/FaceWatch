from reporting.insights.base import Insight


class FocusScore(Insight):
    id    = "focus_score"
    scope = "score"

    def compute(self, conn, face_id: int, date: str) -> dict | None:
        return None  # TODO: I2
