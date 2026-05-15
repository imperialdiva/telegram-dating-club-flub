from datetime import datetime
from typing import Iterable


PRIMARY_WEIGHT = 0.45
BEHAVIORAL_WEIGHT = 0.35
REFERRAL_WEIGHT = 0.10
ACTIVITY_WEIGHT = 0.10


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
    """Уровень 1: рейтинг по полноте анкеты + загруженным фото."""
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

    photos = list(getattr(user, "photos", None) or [])
    if photos:
        score += min(len(photos), 5) * 1.5
    elif user.photo_id:
        score += 1.5

    interests = list(getattr(user, "interests", None) or [])
    if interests:
        score += min(len(interests), 5) * 0.5

    if user.preferred_city:
        score += 0.5
    if user.preferred_gender:
        score += 0.5
    if user.preferred_age_min is not None and user.preferred_age_max is not None:
        score += 1.0

    return round(score, 2)


def calculate_behavioral_score(
    likes_received: int,
    skips_received: int,
    matches_count: int,
    dialogs_started: int = 0,
) -> float:
    """Уровень 2: динамический рейтинг по реакции пользователей."""
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


def calculate_referral_score(referrals_count: int) -> float:
    """Уровень 3: бонус за реферальную систему."""
    return round(float(min(referrals_count * 2, 10)), 2)


def calculate_activity_score(
    activity_by_hour: dict[int, int],
    last_active_at: datetime | None = None,
    now: datetime | None = None,
) -> float:
    """Уровень 2/3: бонус за активность пользователя.

    Учитываем общую частоту, попадание текущего часа в "пик" и свежесть онлайна.
    """
    score = 0.0
    total = sum(activity_by_hour.values()) if activity_by_hour else 0
    if total:
        score += min(total / 5.0, 4.0)
        peak_hours = sorted(
            activity_by_hour.items(), key=lambda item: item[1], reverse=True
        )[:3]
        peak_set = {hour for hour, _ in peak_hours if _ > 0}
        current_hour = (now or datetime.utcnow()).hour
        if current_hour in peak_set:
            score += 2.0

    if last_active_at:
        delta = (now or datetime.utcnow()) - last_active_at
        if delta.total_seconds() < 3600:
            score += 3.0
        elif delta.total_seconds() < 24 * 3600:
            score += 1.5

    return round(score, 2)


def combine_scores(
    primary_score: float,
    behavioral_score: float,
    referral_score: float = 0.0,
    activity_score: float = 0.0,
) -> float:
    return round(
        primary_score * PRIMARY_WEIGHT
        + behavioral_score * BEHAVIORAL_WEIGHT
        + referral_score * REFERRAL_WEIGHT
        + activity_score * ACTIVITY_WEIGHT,
        2,
    )


def _interests_overlap(a: Iterable[str] | None, b: Iterable[str] | None) -> int:
    set_a = {str(i).strip().lower() for i in (a or []) if str(i).strip()}
    set_b = {str(i).strip().lower() for i in (b or []) if str(i).strip()}
    return len(set_a & set_b)


def compatibility_bonus(me, candidate) -> float:
    """Персональный бонус совместимости — добавляется к combined_score кандидата."""
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

    overlap = _interests_overlap(
        getattr(me, "interests", None),
        getattr(candidate, "interests", None),
    )
    if overlap:
        score += min(overlap * 1.0, 4.0)

    if candidate.bio:
        score += 0.5

    candidate_photos = getattr(candidate, "photos", None) or []
    if candidate_photos:
        score += 0.5
    elif candidate.photo_id:
        score += 0.5

    return round(score, 2)
