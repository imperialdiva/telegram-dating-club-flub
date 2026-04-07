import os
import asyncio
import logging
import httpx
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

logging.basicConfig(level=logging.INFO)

raw_token = os.getenv("BOT_TOKEN")
TOKEN = raw_token.strip() if raw_token else None
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

if not TOKEN:
    raise ValueError("Token miss")

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    tg_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{BACKEND_URL}/register",
                params={"tg_id": tg_id, "username": username}
            )
            
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                
                if status == "success":
                    welcome_text = f"Привет, {full_name}! Регистрация прошла успешно"
                elif status == "already_exists":
                    welcome_text = f"С возвращением, {full_name}!"
                else:
                    welcome_text = f"Привет, {full_name}! Регистрация прошла успешно."
            else:
                logging.error(f"Back{response.status_code}")
                welcome_text = "bcak problem"
                
        except Exception as e:
            logging.error(f"back connection: {e}")
            welcome_text = "backend down but you here"

    await message.answer(welcome_text)

async def main():
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stop")