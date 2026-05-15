import logging
import os
import uuid
from typing import Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


logger = logging.getLogger(__name__)


MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_PUBLIC_ENDPOINT = os.getenv("MINIO_PUBLIC_ENDPOINT", "http://localhost:9000")
MINIO_ROOT_USER = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_ROOT_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "photos")
MINIO_REGION = os.getenv("MINIO_REGION", "us-east-1")


def _client(endpoint: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=MINIO_ROOT_USER,
        aws_secret_access_key=MINIO_ROOT_PASSWORD,
        config=Config(signature_version="s3v4"),
        region_name=MINIO_REGION,
    )


def _internal_client():
    return _client(MINIO_ENDPOINT)


def ensure_bucket() -> None:
    s3 = _internal_client()
    try:
        s3.head_bucket(Bucket=MINIO_BUCKET)
    except ClientError:
        try:
            s3.create_bucket(Bucket=MINIO_BUCKET)
            logger.info("Created MinIO bucket: %s", MINIO_BUCKET)
        except ClientError as exc:
            logger.warning("Could not ensure bucket %s: %s", MINIO_BUCKET, exc)


def upload_photo(tg_id: int, data: bytes, content_type: str = "image/jpeg") -> str:
    extension = "jpg"
    if content_type and "/" in content_type:
        guessed = content_type.split("/", 1)[1]
        if guessed in {"jpeg", "jpg", "png", "webp"}:
            extension = "jpg" if guessed == "jpeg" else guessed
    key = f"users/{tg_id}/{uuid.uuid4().hex}.{extension}"
    s3 = _internal_client()
    s3.put_object(
        Bucket=MINIO_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type or "image/jpeg",
    )
    return key


def public_url(key: str) -> str:
    if not key:
        return ""
    return f"{MINIO_PUBLIC_ENDPOINT.rstrip('/')}/{MINIO_BUCKET}/{key}"


def presigned_url(key: str, expires: int = 3600) -> Optional[str]:
    if not key:
        return None
    s3 = _client(MINIO_PUBLIC_ENDPOINT)
    try:
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": MINIO_BUCKET, "Key": key},
            ExpiresIn=expires,
        )
    except ClientError as exc:
        logger.warning("presigned_url failed for %s: %s", key, exc)
        return None


def delete_photo(key: str) -> None:
    if not key:
        return
    s3 = _internal_client()
    try:
        s3.delete_object(Bucket=MINIO_BUCKET, Key=key)
    except ClientError as exc:
        logger.warning("delete_photo failed for %s: %s", key, exc)
