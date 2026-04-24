from __future__ import annotations

import logging
from datetime import date, datetime, time, timezone
from typing import Any

import httpx

from .db import Dividend, Security

log = logging.getLogger(__name__)

TBANK_BASE = "https://invest-public-api.tinkoff.ru/rest"
_SERVICE = "tinkoff.public.invest.api.contract.v1.InstrumentsService"


def _quotation_to_float(q: dict[str, Any] | None) -> float:
    if not q:
        return 0.0
    units = int(q.get("units") or 0)
    nano = int(q.get("nano") or 0)
    return units + nano / 1e9


def _parse_iso_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _date_to_tbank(d: date) -> str:
    return datetime.combine(d, time.min, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TBankAuthError(RuntimeError):
    pass


class TBankClient:
    """Минимальный async-клиент T-Invest REST API для бумаг и дивидендов.

    Использует /rest/... InstrumentsService. Нужен read-only токен
    (создаётся на https://www.tbank.ru/invest/settings/api).
    """

    def __init__(self, token: str, base_url: str = TBANK_BASE, timeout: float = 30.0):
        self._token = token
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-app-name": "stocks-bot",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "TBankClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def _post(self, method: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base}/{_SERVICE}/{method}"
        resp = await self._client.post(url, json=body)
        if resp.status_code == 401:
            raise TBankAuthError("T-Invest token is missing or invalid")
        resp.raise_for_status()
        return resp.json()

    async def fetch_shares(self) -> list[Security]:
        """Все торгуемые акции (RUB); дубликаты по тикеру убираем."""
        payload = await self._post(
            "Shares", {"instrumentStatus": "INSTRUMENT_STATUS_BASE"}
        )
        out: dict[str, Security] = {}
        for item in payload.get("instruments", []) or []:
            ticker = (item.get("ticker") or "").strip()
            figi = (item.get("figi") or "").strip()
            if not ticker or not figi:
                continue
            currency = (item.get("currency") or "").lower()
            if currency != "rub":
                continue
            name = item.get("name") or ticker
            sec = Security(
                secid=ticker,
                shortname=name,
                secname=name,
                board=item.get("classCode") or "TQBR",
                type="share",
                figi=figi,
            )
            # prefer TQBR-like primary boards on ticker collision
            existing = out.get(ticker)
            if existing is None or (sec.board == "TQBR" and existing.board != "TQBR"):
                out[ticker] = sec
        return list(out.values())

    async def fetch_dividends(
        self,
        figi: str,
        from_date: date,
        to_date: date,
    ) -> list[Dividend]:
        """Дивиденды по FIGI в окне [from_date, to_date] (включительно по дате записи)."""
        if not figi:
            return []
        body = {
            "instrumentId": figi,
            "from": _date_to_tbank(from_date),
            "to": _date_to_tbank(to_date),
        }
        payload = await self._post("GetDividends", body)
        out: list[Dividend] = []
        for item in payload.get("dividends", []) or []:
            rec = _parse_iso_date(item.get("recordDate"))
            if rec is None:
                continue
            net_q = item.get("dividendNet") or {}
            value = _quotation_to_float(net_q)
            if value <= 0:
                continue
            currency = (net_q.get("currency") or "rub").upper()
            out.append(
                Dividend(
                    registry_close_date=rec,
                    value=value,
                    currency=currency,
                )
            )
        out.sort(key=lambda d: d.registry_close_date)
        return out
