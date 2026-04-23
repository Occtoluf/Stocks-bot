from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx

from .db import Dividend, Security

log = logging.getLogger(__name__)

ISS_BASE = "https://iss.moex.com/iss"
GOLD_SECID = "GLDRUB_TOM"


def _rows_from_block(payload: dict[str, Any], block: str) -> list[dict[str, Any]]:
    """Convert ISS block ({columns:[...], data:[[...], ...]}) into list of dicts."""
    section = payload.get(block) or {}
    columns: list[str] = section.get("columns") or []
    data: list[list[Any]] = section.get("data") or []
    return [dict(zip(columns, row)) for row in data]


class MoexClient:
    def __init__(self, base_url: str = ISS_BASE, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "MoexClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    async def fetch_shares(self) -> list[Security]:
        """Список акций с основного режима TQBR."""
        payload = await self._get(
            "/engines/stock/markets/shares/boards/TQBR/securities.json",
            params={"iss.meta": "off"},
        )
        rows = _rows_from_block(payload, "securities")
        out: list[Security] = []
        for row in rows:
            secid = row.get("SECID")
            if not secid:
                continue
            out.append(
                Security(
                    secid=secid,
                    shortname=row.get("SHORTNAME") or secid,
                    secname=row.get("SECNAME") or secid,
                    board=row.get("BOARDID") or "TQBR",
                    type="share",
                )
            )
        return out

    async def fetch_gold(self) -> Security | None:
        """Тикер GLDRUB_TOM с валютного рынка."""
        payload = await self._get(
            "/engines/currency/markets/selt/securities.json",
            params={"iss.meta": "off"},
        )
        rows = _rows_from_block(payload, "securities")
        for row in rows:
            if row.get("SECID") == GOLD_SECID:
                return Security(
                    secid=GOLD_SECID,
                    shortname=row.get("SHORTNAME") or "Золото",
                    secname=row.get("SECNAME") or "Золото расчётами TOM",
                    board=row.get("BOARDID") or "CETS",
                    type="currency",
                )
        return Security(
            secid=GOLD_SECID,
            shortname="Золото",
            secname="Золото расчётами TOM",
            board="CETS",
            type="currency",
        )

    async def fetch_all_securities(self) -> list[Security]:
        shares = await self.fetch_shares()
        gold = await self.fetch_gold()
        if gold is not None:
            shares.append(gold)
        return shares

    async def fetch_dividends(self, secid: str) -> list[Dividend]:
        try:
            payload = await self._get(
                f"/securities/{secid}/dividends.json",
                params={"iss.meta": "off"},
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            raise
        rows = _rows_from_block(payload, "dividends")
        out: list[Dividend] = []
        for row in rows:
            raw_date = row.get("registryclosedate") or row.get("REGISTRYCLOSEDATE")
            # MOEX ISS uses "dividendnetperms" (net per share), not "value"
            _KEYS = ["dividendnetperms", "DIVIDENDNETPERMS", "value", "VALUE"]
            value = next(
                (row[k] for k in _KEYS if k in row and row[k] is not None),
                None,
            )
            currency = row.get("currencyid") or row.get("CURRENCYID") or "RUB"
            if not raw_date or value is None:
                continue
            try:
                d = date.fromisoformat(str(raw_date)[:10])
            except ValueError:
                continue
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            out.append(Dividend(registry_close_date=d, value=v, currency=str(currency)))
        return out
