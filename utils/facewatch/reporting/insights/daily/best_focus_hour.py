from reporting.insights.base import Insight


class BestFocusHour(Insight):
    id    = "best_focus_hour"
    scope = "daily"

    def compute(self, conn, face_id: int, date: str) -> dict | None:
        return None  # TODO: I6
