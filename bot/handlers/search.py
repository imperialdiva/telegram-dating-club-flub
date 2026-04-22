import logging
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
import httpx
from config import config

router = Router()


def _build_profile_kb(profile_tg_id: int) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="❤️ Нравится", callback_data=f"like_{profile_tg_id}"),
        types.InlineKeyboardButton(text="👎 Дальше",   callback_data=f"skip_{profile_tg_id}"),
    )
    return kb.as_markup()


async def _fetch_and_show(tg_id: int, target: types.Message | types.CallbackQuery) -> None:
    message = target if isinstance(target, types.Message) else target.message

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{config.BACKEND_URL}/get_match",
                params={"tg_id": tg_id},
                timeout=10.0,
            )
            data = response.json()
        except Exception as e:
            logging.error(f"Ошибка /get_match: {e}")
            await message.answer("Не удалось загрузить анкеты. Попробуй позже.")
            return

    if data.get("status") == "error":
        await message.answer(data.get("message", "Пока никого нет :("))
        return

    caption = (
        f"<b>{data['name']}, {data['age']}</b>\n"
        f"📍 {data['city']}\n\n"
        f"{data['bio']}"
    )

    await message.answer_photo(
        photo=data["photo_id"],
        caption=caption,
        parse_mode="HTML",
        reply_markup=_build_profile_kb(data["tg_id"]),
    )


@router.message(F.text.in_({"🔍 Смотреть анкеты", "Смотреть анкеты"}))
async def show_match(message: types.Message):
    await _fetch_and_show(message.from_user.id, message)


@router.callback_query(F.data.startswith("skip_"))
async def cb_skip(callback: types.CallbackQuery):
    skipped_tg_id = int(callback.data.split("_", 1)[1])

    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{config.BACKEND_URL}/skip",
                json={"from_tg_id": callback.from_user.id, "to_tg_id": skipped_tg_id},
                timeout=5.0,
            )
        except Exception as e:
            logging.error(f"Ошибка /skip: {e}")

    await callback.answer()
    await _fetch_and_show(callback.from_user.id, callback)


@router.callback_query(F.data.startswith("like_"))
async def cb_like(callback: types.CallbackQuery):
    liked_tg_id = int(callback.data.split("_", 1)[1])

    mutual = False
    match_created = False
    matched_profile = None
    actor_profile = None
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{config.BACKEND_URL}/like",
                json={"from_tg_id": callback.from_user.id, "to_tg_id": liked_tg_id},
                timeout=5.0,
            )
            result = resp.json()
            mutual = result.get("mutual", False)
            match_created = result.get("match_created", False)
            matched_profile = result.get("matched_profile")
            actor_profile = result.get("actor_profile")
        except Exception as e:
            logging.error(f"Ошибка /like: {e}")
            await callback.answer("Не удалось отправить лайк.", show_alert=True)
            return

    if result.get("status") == "already_liked":
        await callback.answer("Ты уже ставил(а) лайк этой анкете.")
    elif mutual:
        await callback.answer("🎉 Взаимный лайк! Вы понравились друг другу!", show_alert=True)
        if match_created:
            partner_name = (matched_profile or {}).get("name") or "Новый мэтч"
            my_name = (actor_profile or {}).get("name") or callback.from_user.first_name or "Кто-то"

            try:
                await callback.message.bot.send_message(
                    callback.from_user.id,
                    f"🎉 У вас мэтч с {partner_name}! Теперь можете продолжить общение.",
                )
                await callback.message.bot.send_message(
                    liked_tg_id,
                    f"🎉 У вас мэтч с {my_name}! Открой бота, чтобы продолжить общение.",
                )
            except Exception as e:
                logging.error(f"Ошибка отправки взаимного уведомления: {e}")
    else:
        await callback.answer("❤️ Лайк отправлен!")

    await _fetch_and_show(callback.from_user.id, callback)
