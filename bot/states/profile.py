from aiogram.fsm.state import State, StatesGroup


class ProfileRegistration(StatesGroup):
    name = State()
    age = State()
    city = State()
    bio = State()
    gender = State()
    interests = State()
    photo = State()
    extra_photos = State()


class PreferencesEdit(StatesGroup):
    gender = State()
    city = State()
    age_range = State()
