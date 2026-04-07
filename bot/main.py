import asyncio
import logging
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from os import getenv

TOKEN = "твой_токен"
BACKEND_URL = "http://localhost:8000/users/register"

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username

    # Отправляем данные на бэкенд
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                BACKEND_URL, 
                json={"telegram_id": tg_id, "username": username}
            )
            
            if response.status_code == 200:
                data = response.json()
                if data["status"] == "success":
                    await message.answer("Добро пожаловать в Dating Club! Вы успешно зарегистрированы.")
                else:
                    await message.answer("С возвращением!")
            else:
                await message.answer("Ошибка связи с сервером.")
        except Exception as e:
            logging.error(f"Error: {e}")
            await message.answer("Произошла ошибка при регистрации.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())