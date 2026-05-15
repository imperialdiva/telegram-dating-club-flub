import logging

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from api import backend
from keyboards.main_kb import main_kb
from keyboards.profile_kb import gender_pref_kb
from services.format import format_boost_info
from states.profile import PreferencesEdit


router = Router()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# keyboards
# ---------------------------------------------------------------------------
def _settings_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="✏️ Редактировать анкету", callback_data="edit_profile"))
    kb.row(types.InlineKeyboardButton(text="🎯 Изменить предпочтения", callback_data="edit_prefs"))
    kb.row(types.InlineKeyboardButton(text="🚀 Мой буст", callback_data="boost_status"))
    kb.row(types.InlineKeyboardButton(text="👥 Реферальная ссылка", callback_data="ref_link"))
    kb.row(types.InlineKeyboardButton(text="🗑️ Удалить анкету", callback_data="delete_profile_ask"))
    return kb.as_markup()


def _confirm_delete_kb() -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="✅ Да, удалить", callback_data="delete_profile_confirm"),
        types.InlineKeyboardButton(text="❌ Отмена", callback_data="delete_profile_cancel"),
    )
    return kb.as_markup()


def _boost_kb(can_claim: bool) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if can_claim:
        kb.row(
            types.InlineKeyboardButton(
                text="🚀 Получить дневной буст ×1.3",
                callback_data="boost_claim_daily",
            )
        )
    else:
        kb.row(
            types.InlineKeyboardButton(
                text="⏳ Дневной буст уже получен",
                callback_data="boost_claim_locked",
            )
        )
    return kb.as_markup()


# ---------------------------------------------------------------------------
# entry
# ---------------------------------------------------------------------------
@router.message(F.text == "⚙️ Настройки")
async def show_settings(message: types.Message):
    await message.answer(
        "<b>Настройки</b>\n\nЧто хочешь сделать?",
        parse_mode="HTML",
        reply_markup=_settings_kb(),
    )


# ---------------------------------------------------------------------------
# boosts
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "boost_status")
async def show_boost(callback: types.CallbackQuery):
    await callback.answer()
    try:
        info = await backend.get_boost(callback.from_user.id)
    except Exception:
        logger.exception("get_boost failed")
        await callback.message.answer("Не удалось загрузить статус буста.")
        return
    can_claim = int(info.get("daily_boost_cooldown") or 0) <= 0
    await callback.message.answer(
        format_boost_info(info),
        parse_mode="HTML",
        reply_markup=_boost_kb(can_claim),
    )


@router.callback_query(F.data == "boost_claim_locked")
async def boost_claim_locked(callback: types.CallbackQuery):
    await callback.answer("Дневной буст уже получен — приходи завтра.", show_alert=True)


@router.callback_query(F.data == "boost_claim_daily")
async def boost_claim_daily(callback: types.CallbackQuery):
    try:
        info = await backend.claim_daily_boost(callback.from_user.id)
    except Exception:
        logger.exception("claim_daily_boost failed")
        await callback.answer("Не удалось получить буст.", show_alert=True)
        return

    if info.get("status") == "already_claimed":
        await callback.answer("Сегодня уже получал буст.", show_alert=True)
    else:
        await callback.answer("🚀 Буст активирован!", show_alert=True)

    can_claim = int(info.get("daily_boost_cooldown") or 0) <= 0
    text = format_boost_info(info)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_boost_kb(can_claim))
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=_boost_kb(can_claim))


# ---------------------------------------------------------------------------
# referral link
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "ref_link")
async def show_ref_link(callback: types.CallbackQuery):
    me = callback.from_user
    bot = await callback.message.bot.get_me()
    url = f"https://t.me/{bot.username}?start=ref_{me.id}"
    await callback.answer()
    await callback.message.answer(
        "<b>Твоя реферальная ссылка</b>\n"
        f"<code>{url}</code>\n\n"
        "За каждого, кто запустит бота по ссылке, ты получишь +балл к рейтингу "
        "и буст ×1.5 на 24 часа.",
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "delete_profile_ask")
async def delete_profile_ask(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "⚠️ Ты уверен, что хочешь удалить анкету?\n"
        "Все данные и фото будут удалены безвозвратно.",
        reply_markup=_confirm_delete_kb(),
    )


@router.callback_query(F.data == "delete_profile_cancel")
async def delete_profile_cancel(callback: types.CallbackQuery):
    await callback.answer("Отмена.")
    try:
        await callback.message.delete()
    except Exception:
        pass


@router.callback_query(F.data == "delete_profile_confirm")
async def delete_profile_confirm(callback: types.CallbackQuery):
    try:
        status, _ = await backend.delete_profile(callback.from_user.id)
    except Exception:
        logger.exception("Ошибка удаления профиля")
        await callback.answer("Ошибка при удалении. Попробуй позже.", show_alert=True)
        return

    if status == 404:
        await callback.answer("Анкета не найдена.", show_alert=True)
        return

    await callback.answer("Анкета удалена.")
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        "Анкета удалена. Ты можешь создать новую в любой момент.",
        reply_markup=main_kb(),
    )


# ---------------------------------------------------------------------------
# preferences (FSM)
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "edit_prefs")
async def edit_preferences(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.answer("Кто тебе интересен?", reply_markup=gender_pref_kb())
    await state.set_state(PreferencesEdit.gender)


@router.message(PreferencesEdit.gender)
async def prefs_gender(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    pref_gender = None if text.lower() == "любой" else text
    if pref_gender and pref_gender not in {"Мужской", "Женский"}:
        return await message.answer("Выбери из кнопок.", reply_markup=gender_pref_kb())

    await state.update_data(preferred_gender=pref_gender or "")
    await message.answer(
        "Город для поиска (можно «-» чтобы убрать):",
        reply_markup=types.ReplyKeyboardRemove(),
    )
    await state.set_state(PreferencesEdit.city)


@router.message(PreferencesEdit.city)
async def prefs_city(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    city = "" if text in {"-", ""} else text[:60]
    await state.update_data(preferred_city=city)
    await message.answer(
        "Возрастной диапазон в формате <code>18-30</code>:", parse_mode="HTML"
    )
    await state.set_state(PreferencesEdit.age_range)


@router.message(PreferencesEdit.age_range)
async def prefs_age(message: types.Message, state: FSMContext):
    text = (message.text or "").strip().replace(" ", "")
    if "-" not in text:
        return await message.answer("Формат: 18-30")
    a, b = text.split("-", 1)
    if not (a.isdigit() and b.isdigit()):
        return await message.answer("Введи числа, например 18-30.")
    age_min, age_max = int(a), int(b)
    if not (18 <= age_min <= 120 and 18 <= age_max <= 120):
        return await message.answer("Возраст должен быть от 18 до 120.")

    data = await state.get_data()
    payload = {
        "tg_id": message.from_user.id,
        "preferred_gender": data.get("preferred_gender") or None,
        "preferred_city": data.get("preferred_city") or None,
        "preferred_age_min": age_min,
        "preferred_age_max": age_max,
    }
    try:
        await backend.update_preferences(payload)
    except Exception:
        logger.exception("update_preferences failed")
        await message.answer("Не удалось сохранить настройки.", reply_markup=main_kb())
        await state.clear()
        return

    await state.clear()
    await message.answer("✅ Предпочтения сохранены.", reply_markup=main_kb())
