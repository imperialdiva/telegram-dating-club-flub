"""Чистые форматирующие функции — без I/O, легко тестировать."""


def format_ttl(seconds: int) -> str:
    seconds = int(seconds or 0)
    if seconds <= 0:
        return "0м"
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    if hours and minutes:
        return f"{hours}ч {minutes}м"
    if hours:
        return f"{hours}ч"
    return f"{minutes}м"


def format_my_profile(data: dict) -> str:
    name = data.get("name") or "—"
    age = data.get("age") or "?"
    city = data.get("city") or "—"
    gender = data.get("gender") or "—"
    bio = data.get("bio") or "—"
    interests = data.get("interests") or []
    rating = data.get("rating") or {}
    referrals_count = data.get("referrals_count", 0)
    boost = data.get("boost") or {}

    interests_line = ", ".join(interests) if interests else "—"
    rating_line = (
        f"⭐ Рейтинг: <b>{rating.get('combined_score', 0)}</b> "
        f"(анкета {rating.get('primary_score', 0)}, поведение {rating.get('behavioral_score', 0)}, "
        f"актив {rating.get('activity_score', 0)}, рефералы {rating.get('referral_score', 0)})"
    )
    boost_line = ""
    if boost.get("active"):
        boost_line = (
            f"\n🚀 <b>Активный буст:</b> ×{float(boost.get('multiplier', 1)):.2f} "
            f"(осталось {format_ttl(boost.get('ttl_seconds', 0))})"
        )

    gender_emoji = (
        "♂️" if gender == "Мужской" else ("♀️" if gender == "Женский" else "•")
    )
    return (
        f"<b>{name}, {age}</b>\n"
        f"📍 {city}\n"
        f"{gender_emoji} {gender}\n"
        f"🎯 Интересы: {interests_line}\n"
        f"👥 Приглашённых друзей: {referrals_count}{boost_line}\n\n"
        f"{bio}\n\n"
        f"{rating_line}"
    )


def format_candidate(data: dict) -> str:
    name = data.get("name") or "—"
    age = data.get("age") or "?"
    city = data.get("city") or "—"
    bio = data.get("bio") or ""
    interests = data.get("interests") or []
    interests_line = f"\n🎯 {', '.join(interests)}" if interests else ""
    boost_line = "🚀 <i>boosted</i>\n" if data.get("boosted") else ""
    return (
        f"{boost_line}"
        f"<b>{name}, {age}</b>\n"
        f"📍 {city}{interests_line}\n\n"
        f"{bio}"
    )


def format_boost_info(info: dict) -> str:
    multiplier = float(info.get("multiplier") or 1.0)
    ttl = int(info.get("ttl_seconds") or 0)
    cooldown = int(info.get("daily_boost_cooldown") or 0)

    if info.get("active") and ttl > 0:
        active = (
            f"🚀 <b>Активный буст:</b> ×{multiplier:.2f}\n"
            f"Осталось: <b>{format_ttl(ttl)}</b>\n\n"
        )
    else:
        active = "Активного буста нет.\n\n"

    if cooldown > 0:
        cooldown_line = (
            f"⏳ Дневной буст можно будет забрать через <b>{format_ttl(cooldown)}</b>."
        )
    else:
        cooldown_line = (
            "🎁 Дневной буст готов к получению — "
            "+30% к видимости в чужих очередях на 24 часа."
        )

    return (
        "<b>🚀 Буст-система</b>\n\n"
        + active
        + cooldown_line
        + "\n\nКак получить:\n"
        "• новичкам — автоматически ×2 на 1ч\n"
        "• за каждого приглашённого друга — ×1.5 на 24ч\n"
        "• за заполненную анкету с фото — ×1.4 на 1ч\n"
        "• ежедневно вручную — ×1.3 на 24ч"
    )
