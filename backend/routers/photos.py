import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from cache import delete_queue
from config import MAX_PHOTO_BYTES, MAX_PHOTOS_PER_USER
from db import AsyncSessionLocal
from services.profiles import bump_activity, get_user_or_none
from storage import delete_photo, ensure_bucket, public_url, upload_photo
from tasks import schedule_recalculate_user_rating


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/profile/{tg_id}/photos")
async def upload_user_photo(tg_id: int, file: UploadFile = File(...)):
    blob = await file.read()
    if not blob:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(blob) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="File too large (>8MB)")

    async with AsyncSessionLocal() as session:
        user = await get_user_or_none(session, tg_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        try:
            ensure_bucket()
            key = upload_photo(tg_id, blob, file.content_type or "image/jpeg")
        except Exception as exc:
            logger.exception("Photo upload failed")
            raise HTTPException(status_code=500, detail=f"Storage error: {exc}")

        photos = list(user.photos or [])
        photos.append(key)
        user.photos = photos[:MAX_PHOTOS_PER_USER]
        if not user.photo_id:
            user.photo_id = key
        await bump_activity(session, tg_id)
        await session.commit()

    schedule_recalculate_user_rating(tg_id)
    await delete_queue(tg_id)
    return {
        "status": "success",
        "key": key,
        "url": public_url(key),
        "photos": list(user.photos or []),
    }


@router.delete("/profile/{tg_id}/photos/{index}")
async def delete_user_photo(tg_id: int, index: int):
    async with AsyncSessionLocal() as session:
        user = await get_user_or_none(session, tg_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        photos = list(user.photos or [])
        if index < 0 or index >= len(photos):
            raise HTTPException(status_code=404, detail="Photo not found")

        key = photos.pop(index)
        user.photos = photos
        if user.photo_id == key:
            user.photo_id = photos[0] if photos else None
        await session.commit()

    delete_photo(key)
    schedule_recalculate_user_rating(tg_id)
    await delete_queue(tg_id)
    return {"status": "success", "photos": photos}
