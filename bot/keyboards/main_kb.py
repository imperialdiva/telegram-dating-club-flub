from aiogram import types
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def main_kb():
    builder = ReplyKeyboardBuilder()
    builder.row(
        types.KeyboardButton(text="👤 Моя анкета"),
        types.KeyboardButton(text="🔍 Смотреть анкеты"),
    )
    builder.row(
        types.KeyboardButton(text="💞 Мои мэтчи"),
        types.KeyboardButton(text="⚙️ Настройки"),
    )
    return builder.as_markup(resize_keyboard=True)
