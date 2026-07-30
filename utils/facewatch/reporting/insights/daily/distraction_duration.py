from reporting.insights.base import Insight


class DistractionDuration(Insight):
    id    = "distraction_duration"
    scope = "daily"

    def compute(self, conn, face_id: int, date: str, config) -> dict | None:
        return None  # TODO: I5
