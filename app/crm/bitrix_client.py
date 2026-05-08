"""Клиент к входящим вебхукам Bitrix24 с ретраями.

Дедуп FR-6.2: ищем существующую сделку через локальную SQLite-таблицу `deals` (см. state.repository).
Здесь — только сетевая часть.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from loguru import logger

from app.config import settings

HTTP_TIMEOUT = 20.0
MAX_RETRIES = 3


class BitrixError(RuntimeError):
    pass


class BitrixClient:
    def __init__(self) -> None:
        self.base = settings.bitrix_webhook_url.rstrip("/")

    async def _call(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self.base}/{method}.json"
        last_err: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                    r = await client.post(url, json=payload or {})
                if r.status_code != 200:
                    raise BitrixError(f"{method} HTTP {r.status_code}: {r.text[:200]}")
                data = r.json()
                if "error" in data:
                    raise BitrixError(f"{method} error: {data.get('error')} {data.get('error_description')}")
                return data.get("result")
            except Exception as e:
                last_err = e
                wait = 2**attempt
                logger.warning("Bitrix {} attempt {} failed: {}; retry in {}s", method, attempt + 1, e, wait)
                await asyncio.sleep(wait)
        assert last_err is not None
        raise last_err

    async def find_contact_by_phone(self, phone: str) -> str | None:
        result = await self._call(
            "crm.contact.list",
            {"filter": {"PHONE": phone}, "select": ["ID"]},
        )
        if isinstance(result, list) and result:
            return str(result[0].get("ID"))
        return None

    async def add_contact(self, payload: dict) -> str:
        result = await self._call("crm.contact.add", payload)
        return str(result)

    async def add_deal(self, payload: dict) -> str:
        result = await self._call("crm.deal.add", payload)
        return str(result)

    async def update_deal(self, deal_id: str, payload: dict) -> bool:
        result = await self._call("crm.deal.update", {"id": deal_id, **payload})
        return bool(result)

    def deal_url(self, deal_id: str) -> str:
        # base вида https://portal.bitrix24.ru/rest/1/abcdef/
        portal = self.base.split("/rest/")[0]
        return f"{portal}/crm/deal/details/{deal_id}/"


bitrix = BitrixClient()
