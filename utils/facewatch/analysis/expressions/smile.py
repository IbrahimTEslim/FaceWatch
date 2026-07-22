from .base import Expression


class Smile(Expression):
    name = "smile"
    color = (0, 255, 128)
    threshold_key = "expr_threshold_smile"
    cooldown_sec = 1.0
    count_events = True

    def compute_activation(self, blendshapes: dict[str, float], landmarks: list) -> float:
        return (blendshapes.get("mouthSmileLeft", 0.0) + blendshapes.get("mouthSmileRight", 0.0)) / 2.0
