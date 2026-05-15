import logging

from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from api import backend
from services.notify import notify_dialog_started


router = Router()
logger = logging.getLogger(__name__)


def _match_kb(partner: dict, partner_id: int, dialog_started: bool) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if not dialog_started:
        kb.row(
            types.InlineKeyboardButton(
                text="💬 Написать первым", callback_data=f"msg_{partner_id}"
            )
        )
    if partner.get("username"):
        kb.row(
            types.InlineKeyboardButton(
                text=f"📨 Открыть @{partner['username']}",
                url=f"https://t.me/{partner['username']}",
            )
        )
    return kb.as_markup()


@router.message(F.text == "💞 Мои мэтчи")
async def show_matches(message: types.Message):
    try:
        data = await backend.list_matches(message.from_user.id)
    except Exception:
        logger.exception("Ошибка /matches")
        await message.answer("Не удалось загрузить мэтчи.")
        return

    matches = data.get("matches") or []
    if not matches:
        await message.answer("Пока нет мэтчей. Лайкай тех, кто нравится 😉")
        return

    for match in matches:
        partner = match.get("partner") or {}
        partner_id = match.get("partner_tg_id")
        name = partner.get("name") or "Кто-то"
        age = partner.get("age") or "?"
        city = partner.get("city") or "—"
        dialog_started = bool(match.get("dialog_started"))

        caption = (
            f"<b>{name}, {age}</b>\n"
            f"📍 {city}\n"
            f"{'💬 Диалог уже начат' if dialog_started else '✨ Напиши первым'}"
        )
        kb = _match_kb(partner, partner_id, dialog_started)
        photo = partner.get("photo_id")
        if photo:
            try:
                await message.answer_photo(
                    photo=photo, caption=caption, parse_mode="HTML", reply_markup=kb
                )
                continue
            except Exception:
                logger.exception("Не удалось показать фото мэтча")
        await message.answer(caption, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("msg_"))
async def cb_message_match(callback: types.CallbackQuery):
    partner_id = int(callback.data.split("_", 1)[1])
    try:
        await backend.dialog_started(callback.from_user.id, partner_id)
    except Exception:
        logger.exception("dialog_started failed")

    await notify_dialog_started(callback.message.bot, callback.from_user, partner_id)
    await callback.answer("Сообщили твоему мэтчу 💌", show_alert=True)
