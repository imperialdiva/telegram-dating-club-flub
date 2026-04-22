from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from states.profile import ProfileRegistration
from keyboards.profile_kb import gender_kb
import httpx
from config import config

router = Router()

@router.message(F.text == "Создать анкету")
async def start_registration(message: types.Message, state: FSMContext):
    await message.answer("Как тебя зовут?")
    await state.set_state(ProfileRegistration.name)

@router.message(ProfileRegistration.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Сколько тебе лет?")
    await state.set_state(ProfileRegistration.age)

@router.message(ProfileRegistration.age)
async def process_age(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer(" Введи число, пожалуйста.")
    
    await state.update_data(age=int(message.text))
    await message.answer("Выбери свой пол:", reply_markup=gender_kb())
    await state.set_state(ProfileRegistration.gender)

@router.message(ProfileRegistration.gender)
async def process_gender(message: types.Message, state: FSMContext):
    await state.update_data(gender=message.text)
    await message.answer("Отправь свое фото.")
    await state.set_state(ProfileRegistration.photo)

@router.message(ProfileRegistration.photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    photo_id = message.photo[-1].file_id
    
    # Отправляем все данные на бэкенд
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{config.BACKEND_URL}/update_profile",
                json={
                    "tg_id": message.from_user.id,
                    "name": user_data['name'],
                    "age": user_data['age'],
                    "gender": user_data['gender'],
                    "photo_id": photo_id
                }
            )
            await message.answer("Анкета сохранена! Теперь мы подберем тебе пару.")
            await state.clear()
        except Exception as e:
            await message.answer("Ошибка при сохранении. Попробуй позже.")