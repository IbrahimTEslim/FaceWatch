DEFAULT_FACE_WIDTH_CM = 14.0  # adult average — fallback when demographics unavailable


def estimate_face_width_cm(age: int, gender: str) -> float:
    """
    Returns estimated face width in cm based on age and gender.
    Source: anthropometric studies on facial dimensions.
    Children: ~10.5–12.5cm. Teens: ~13.2cm. Adults: ~14.0cm.
    Female faces average ~0.5cm narrower than male.
    """
    if age < 5:
        base = 10.5
    elif age < 10:
        base = 11.5
    elif age < 13:
        base = 12.5
    elif age < 18:
        base = 13.2
    else:
        base = DEFAULT_FACE_WIDTH_CM

    if gender and gender.lower() in ("woman", "female", "f"):
        base -= 0.5

    return base
