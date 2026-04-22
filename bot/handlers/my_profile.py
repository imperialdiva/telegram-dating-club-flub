import logging
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
import httpx
from config import config

router = Router()


def _profile_inline_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✏️ Редактировать анкету", callback_data="edit_profile"))
    return kb.as_markup()


@router.message(F.text == "👤 Моя анкета")
async def show_my_profile(message: types.Message):
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{config.BACKEND_URL}/profile/{message.from_user.id}",
                timeout=5.0,
            )
        except Exception as e:
            logging.error(f"Ошибка /profile: {e}")
            await message.answer("Не удалось загрузить анкету. Попробуй позже.")
            return

    if resp.status_code == 404:
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="📝 Заполнить анкету", callback_data="edit_profile"))
        await message.answer(
            "У тебя пока нет анкеты.\nЗаполни её, чтобы начать знакомиться!",
            reply_markup=kb.as_markup(),
        )
        return

    data = resp.json()

    if not data.get("photo_id"):
        kb = InlineKeyboardBuilder()
        kb.row(types.InlineKeyboardButton(text="✏️ Дозаполнить анкету", callback_data="edit_profile"))
        await message.answer(
            "Анкета заполнена не полностью. Добавь фото и остальные данные.",
            reply_markup=kb.as_markup(),
        )
        return

    caption = (
        f"<b>{data['name']}, {data['age']}</b>\n"
        f"📍 {data['city']}\n"
        f"{'♂️' if data['gender'] == 'Мужской' else '♀️'} {data['gender']}\n\n"
        f"{data['bio']}"
    )

    await message.answer_photo(
        photo=data["photo_id"],
        caption=caption,
        parse_mode="HTML",
        reply_markup=_profile_inline_kb(),
    )
