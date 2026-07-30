from reporting.insights.base import Insight


class BestWeekday(Insight):
    id    = "best_weekday"
    scope = "weekly"

    def compute(self, conn, face_id: int, date: str, config) -> dict | None:
        return None  # TODO: I12
