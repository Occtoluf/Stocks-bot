from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from aiogram import F, Router
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..db import Database, Security
from ..matcher import match_security
from ..parser import parse_purchase

log = logging.getLogger(__name__)
router = Router()


@dataclass
class PendingPurchase:
    raw_name: str
    qty: float
    price: float
    suggestions: list[Security]


# process-local хранилище выбора. Ключ: (user_id, message_id бота с кнопками).
_pending: dict[tuple[int, int], PendingPurchase] = {}


class PickCB(CallbackData, prefix="pick"):
    index: int  # индекс в suggestions; -1 = cancel


def _format_confirmation(sec: Security, qty: float, price: float, purchased_at: date) -> str:
    return (
        f"✅ Сохранено: <b>{sec.shortname}</b> ({sec.secid})\n"
        f"{purchased_at.strftime('%d.%m.%y')} — {qty:g} × {price:g}"
    )


def _build_kb(suggestions: list[Security]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for i, sec in enumerate(suggestions):
        label = f"{sec.shortname} ({sec.secid})"
        kb.row(InlineKeyboardButton(text=label, callback_data=PickCB(index=i).pack()))
    kb.row(InlineKeyboardButton(text="Отмена", callback_data=PickCB(index=-1).pack()))
    return kb


async def _save_purchase(
    db: Database,
    user_id: int,
    sec: Security,
    raw_name: str,
    qty: float,
    price: float,
) -> tuple[Security, date]:
    commission = await db.get_commission(user_id)
    today = date.today()
    await db.add_purchase(user_id, sec.secid, qty, price, commission, today)
    await db.set_alias(user_id, raw_name, sec.secid)
    return sec, today


@router.message(F.text & ~F.text.startswith("/"))
async def handle_free_text(message: Message, db: Database) -> None:
    text = message.text or ""
    parsed = parse_purchase(text)
    if parsed is None:
        return  # молча игнорим — возможно пользователь пишет что-то другое

    user_id = message.from_user.id if message.from_user else 0
    match = await match_security(db, user_id, parsed.name)

    if match.picked:
        sec, purchased_at = await _save_purchase(
            db, user_id, match.picked, parsed.name, parsed.qty, parsed.price
        )
        await message.answer(_format_confirmation(sec, parsed.qty, parsed.price, purchased_at))
        return

    suggestions = match.suggestions or []
    if not suggestions:
        await message.answer(
            "Не нашёл такую бумагу. Попробуй указать тикер (например, <code>SBER</code>) "
            "или уточнить название."
        )
        return

    kb = _build_kb(suggestions)
    sent = await message.answer(
        f"Под «{parsed.name}» подходит несколько бумаг — выбери нужную:",
        reply_markup=kb.as_markup(),
    )
    _pending[(user_id, sent.message_id)] = PendingPurchase(
        raw_name=parsed.name,
        qty=parsed.qty,
        price=parsed.price,
        suggestions=suggestions,
    )


@router.callback_query(PickCB.filter())
async def handle_pick(query: CallbackQuery, callback_data: PickCB, db: Database) -> None:
    user_id = query.from_user.id
    msg = query.message
    key = (user_id, msg.message_id) if msg else None
    pending = _pending.pop(key, None) if key else None

    if pending is None:
        await query.answer("Выбор уже неактуален", show_alert=False)
        if msg:
            await msg.edit_text("Выбор уже неактуален — отправь покупку заново.")
        return

    if callback_data.index == -1:
        await query.answer("Отменено")
        if msg:
            await msg.edit_text("Отменено.")
        return

    try:
        sec = pending.suggestions[callback_data.index]
    except IndexError:
        await query.answer("Некорректный выбор", show_alert=True)
        return

    sec, purchased_at = await _save_purchase(
        db, user_id, sec, pending.raw_name, pending.qty, pending.price
    )
    await query.answer("Сохранено")
    if msg:
        await msg.edit_text(_format_confirmation(sec, pending.qty, pending.price, purchased_at))
