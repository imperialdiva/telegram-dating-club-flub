from fastapi import APIRouter

from storage import MINIO_BUCKET


router = APIRouter()


@router.get("/")
async def health_check():
    return {"status": "ok", "bucket": MINIO_BUCKET}
