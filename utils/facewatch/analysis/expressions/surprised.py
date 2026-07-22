from .base import Expression


class Surprised(Expression):
    name = "surprised"
    color = (0, 255, 255)
    threshold_key = "expr_threshold_surprised"
    cooldown_sec = 1.0
    count_events = True

    def compute_activation(self, blendshapes: dict[str, float], landmarks: list) -> float:
        return (
            blendshapes.get("browOuterUpLeft", 0.0)
            + blendshapes.get("browOuterUpRight", 0.0)
            + blendshapes.get("browInnerUp", 0.0)
        ) / 3.0
