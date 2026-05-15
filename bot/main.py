import asyncio
import logging

from aiogram import Bot, Dispatcher

from config import config
from handlers import matches, my_profile, profile, search, settings, start
from middlewares import ThrottlingMiddleware


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )

    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()

    throttler = ThrottlingMiddleware(rate=0.4)
    dp.message.middleware(throttler)
    dp.callback_query.middleware(throttler)

    dp.include_router(start.router)
    dp.include_router(my_profile.router)
    dp.include_router(matches.router)
    dp.include_router(settings.router)
    dp.include_router(profile.router)
    dp.include_router(search.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
