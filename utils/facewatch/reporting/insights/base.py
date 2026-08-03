from abc import ABC, abstractmethod

from storage.config_store import ConfigStore


class Insight(ABC):
    id:    str   # unique key, used in template and JSON
    scope: str   # "daily" | "weekly" | "score"

    @abstractmethod
    def compute(self, conn, face_id: int, date: str, config: ConfigStore) -> dict | None:
        """
        Return a dict of insight data, or None if insufficient data.
        The dict must always include at least {"id": self.id}.
        """
