import logging

from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from api import backend
from services.format import format_my_profile


router = Router()
logger = logging.getLogger(__name__)


def _profile_inline_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_profile"))
    return kb.as_markup()


@router.message(F.text == "👤 Моя анкета")
async def show_my_profile(message: types.Message):
    try:
        data = await backend.get_profile(message.from_user.id)
    except Exception:
        logger.exception("Ошибка /profile")
        await message.answer("Не удалось загрузить анкету. Попробуй позже.")
        return

    if data is None:
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="📝 Заполнить анкету", callback_data="edit_profile"))
        await message.answer(
            "У тебя пока нет анкеты.\nЗаполни её, чтобы начать знакомиться!",
            reply_markup=kb.as_markup(),
        )
        return

    if not data.get("photo_id") and not data.get("photos"):
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="✏️ Дозаполнить анкету", callback_data="edit_profile"))
        await message.answer(
            "Анкета заполнена не полностью. Добавь фото и остальные данные.",
            reply_markup=kb.as_markup(),
        )
        return

    caption = format_my_profile(data)
    photo_to_show = data.get("photo_id")
    if photo_to_show:
        await message.answer_photo(
            photo=photo_to_show,
            caption=caption,
            parse_mode="HTML",
            reply_markup=_profile_inline_kb(),
        )
    else:
        await message.answer(
            caption, parse_mode="HTML", reply_markup=_profile_inline_kb()
        )
