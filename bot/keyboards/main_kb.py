from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram import types


def main_kb():
    builder = ReplyKeyboardBuilder()
    builder.row(
        types.KeyboardButton(text="👤 Моя анкета"),
        types.KeyboardButton(text="🔍 Смотреть анкеты"),
    )
    builder.row(types.KeyboardButton(text="⚙️ Настройки"))
    return builder.as_markup(resize_keyboard=True)
