from alerts.base import AlertContext, AlertEvent, AlertType, AlertPriority
from alerts.registry import build_alerts


class AlertManager:
    def __init__(self):
        self._tracks: dict[int, list] = {}

    def update(self, track_id: int, ctx: AlertContext, dt: float) -> list[AlertEvent]:
        if track_id not in self._tracks:
            self._tracks[track_id] = build_alerts()
        return [a.update(a.is_condition_met(ctx), dt, ctx.config) for a in self._tracks[track_id]]

    def active(self, track_id: int) -> bool:
        return any(a.active for a in self._tracks.get(track_id, []))

    def active_priorities(self) -> set[AlertPriority]:
        return {a.priority for alerts in self._tracks.values() for a in alerts if a.active}

    def count_active_by_type(self, track_id: int, alert_type: AlertType) -> int:
        return sum(1 for a in self._tracks.get(track_id, []) if a.active and a.alert_type is alert_type)

    def drop(self, track_id: int) -> None:
        self._tracks.pop(track_id, None)
