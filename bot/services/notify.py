"""Уведомления о мэтче и старте диалога."""
import logging

from aiogram import Bot, types
from aiogram.utils.keyboard import InlineKeyboardBuilder


logger = logging.getLogger(__name__)


def _msg_kb(partner_id: int) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="💬 Написать первым", callback_data=f"msg_{partner_id}"
        )
    )
    return kb.as_markup()


async def notify_match(
    bot: Bot,
    actor_tg_id: int,
    actor_name: str,
    partner_tg_id: int,
    partner_name: str,
) -> None:
    """Послать обоим участникам уведомление о мэтче с кнопкой 'Написать первым'."""
    try:
        await bot.send_message(
            actor_tg_id,
            f"🎉 У вас мэтч с <b>{partner_name}</b>! Ты можешь написать первым.",
            parse_mode="HTML",
            reply_markup=_msg_kb(partner_tg_id),
        )
        await bot.send_message(
            partner_tg_id,
            f"🎉 У вас мэтч с <b>{actor_name}</b>! Открой бота и напиши первым.",
            parse_mode="HTML",
            reply_markup=_msg_kb(actor_tg_id),
        )
    except Exception:
        logger.exception("Не удалось отправить уведомление о мэтче")


async def notify_dialog_started(
    bot: Bot, actor: types.User, partner_tg_id: int
) -> None:
    deep_link = (
        f"https://t.me/{actor.username}"
        if actor.username
        else f"tg://user?id={actor.id}"
    )
    try:
        await bot.send_message(
            partner_tg_id,
            f"💬 <b>{actor.first_name or 'Кто-то'}</b> хочет начать диалог!\n"
            f"Открой профиль: {deep_link}",
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Не удалось уведомить партнёра о диалоге")
