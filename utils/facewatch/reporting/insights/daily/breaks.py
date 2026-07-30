from reporting.insights.base import Insight


class MeaningfulBreaks(Insight):
    id    = "meaningful_breaks"
    scope = "daily"

    def compute(self, conn, face_id: int, date: str) -> dict | None:
        return None  # TODO: I4
