from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram import types

def gender_kb():
    builder = ReplyKeyboardBuilder()
    builder.row(
        types.KeyboardButton(text="Мужской"),
        types.KeyboardButton(text="Женский")
    )
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)