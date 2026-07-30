from reporting.insights.base import Insight


class FirstFatigue(Insight):
    id    = "first_fatigue"
    scope = "daily"

    def compute(self, conn, face_id: int, date: str) -> dict | None:
        return None  # TODO: I7
