from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..db import Database, Security
from ..dividends import build_report, format_report
from ..matcher import match_security
from ..tbank import TBankAuthError, TBankClient

log = logging.getLogger(__name__)
router = Router()

DIVIDENDS_STALE_HOURS = 12
# Сколько истории дивидендов запрашивать относительно первой покупки.
DIVIDENDS_HISTORY_MARGIN_DAYS = 365
# Насколько заглядывать вперёд (нужно, чтобы вытянуть объявленные будущие).
DIVIDENDS_FUTURE_MARGIN_DAYS = 365


async def _ensure_dividends(
    db: Database, tbank: TBankClient, sec: Security, first_purchase: date
) -> None:
    updated = await db.dividends_updated_at(sec.secid)
    if updated is not None:
        age = datetime.now(timezone.utc) - updated
        if age < timedelta(hours=DIVIDENDS_STALE_HOURS):
            cached = await db.get_dividends(sec.secid)
            if cached:
                return
    if not sec.figi:
        log.warning("no FIGI for %s, cannot fetch dividends", sec.secid)
        return
    today = date.today()
    from_date = min(first_purchase, today) - timedelta(days=DIVIDENDS_HISTORY_MARGIN_DAYS)
    to_date = today + timedelta(days=DIVIDENDS_FUTURE_MARGIN_DAYS)
    try:
        divs = await tbank.fetch_dividends(sec.figi, from_date, to_date)
    except TBankAuthError:
        log.error("T-Invest token invalid or missing")
        return
    except Exception as e:
        log.warning("failed to refresh dividends for %s: %s", sec.secid, e)
        return
    if divs:
        await db.replace_dividends(sec.secid, divs)


@router.message(Command("dividends"))
async def cmd_dividends(
    message: Message, command: CommandObject, db: Database, tbank: TBankClient
) -> None:
    user_id = message.from_user.id if message.from_user else 0
    raw_name = (command.args or "").strip()
    if not raw_name:
        await message.answer(
            "Укажи название или тикер: <code>/dividends Сбер</code>."
        )
        return

    match = await match_security(db, user_id, raw_name)
    sec = match.picked
    if sec is None:
        if match.suggestions:
            hint = ", ".join(f"{s.shortname} ({s.secid})" for s in match.suggestions)
            await message.answer(
                f"Не понял однозначно «{raw_name}». Возможные варианты: {hint}.\n"
                "Уточни тикер."
            )
        else:
            await message.answer(f"Не нашёл бумагу «{raw_name}».")
        return

    purchases = await db.list_purchases(user_id, sec.secid)
    if not purchases:
        await message.answer(f"Нет покупок по {sec.shortname} ({sec.secid}).")
        return

    first_purchase = min(p.purchased_at for p in purchases)
    await _ensure_dividends(db, tbank, sec, first_purchase)
    dividends = await db.get_dividends(sec.secid)
    report = build_report(sec.secid, purchases, dividends)
    await message.answer(format_report(report, sec.shortname))
