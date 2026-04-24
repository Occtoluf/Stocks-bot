from __future__ import annotations

import os
from datetime import date, timedelta

import httpx
import pytest

from stocks_bot.tbank import (
    TBankAuthError,
    TBankClient,
    _date_to_tbank,
    _parse_iso_date,
    _quotation_to_float,
)


def test_quotation_to_float_units_and_nano():
    assert _quotation_to_float({"units": "70", "nano": 850000000}) == pytest.approx(70.85)
    assert _quotation_to_float({"units": "36", "nano": 0}) == 36
    assert _quotation_to_float({"units": "-1", "nano": -500000000}) == pytest.approx(-1.5)
    assert _quotation_to_float(None) == 0.0
    assert _quotation_to_float({}) == 0.0


def test_parse_iso_date():
    assert _parse_iso_date("2025-10-10T00:00:00Z") == date(2025, 10, 10)
    assert _parse_iso_date("2026-05-15T10:30:00+03:00") == date(2026, 5, 15)
    assert _parse_iso_date(None) is None
    assert _parse_iso_date("garbage") is None


def test_date_to_tbank_format():
    assert _date_to_tbank(date(2025, 1, 2)) == "2025-01-02T00:00:00Z"


async def test_fetch_shares_parses_and_dedupes(monkeypatch):
    client = TBankClient("fake")
    captured: dict[str, object] = {}

    async def fake_post(method: str, body: dict):
        captured["method"] = method
        captured["body"] = body
        return {
            "instruments": [
                {
                    "figi": "BBG004730N88",
                    "ticker": "SBER",
                    "classCode": "TQBR",
                    "currency": "rub",
                    "name": "Сбер Банк",
                },
                {
                    "figi": "BBG004730N88",
                    "ticker": "SBER",
                    "classCode": "SPEQ",
                    "currency": "rub",
                    "name": "Сбер Банк",
                },
                {
                    "figi": "BBG000BVPV84",
                    "ticker": "AAPL",
                    "classCode": "SPEQ",
                    "currency": "usd",
                    "name": "Apple",
                },
                {
                    "figi": "",
                    "ticker": "NOFIGI",
                    "classCode": "TQBR",
                    "currency": "rub",
                    "name": "broken",
                },
            ]
        }

    monkeypatch.setattr(client, "_post", fake_post)
    try:
        shares = await client.fetch_shares()
    finally:
        await client.aclose()

    assert captured["method"] == "Shares"
    tickers = {s.secid for s in shares}
    assert tickers == {"SBER"}  # USD + dup + empty figi dropped
    sber = next(s for s in shares if s.secid == "SBER")
    assert sber.figi == "BBG004730N88"
    assert sber.board == "TQBR"


async def test_fetch_dividends_parses(monkeypatch):
    client = TBankClient("fake")
    captured: dict[str, object] = {}

    async def fake_post(method: str, body: dict):
        captured["method"] = method
        captured["body"] = body
        return {
            "dividends": [
                {
                    "recordDate": "2025-10-10T00:00:00Z",
                    "paymentDate": "2025-10-25T00:00:00Z",
                    "dividendNet": {"units": "70", "nano": 850000000, "currency": "rub"},
                },
                {
                    "recordDate": "2025-12-19T00:00:00Z",
                    "dividendNet": {"units": "36", "nano": 0, "currency": "rub"},
                },
                {
                    "recordDate": "2026-05-15T00:00:00Z",
                    "dividendNet": {"units": "56", "nano": 800000000, "currency": "rub"},
                },
                {
                    "recordDate": None,
                    "dividendNet": {"units": "10", "nano": 0, "currency": "rub"},
                },
                {
                    "recordDate": "2024-01-01T00:00:00Z",
                    "dividendNet": {"units": "0", "nano": 0, "currency": "rub"},
                },
            ]
        }

    monkeypatch.setattr(client, "_post", fake_post)
    try:
        divs = await client.fetch_dividends(
            "BBG", date(2024, 1, 1), date(2027, 1, 1)
        )
    finally:
        await client.aclose()

    assert captured["method"] == "GetDividends"
    assert captured["body"]["instrumentId"] == "BBG"
    assert captured["body"]["from"] == "2024-01-01T00:00:00Z"

    assert [d.registry_close_date for d in divs] == [
        date(2025, 10, 10),
        date(2025, 12, 19),
        date(2026, 5, 15),
    ]
    assert divs[0].value == pytest.approx(70.85)
    assert divs[1].value == 36
    assert divs[2].value == pytest.approx(56.8)
    assert all(d.currency == "RUB" for d in divs)


async def test_fetch_dividends_empty_figi():
    client = TBankClient("fake")
    try:
        divs = await client.fetch_dividends("", date(2024, 1, 1), date(2027, 1, 1))
    finally:
        await client.aclose()
    assert divs == []


async def test_auth_error_on_401(monkeypatch):
    client = TBankClient("fake")

    class FakeResp:
        status_code = 401

        def raise_for_status(self):
            raise httpx.HTTPStatusError("401", request=None, response=None)

        def json(self):
            return {}

    async def fake_http_post(url, json):
        return FakeResp()

    monkeypatch.setattr(client._client, "post", fake_http_post)
    try:
        with pytest.raises(TBankAuthError):
            await client.fetch_shares()
    finally:
        await client.aclose()


# ------- live tests (opt-in) -----------------------------------------------

TBANK_TOKEN_ENV = os.environ.get("TBANK_TOKEN")


@pytest.mark.tbank
async def test_live_fetch_shares():
    """Живой вызов T-Invest: нужен TBANK_TOKEN в окружении."""
    if not TBANK_TOKEN_ENV:
        pytest.skip("TBANK_TOKEN not set")
    async with TBankClient(TBANK_TOKEN_ENV) as client:
        shares = await client.fetch_shares()
    tickers = {s.secid for s in shares}
    assert "SBER" in tickers
    sber = next(s for s in shares if s.secid == "SBER")
    assert sber.figi


@pytest.mark.tbank
async def test_live_fetch_dividends_plzl():
    """Живой вызов: у PLZL должны быть свежие дивиденды, которых нет в MOEX ISS."""
    if not TBANK_TOKEN_ENV:
        pytest.skip("TBANK_TOKEN not set")
    async with TBankClient(TBANK_TOKEN_ENV) as client:
        shares = await client.fetch_shares()
        plzl = next((s for s in shares if s.secid == "PLZL"), None)
        assert plzl is not None and plzl.figi
        divs = await client.fetch_dividends(
            plzl.figi,
            date.today() - timedelta(days=365 * 2),
            date.today() + timedelta(days=365),
        )
    assert divs, "expected at least one dividend for PLZL"
    # хотя бы одна строка должна быть свежее того, что отдаёт MOEX ISS (25.04.2025)
    assert max(d.registry_close_date for d in divs) > date(2025, 4, 25)
