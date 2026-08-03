from .base import Insight

# Scores
from .scores.focus_score import FocusScore
from .scores.fatigue_score import FatigueScore
from .scores.ergonomic_score import ErgonomicScore

# Daily
from .daily.longest_session import LongestSession
from .daily.breaks import MeaningfulBreaks
from .daily.distraction_duration import DistractionDuration
from .daily.best_focus_hour import BestFocusHour
from .daily.first_fatigue import FirstFatigue
from .daily.screen_presence import ScreenPresence
from .daily.viewing_distance_trend import ViewingDistanceTrend

# Weekly
from .weekly.consistency import ConsistencyScore
from .weekly.best_weekday import BestWeekday


_INSIGHTS: list[Insight] = [
    # Scores
    FocusScore(),
    FatigueScore(),
    ErgonomicScore(),
    # Daily
    LongestSession(),
    MeaningfulBreaks(),
    DistractionDuration(),
    BestFocusHour(),
    FirstFatigue(),
    ScreenPresence(),
    ViewingDistanceTrend(),
    # Weekly
    ConsistencyScore(),
    BestWeekday(),
]


def build_insights(conn, face_id: int, date: str, config) -> dict:
    """
    Run all registered insights. Returns a dict keyed by insight id.
    Insights returning None (insufficient data) are omitted.
    """
    result: dict[str, dict] = {}
    for insight in _INSIGHTS:
        data = insight.compute(conn, face_id, date, config)
        if data is not None:
            result[insight.id] = data
    return result
