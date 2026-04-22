import httpx
import logging
from aiogram import Router, types
from aiogram.filters import CommandStart
from keyboards.main_kb import main_kb
from config import config

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{config.BACKEND_URL}/register",
                params={
                    "tg_id": message.from_user.id,
                    "username": message.from_user.username,
                    "first_name": message.from_user.first_name
                },
                timeout=5.0
            )
        except Exception as e:
            logging.error(f"Ошибка регистрации при старте: {e}")

    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Добро пожаловать в <b>Club Flub</b>.\n"
        "Заполни анкету и начни знакомиться!",
        parse_mode="HTML",
        reply_markup=main_kb()
    )