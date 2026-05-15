"""Тонкий клиент над backend REST API."""
import logging
from typing import Any, Optional

import httpx

from config import config


logger = logging.getLogger(__name__)


class Backend:
    def __init__(self, base_url: str, timeout: float = 10.0):
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    async def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout)

    async def register(
        self,
        tg_id: int,
        username: Optional[str],
        first_name: Optional[str],
        referrer_tg_id: Optional[int] = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"tg_id": tg_id}
        if username:
            params["username"] = username
        if first_name:
            params["first_name"] = first_name
        if referrer_tg_id:
            params["referrer_tg_id"] = referrer_tg_id
        async with await self._client() as client:
            resp = await client.post(f"{self._base}/register", params=params)
            return resp.json()

    async def update_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with await self._client() as client:
            resp = await client.post(f"{self._base}/update_profile", json=payload)
            return resp.json()

    async def update_preferences(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with await self._client() as client:
            resp = await client.patch(f"{self._base}/preferences", json=payload)
            return resp.json()

    async def get_profile(self, tg_id: int) -> Optional[dict[str, Any]]:
        async with await self._client() as client:
            resp = await client.get(f"{self._base}/profile/{tg_id}")
            if resp.status_code == 404:
                return None
            return resp.json()

    async def delete_profile(self, tg_id: int) -> tuple[int, dict[str, Any]]:
        async with await self._client() as client:
            resp = await client.delete(f"{self._base}/profile/{tg_id}")
            try:
                body = resp.json()
            except Exception:
                body = {}
            return resp.status_code, body

    async def upload_photo(
        self, tg_id: int, blob: bytes, filename: str = "photo.jpg",
        content_type: str = "image/jpeg",
    ) -> dict[str, Any]:
        async with await self._client() as client:
            resp = await client.post(
                f"{self._base}/profile/{tg_id}/photos",
                files={"file": (filename, blob, content_type)},
            )
            return resp.json()

    async def delete_photo(self, tg_id: int, index: int) -> dict[str, Any]:
        async with await self._client() as client:
            resp = await client.delete(f"{self._base}/profile/{tg_id}/photos/{index}")
            return resp.json()

    async def next_match(self, tg_id: int) -> dict[str, Any]:
        async with await self._client() as client:
            resp = await client.get(f"{self._base}/get_match", params={"tg_id": tg_id})
            return resp.json()

    async def like(self, from_tg_id: int, to_tg_id: int) -> dict[str, Any]:
        async with await self._client() as client:
            resp = await client.post(
                f"{self._base}/like",
                json={"from_tg_id": from_tg_id, "to_tg_id": to_tg_id},
            )
            return resp.json()

    async def skip(self, from_tg_id: int, to_tg_id: int) -> dict[str, Any]:
        async with await self._client() as client:
            await client.post(
                f"{self._base}/skip",
                json={"from_tg_id": from_tg_id, "to_tg_id": to_tg_id},
            )

    async def list_matches(self, tg_id: int) -> dict[str, Any]:
        async with await self._client() as client:
            resp = await client.get(f"{self._base}/matches/{tg_id}")
            return resp.json()

    async def dialog_started(self, from_tg_id: int, to_tg_id: int) -> dict[str, Any]:
        async with await self._client() as client:
            resp = await client.post(
                f"{self._base}/matches/dialog-started",
                json={"from_tg_id": from_tg_id, "to_tg_id": to_tg_id},
            )
            return resp.json()

    async def get_boost(self, tg_id: int) -> dict[str, Any]:
        async with await self._client() as client:
            resp = await client.get(f"{self._base}/boost/{tg_id}")
            return resp.json()

    async def claim_daily_boost(self, tg_id: int) -> dict[str, Any]:
        async with await self._client() as client:
            resp = await client.post(f"{self._base}/boost/{tg_id}/claim-daily")
            return resp.json()


backend = Backend(config.BACKEND_URL)
