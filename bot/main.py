import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import config
from handlers import start  # Импортируем наш файл с обработчиками

async def main():
    logging.basicConfig(level=logging.INFO)
    
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()

    # Подключаем роутер из handlers/start.py
    dp.include_router(start.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())