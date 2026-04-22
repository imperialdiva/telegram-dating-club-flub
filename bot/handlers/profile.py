import logging
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from states.profile import ProfileRegistration
from keyboards.profile_kb import gender_kb
from keyboards.main_kb import main_kb
import httpx
from config import config

router = Router()

VALID_GENDERS = {"Мужской", "Женский"}


async def _begin_registration(target: types.Message | types.CallbackQuery, state: FSMContext):
    if isinstance(target, types.CallbackQuery):
        await target.answer()
        msg = target.message
    else:
        msg = target
    await msg.answer("Как тебя зовут?", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(ProfileRegistration.name)


@router.message(F.text == "Заполнить анкету")
async def start_registration_text(message: types.Message, state: FSMContext):
    await _begin_registration(message, state)


@router.callback_query(F.data == "edit_profile")
async def start_registration_callback(callback: types.CallbackQuery, state: FSMContext):
    await _begin_registration(callback, state)


@router.message(ProfileRegistration.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Сколько тебе лет?")
    await state.set_state(ProfileRegistration.age)


@router.message(ProfileRegistration.age)
async def process_age(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or not (14 <= int(message.text) <= 99):
        return await message.answer("Введи корректный возраст (от 14 до 99).")

    await state.update_data(age=int(message.text))
    await message.answer("Из какого ты города?")
    await state.set_state(ProfileRegistration.city)


@router.message(ProfileRegistration.city)
async def process_city(message: types.Message, state: FSMContext):
    await state.update_data(city=message.text)
    await message.answer("Расскажи немного о себе (пару предложений):")
    await state.set_state(ProfileRegistration.bio)


@router.message(ProfileRegistration.bio)
async def process_bio(message: types.Message, state: FSMContext):
    await state.update_data(bio=message.text)
    await message.answer("Выбери свой пол:", reply_markup=gender_kb())
    await state.set_state(ProfileRegistration.gender)


@router.message(ProfileRegistration.gender)
async def process_gender(message: types.Message, state: FSMContext):
    if message.text not in VALID_GENDERS:
        return await message.answer(
            "Пожалуйста, выбери пол с помощью кнопок ниже.",
            reply_markup=gender_kb()
        )

    await state.update_data(gender=message.text)
    await message.answer(
        "Отправь своё фото.",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(ProfileRegistration.photo)


@router.message(ProfileRegistration.photo, ~F.photo)
async def process_photo_wrong(message: types.Message):
    await message.answer("Пожалуйста, отправь именно фото, а не файл или текст.")


@router.message(ProfileRegistration.photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    photo_id = message.photo[-1].file_id

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{config.BACKEND_URL}/update_profile",
                json={
                    "tg_id": message.from_user.id,
                    "name": user_data["name"],
                    "age": user_data["age"],
                    "city": user_data.get("city"),
                    "bio": user_data.get("bio"),
                    "gender": user_data["gender"],
                    "photo_id": photo_id
                }
            )
            resp.raise_for_status()
            await message.answer(
                "✅ Анкета сохранена! Теперь можешь смотреть анкеты других.",
                reply_markup=main_kb()
            )
        except Exception as e:
            logging.error(f"Ошибка сохранения профиля: {e}")
            await message.answer(
                "Ошибка при сохранении. Попробуй позже.",
                reply_markup=main_kb()
            )

    await state.clear()
