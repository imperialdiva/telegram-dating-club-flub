import logging
from typing import Optional

from aiogram import Router, types
from aiogram.filters import Command, CommandObject, CommandStart

from api import backend
from keyboards.main_kb import main_kb


router = Router()


def _parse_referrer(args: Optional[str]) -> Optional[int]:
    if not args:
        return None
    token = args.strip()
    if token.startswith("ref_"):
        token = token[4:]
    if token.startswith("ref"):
        token = token[3:]
    if token.isdigit():
        return int(token)
    return None


@router.message(CommandStart(deep_link=True))
async def cmd_start_with_payload(message: types.Message, command: CommandObject):
    await _do_start(message, _parse_referrer(command.args))


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    await _do_start(message, None)


async def _do_start(message: types.Message, referrer_tg_id: Optional[int]):
    try:
        result = await backend.register(
            tg_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            referrer_tg_id=referrer_tg_id,
        )
    except Exception as exc:
        logging.error("Ошибка регистрации при /start: %s", exc)
        result = {}

    referral_note = ""
    if result.get("referrer_applied"):
        referral_note = "\n\n👥 Тебя пригласил друг — он получит +балл к рейтингу."

    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n\n"
        "Добро пожаловать в <b>Club Flub</b>.\n"
        "Заполни анкету и начни знакомиться!" + referral_note,
        parse_mode="HTML",
        reply_markup=main_kb(),
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "<b>Что я умею</b>\n\n"
        "👤 Моя анкета — посмотреть и редактировать профиль\n"
        "🔍 Смотреть анкеты — листать кандидатов и ставить лайки\n"
        "💞 Мои мэтчи — список взаимных лайков, начать переписку\n"
        "⚙️ Настройки — изменить предпочтения, реферальная ссылка, удалить анкету\n\n"
        "Команды: /start /profile /matches /settings /help",
        parse_mode="HTML",
        reply_markup=main_kb(),
    )


@router.message(Command("profile"))
async def cmd_profile(message: types.Message):
    await message.answer("Открой раздел «👤 Моя анкета».", reply_markup=main_kb())


@router.message(Command("matches"))
async def cmd_matches(message: types.Message):
    await message.answer("Открой раздел «💞 Мои мэтчи».", reply_markup=main_kb())


@router.message(Command("settings"))
async def cmd_settings(message: types.Message):
    await message.answer("Открой раздел «⚙️ Настройки».", reply_markup=main_kb())
