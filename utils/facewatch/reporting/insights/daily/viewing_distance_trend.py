from reporting.insights.base import Insight


class ViewingDistanceTrend(Insight):
    id    = "viewing_distance_trend"
    scope = "daily"

    def compute(self, conn, face_id: int, date: str) -> dict | None:
        return None  # TODO: I9
