from reporting.insights.base import Insight


class LongestSession(Insight):
    id    = "longest_session"
    scope = "daily"

    def compute(self, conn, face_id: int, date: str) -> dict | None:
        return None  # TODO: I3
