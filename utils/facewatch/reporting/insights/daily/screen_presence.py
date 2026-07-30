from reporting.insights.base import Insight


class ScreenPresence(Insight):
    id    = "screen_presence"
    scope = "daily"

    def compute(self, conn, face_id: int, date: str) -> dict | None:
        return None  # TODO: I8
