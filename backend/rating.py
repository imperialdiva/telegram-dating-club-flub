PRIMARY_WEIGHT = 0.6
BEHAVIORAL_WEIGHT = 0.4


def default_preferred_age_range(age: int | None) -> tuple[int | None, int | None]:
    if not age:
        return None, None
    return max(18, int(age) - 5), int(age) + 5


def resolve_preferred_gender(gender: str | None, preferred_gender: str | None) -> str | None:
    if preferred_gender:
        return preferred_gender
    if gender == "Мужской":
        return "Женский"
    if gender == "Женский":
        return "Мужской"
    return None


def calculate_primary_score(user) -> float:
    score = 0.0

    if user.age:
        score += 1.0
    if user.gender:
        score += 1.0
    if user.city:
        score += 1.5
    if user.bio:
        score += 2.0
    if user.username:
        score += 1.0
    if user.photo_id:
        score += 3.0
    if user.preferred_city:
        score += 1.0
    if user.preferred_gender:
        score += 1.0
    if user.preferred_age_min is not None and user.preferred_age_max is not None:
        score += 1.5

    return round(score, 2)


def calculate_behavioral_score(
    likes_received: int,
    skips_received: int,
    matches_count: int,
    dialogs_started: int = 0,
) -> float:
    score = float(min(likes_received * 2, 10))

    total_feedback = likes_received + skips_received
    if total_feedback:
        like_ratio = likes_received / total_feedback
        if like_ratio >= 0.8:
            score += 4.0
        elif like_ratio >= 0.6:
            score += 3.0
        elif like_ratio >= 0.4:
            score += 2.0
        elif like_ratio > 0:
            score += 1.0

    score += float(min(matches_count * 3, 9))
    score += float(min(dialogs_started * 2, 6))
    return round(score, 2)


def combine_scores(primary_score: float, behavioral_score: float) -> float:
    return round(
        (primary_score * PRIMARY_WEIGHT) + (behavioral_score * BEHAVIORAL_WEIGHT),
        2,
    )


def compatibility_bonus(me, candidate) -> float:
    score = 0.0

    preferred_city = me.preferred_city or me.city
    if preferred_city and candidate.city and preferred_city.strip().lower() == candidate.city.strip().lower():
        score += 3.0

    preferred_gender = resolve_preferred_gender(me.gender, me.preferred_gender)
    if preferred_gender and candidate.gender == preferred_gender:
        score += 3.0

    preferred_age_min = me.preferred_age_min
    preferred_age_max = me.preferred_age_max
    if preferred_age_min is None or preferred_age_max is None:
        preferred_age_min, preferred_age_max = default_preferred_age_range(me.age)

    if candidate.age is not None and preferred_age_min is not None and preferred_age_max is not None:
        age = int(candidate.age)
        if preferred_age_min <= age <= preferred_age_max:
            score += 4.0
        else:
            distance = min(abs(age - preferred_age_min), abs(age - preferred_age_max))
            if distance <= 3:
                score += 1.5

    if candidate.bio:
        score += 0.5
    if candidate.photo_id:
        score += 0.5

    return round(score, 2)
