import logging

from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from api import backend
from services.format import format_candidate
from services.notify import notify_match


router = Router()
logger = logging.getLogger(__name__)


def _build_profile_kb(profile_tg_id: int) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="❤️ Нравится", callback_data=f"like_{profile_tg_id}"),
        types.InlineKeyboardButton(text="👎 Дальше", callback_data=f"skip_{profile_tg_id}"),
    )
    return kb.as_markup()


async def _fetch_and_show(tg_id: int, target) -> None:
    message = target if isinstance(target, types.Message) else target.message

    try:
        data = await backend.next_match(tg_id)
    except Exception:
        logger.exception("Ошибка /get_match")
        await message.answer("Не удалось загрузить анкеты. Попробуй позже.")
        return

    if data.get("status") == "error":
        await message.answer(data.get("message", "Пока никого нет :("))
        return

    caption = format_candidate(data)
    photo_to_show = data.get("photo_id")
    kb = _build_profile_kb(data["tg_id"])

    if photo_to_show:
        await message.answer_photo(
            photo=photo_to_show, caption=caption, parse_mode="HTML", reply_markup=kb
        )
    else:
        urls = data.get("photo_urls") or []
        url_block = f"\n\n🖼 {urls[0]}" if urls else ""
        await message.answer(caption + url_block, parse_mode="HTML", reply_markup=kb)


@router.message(F.text.in_({"🔍 Смотреть анкеты", "Смотреть анкеты"}))
async def show_match(message: types.Message):
    await _fetch_and_show(message.from_user.id, message)


@router.callback_query(F.data.startswith("skip_"))
async def cb_skip(callback: types.CallbackQuery):
    skipped_tg_id = int(callback.data.split("_", 1)[1])
    try:
        await backend.skip(callback.from_user.id, skipped_tg_id)
    except Exception:
        logger.exception("Ошибка /skip")
    await callback.answer()
    await _fetch_and_show(callback.from_user.id, callback)


@router.callback_query(F.data.startswith("like_"))
async def cb_like(callback: types.CallbackQuery):
    liked_tg_id = int(callback.data.split("_", 1)[1])

    try:
        result = await backend.like(callback.from_user.id, liked_tg_id)
    except Exception:
        logger.exception("Ошибка /like")
        await callback.answer("Не удалось отправить лайк.", show_alert=True)
        return

    status = result.get("status")
    mutual = result.get("mutual", False)
    match_created = result.get("match_created", False)
    matched_profile = result.get("matched_profile") or {}
    actor_profile = result.get("actor_profile") or {}

    if status == "already_liked":
        await callback.answer("Ты уже ставил(а) лайк этой анкете.")
    elif mutual:
        await callback.answer("🎉 Взаимный лайк!", show_alert=True)
        if match_created:
            await notify_match(
                bot=callback.message.bot,
                actor_tg_id=callback.from_user.id,
                actor_name=(
                    actor_profile.get("name")
                    or callback.from_user.first_name
                    or "Кто-то"
                ),
                partner_tg_id=liked_tg_id,
                partner_name=matched_profile.get("name") or "Новый мэтч",
            )
    else:
        await callback.answer("❤️ Лайк отправлен!")

    await _fetch_and_show(callback.from_user.id, callback)
