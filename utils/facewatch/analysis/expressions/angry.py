from .base import Expression


class Angry(Expression):
    name = "angry"
    color = (0, 0, 255)
    threshold_key = "expr_threshold_angry"
    cooldown_sec = 1.5
    count_events = True

    def compute_activation(self, blendshapes: dict[str, float], landmarks: list) -> float:
        return (blendshapes.get("browDownLeft", 0.0) + blendshapes.get("browDownRight", 0.0)) / 2.0
