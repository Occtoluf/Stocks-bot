from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..db import Database
from ..dividends import build_report, format_report
from ..matcher import match_security
from ..moex import MoexClient

log = logging.getLogger(__name__)
router = Router()

DIVIDENDS_STALE_HOURS = 24


async def _ensure_dividends(db: Database, moex: MoexClient, secid: str) -> None:
    from datetime import datetime, timezone, timedelta

    updated = await db.dividends_updated_at(secid)
    if updated is not None:
        age = datetime.now(timezone.utc) - updated
        if age < timedelta(hours=DIVIDENDS_STALE_HOURS):
            return
    try:
        divs = await moex.fetch_dividends(secid)
    except Exception as e:
        log.warning("failed to refresh dividends for %s: %s", secid, e)
        return
    await db.replace_dividends(secid, divs)


@router.message(Command("dividends"))
async def cmd_dividends(
    message: Message, command: CommandObject, db: Database, moex: MoexClient
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

    await _ensure_dividends(db, moex, sec.secid)
    dividends = await db.get_dividends(sec.secid)
    report = build_report(sec.secid, purchases, dividends)
    await message.answer(format_report(report, sec.shortname))
