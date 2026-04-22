from aiogram.fsm.state import StatesGroup, State

class ProfileRegistration(StatesGroup):
    name = State()
    age = State()
    gender = State()
    photo = State()