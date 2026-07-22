from .base import Expression
from .blink import BlinkLeft, BlinkRight
from .smile import Smile
from .angry import Angry
from .surprised import Surprised
from .drowsy import Drowsy
from .neutral import Neutral


def build_expressions() -> list[Expression]:
    others: list[Expression] = [
        BlinkLeft(),
        BlinkRight(),
        Smile(),
        Angry(),
        Surprised(),
        Drowsy(),
    ]
    return others + [Neutral(others)]
