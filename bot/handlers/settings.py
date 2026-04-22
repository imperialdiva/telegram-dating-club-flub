import logging
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
import httpx
from config import config
from keyboards.main_kb import main_kb

router = Router()


def _settings_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✏️ Редактировать анкету", callback_data="edit_profile"))
    kb.row(types.InlineKeyboardButton(text="🗑️ Удалить анкету", callback_data="delete_profile_ask"))
    return kb.as_markup()


def _confirm_delete_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="✅ Да, удалить", callback_data="delete_profile_confirm"),
        types.InlineKeyboardButton(text="❌ Отмена", callback_data="delete_profile_cancel"),
    )
    return kb.as_markup()


@router.message(F.text == "⚙️ Настройки")
async def show_settings(message: types.Message):
    await message.answer(
        "<b>Настройки</b>\n\nЧто хочешь сделать?",
        parse_mode="HTML",
        reply_markup=_settings_kb(),
    )


@router.callback_query(F.data == "delete_profile_ask")
async def delete_profile_ask(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "⚠️ Ты уверен, что хочешь удалить анкету?\nВсе данные будут удалены безвозвратно.",
        reply_markup=_confirm_delete_kb(),
    )


@router.callback_query(F.data == "delete_profile_cancel")
async def delete_profile_cancel(callback: types.CallbackQuery):
    await callback.answer("Отмена.")
    await callback.message.delete()


@router.callback_query(F.data == "delete_profile_confirm")
async def delete_profile_confirm(callback: types.CallbackQuery):
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.delete(
                f"{config.BACKEND_URL}/profile/{callback.from_user.id}",
                timeout=5.0,
            )
        except Exception as e:
            logging.error(f"Ошибка удаления профиля: {e}")
            await callback.answer("Ошибка при удалении. Попробуй позже.", show_alert=True)
            return

    if resp.status_code == 404:
        await callback.answer("Анкета не найдена.", show_alert=True)
        return

    await callback.answer("Анкета удалена.")
    await callback.message.delete()
    await callback.message.answer(
        "Анкета удалена. Ты можешь создать новую в любой момент.",
        reply_markup=main_kb(),
    )
