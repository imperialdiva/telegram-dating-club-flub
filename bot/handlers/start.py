import httpx
import logging
from aiogram import Router, types
from aiogram.filters import CommandStart
from config import config

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer("Регистрирую тебя в системе...")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{config.BACKEND_URL}/register",
                params={
                    "tg_id": message.from_user.id, 
                    "username": message.from_user.username,
                    "first_name": message.from_user.first_name
                }
            )
            if response.status_code == 200:
                res_data = response.json()
                if res_data.get("status") == "success":
                    await message.answer("Готово! Ты в базе.")
                else:
                    await message.answer("Ты уже был зарегистрирован ранее.")
            else:
                await message.answer("Ошибка бэкенда.")
        except Exception as e:
            logging.error(f"Ошибка связи: {e}")
            await message.answer("Бэкенд недоступен.")