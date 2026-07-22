from .base import Expression


class BlinkLeft(Expression):
    name = "blink_left"
    color = (255, 200, 0)
    threshold_key = "expr_threshold_blink"
    cooldown_sec = 0.2
    count_events = True

    def compute_activation(self, blendshapes: dict[str, float], landmarks: list) -> float:
        return blendshapes.get("eyeBlinkLeft", 0.0)


class BlinkRight(Expression):
    name = "blink_right"
    color = (255, 200, 0)
    threshold_key = "expr_threshold_blink"
    cooldown_sec = 0.2
    count_events = True

    def compute_activation(self, blendshapes: dict[str, float], landmarks: list) -> float:
        return blendshapes.get("eyeBlinkRight", 0.0)
