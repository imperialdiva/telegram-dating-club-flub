from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def gender_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Мужчина"), KeyboardButton(text="Женщина")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )