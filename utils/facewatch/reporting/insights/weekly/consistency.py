from reporting.insights.base import Insight


class ConsistencyScore(Insight):
    id    = "consistency_score"
    scope = "weekly"

    def compute(self, conn, face_id: int, date: str, config) -> dict | None:
        return None  # TODO: I11
