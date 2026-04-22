import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import config
from handlers import start, profile, search, my_profile, settings

async def main():
    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(my_profile.router)
    dp.include_router(settings.router)
    dp.include_router(profile.router)
    dp.include_router(search.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())