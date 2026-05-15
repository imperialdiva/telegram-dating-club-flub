"""Константы приложения (настройки буста, лимиты и т.п.)."""

# --- boosts ---
ONBOARDING_BOOST_MULT = 2.0
ONBOARDING_BOOST_TTL = 60 * 60          # 1 час новичку
REFERRER_BOOST_MULT = 1.5
REFERRER_BOOST_TTL = 24 * 60 * 60       # 24 часа за каждого реферала
DAILY_BOOST_MULT = 1.3
DAILY_BOOST_TTL = 24 * 60 * 60          # 24 часа из ежедневного клейма
PROFILE_COMPLETE_BOOST_MULT = 1.4
PROFILE_COMPLETE_BOOST_TTL = 60 * 60    # 1 час за заполнение анкеты с фото

# --- photos ---
MAX_PHOTOS_PER_USER = 5
MAX_PHOTO_BYTES = 8 * 1024 * 1024       # 8 MB

# --- interests ---
MAX_INTERESTS = 10
