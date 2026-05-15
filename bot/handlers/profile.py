import io
import logging

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from api import backend
from keyboards.main_kb import main_kb
from keyboards.profile_kb import gender_kb, photos_done_kb, skip_kb
from states.profile import ProfileRegistration


router = Router()
logger = logging.getLogger(__name__)

VALID_GENDERS = {"Мужской", "Женский"}
MAX_PHOTOS = 5


# ---------------------------------------------------------------------------
# entry points
# ---------------------------------------------------------------------------
async def _begin_registration(target, state: FSMContext):
    if isinstance(target, types.CallbackQuery):
        await target.answer()
        msg = target.message
    else:
        msg = target
    await state.clear()
    await msg.answer("Как тебя зовут?", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(ProfileRegistration.name)


@router.message(F.text == "Заполнить анкету")
async def start_registration_text(message: types.Message, state: FSMContext):
    await _begin_registration(message, state)


@router.callback_query(F.data == "edit_profile")
async def start_registration_callback(callback: types.CallbackQuery, state: FSMContext):
    await _begin_registration(callback, state)


# ---------------------------------------------------------------------------
# FSM steps
# ---------------------------------------------------------------------------
@router.message(ProfileRegistration.name)
async def process_name(message: types.Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name or len(name) > 50:
        return await message.answer("Имя должно быть от 1 до 50 символов.")
    await state.update_data(name=name)
    await message.answer("Сколько тебе лет?")
    await state.set_state(ProfileRegistration.age)


@router.message(ProfileRegistration.age)
async def process_age(message: types.Message, state: FSMContext):
    if not (message.text or "").isdigit() or not (14 <= int(message.text) <= 99):
        return await message.answer("Введи корректный возраст (от 14 до 99).")
    await state.update_data(age=int(message.text))
    await message.answer("Из какого ты города?")
    await state.set_state(ProfileRegistration.city)


@router.message(ProfileRegistration.city)
async def process_city(message: types.Message, state: FSMContext):
    city = (message.text or "").strip()[:60]
    await state.update_data(city=city)
    await message.answer("Расскажи немного о себе (пару предложений):")
    await state.set_state(ProfileRegistration.bio)


@router.message(ProfileRegistration.bio)
async def process_bio(message: types.Message, state: FSMContext):
    bio = (message.text or "").strip()[:500]
    await state.update_data(bio=bio)
    await message.answer("Выбери свой пол:", reply_markup=gender_kb())
    await state.set_state(ProfileRegistration.gender)


@router.message(ProfileRegistration.gender)
async def process_gender(message: types.Message, state: FSMContext):
    if message.text not in VALID_GENDERS:
        return await message.answer(
            "Пожалуйста, выбери пол с помощью кнопок ниже.",
            reply_markup=gender_kb(),
        )
    await state.update_data(gender=message.text)
    await message.answer(
        "Перечисли свои интересы через запятую (до 10 штук). Например: <i>музыка, спорт, кино, путешествия</i>.\n\n"
        "Можно нажать «Пропустить».",
        parse_mode="HTML",
        reply_markup=skip_kb(),
    )
    await state.set_state(ProfileRegistration.interests)


@router.message(ProfileRegistration.interests)
async def process_interests(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    interests: list[str] = []
    if text and text.lower() != "пропустить":
        interests = [
            piece.strip().lower()
            for piece in text.replace(";", ",").split(",")
            if piece.strip()
        ][:10]
    await state.update_data(interests=interests)
    await message.answer(
        "Отправь своё фото (можно до 5 штук, по одному).",
        reply_markup=types.ReplyKeyboardRemove(),
    )
    await state.set_state(ProfileRegistration.photo)


@router.message(ProfileRegistration.photo, ~F.photo)
async def process_photo_wrong(message: types.Message):
    await message.answer("Пожалуйста, отправь именно фото, а не файл или текст.")


@router.message(ProfileRegistration.photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    tg_id = message.from_user.id

    profile_payload = {
        "tg_id": tg_id,
        "name": user_data["name"],
        "age": user_data["age"],
        "city": user_data.get("city"),
        "bio": user_data.get("bio"),
        "gender": user_data["gender"],
        "interests": user_data.get("interests") or [],
        "photo_id": message.photo[-1].file_id,
    }

    try:
        await backend.update_profile(profile_payload)
    except Exception as exc:
        logger.exception("Ошибка сохранения профиля")
        await message.answer(
            "Ошибка при сохранении. Попробуй позже.",
            reply_markup=main_kb(),
        )
        await state.clear()
        return

    uploaded = await _upload_photo_to_minio(message, tg_id)

    await state.update_data(photos_uploaded=1 if uploaded else 0)
    await message.answer(
        "✅ Анкета сохранена. Можешь добавить ещё фото (до 5) или нажми «Готово».",
        reply_markup=photos_done_kb(),
    )
    await state.set_state(ProfileRegistration.extra_photos)


@router.message(ProfileRegistration.extra_photos, F.text == "Готово")
async def finish_extra_photos(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Анкета готова! Используй меню, чтобы смотреть других.",
        reply_markup=main_kb(),
    )


@router.message(ProfileRegistration.extra_photos, F.photo)
async def process_extra_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uploaded = int(data.get("photos_uploaded", 0))
    if uploaded >= MAX_PHOTOS:
        await message.answer(
            f"Лимит {MAX_PHOTOS} фото достигнут.",
            reply_markup=photos_done_kb(),
        )
        return

    success = await _upload_photo_to_minio(message, message.from_user.id)
    if success:
        uploaded += 1
        await state.update_data(photos_uploaded=uploaded)
        await message.answer(
            f"Загружено фото {uploaded}/{MAX_PHOTOS}. Ещё или «Готово»?",
            reply_markup=photos_done_kb(),
        )
    else:
        await message.answer("Не удалось загрузить фото. Попробуй ещё раз.")


@router.message(ProfileRegistration.extra_photos)
async def process_extra_photo_wrong(message: types.Message):
    await message.answer(
        "Отправь фото или нажми «Готово».",
        reply_markup=photos_done_kb(),
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
async def _upload_photo_to_minio(message: types.Message, tg_id: int) -> bool:
    try:
        photo = message.photo[-1]
        bot = message.bot
        file = await bot.get_file(photo.file_id)
        buf = io.BytesIO()
        await bot.download_file(file.file_path, destination=buf)
        buf.seek(0)
        result = await backend.upload_photo(
            tg_id=tg_id,
            blob=buf.read(),
            filename=f"{photo.file_id}.jpg",
            content_type="image/jpeg",
        )
        return result.get("status") == "success"
    except Exception:
        logger.exception("Не удалось загрузить фото в MinIO")
        return False
