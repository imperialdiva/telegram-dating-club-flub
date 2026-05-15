from aiogram import types
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def gender_kb():
    builder = ReplyKeyboardBuilder()
    builder.row(
        types.KeyboardButton(text="Мужской"),
        types.KeyboardButton(text="Женский"),
    )
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def gender_pref_kb():
    builder = ReplyKeyboardBuilder()
    builder.row(
        types.KeyboardButton(text="Мужской"),
        types.KeyboardButton(text="Женский"),
    )
    builder.row(types.KeyboardButton(text="Любой"))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def skip_kb(label: str = "Пропустить"):
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text=label))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def photos_done_kb():
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="Готово"))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)
