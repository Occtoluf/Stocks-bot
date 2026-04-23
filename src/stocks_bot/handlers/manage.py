from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..db import Database
from ..dividends import effective_price
from ..parser import parse_qty_price

router = Router()


def _fmt(v: float) -> str:
    if v == int(v):
        return f"{int(v)}"
    return f"{v:.4f}".rstrip("0").rstrip(".")


@router.message(Command("list"))
async def cmd_list(message: Message, db: Database) -> None:
    user_id = message.from_user.id if message.from_user else 0
    secids = await db.list_user_secids(user_id)
    if not secids:
        await message.answer("Пусто. Отправь первую покупку, например: <code>Сбер 10х315</code>.")
        return

    lines: list[str] = []
    for secid in sorted(secids):
        sec = await db.get_security(secid)
        name = sec.shortname if sec else secid
        purchases = await db.list_purchases(user_id, secid)
        total_qty = sum(p.qty for p in purchases)
        total_cost = sum(p.qty * effective_price(p.price, p.commission_pct) for p in purchases)
        avg = total_cost / total_qty if total_qty > 0 else 0
        lines.append(
            f"<b>{name}</b> ({secid}): {_fmt(total_qty)} шт, средняя {avg:.2f}"
        )
    await message.answer("\n".join(lines))


@router.message(Command("delete"))
async def cmd_delete(message: Message, command: CommandObject, db: Database) -> None:
    user_id = message.from_user.id if message.from_user else 0
    args = (command.args or "").strip()
    if not args.isdigit():
        await message.answer("Формат: <code>/delete 12</code> (id из /list или /dividends).")
        return
    purchase_id = int(args)
    ok = await db.delete_purchase(purchase_id, user_id)
    if ok:
        await message.answer(f"Покупка #{purchase_id} удалена.")
    else:
        await message.answer(f"Покупка #{purchase_id} не найдена.")


@router.message(Command("edit"))
async def cmd_edit(message: Message, command: CommandObject, db: Database) -> None:
    user_id = message.from_user.id if message.from_user else 0
    args = (command.args or "").strip()
    parts = args.split(maxsplit=1)
    if len(parts) != 2 or not parts[0].isdigit():
        await message.answer(
            "Формат: <code>/edit 12 10x320.5</code> или <code>/edit 12 10x320.5 1.1.2025</code>."
        )
        return
    purchase_id = int(parts[0])
    parsed = parse_qty_price(parts[1])
    if parsed is None:
        await message.answer(
            "Не понял qty/price. Пример: <code>/edit 12 10x320.5 1.1.2025</code>."
        )
        return
    existing = await db.get_purchase(purchase_id, user_id)
    if existing is None:
        await message.answer(f"Покупка #{purchase_id} не найдена.")
        return
    new_date = parsed.purchased_at or existing.purchased_at
    ok = await db.update_purchase(
        purchase_id, user_id, parsed.qty, parsed.price, new_date
    )
    if ok:
        await message.answer(
            f"Покупка #{purchase_id} обновлена: "
            f"{_fmt(parsed.qty)}x{_fmt(parsed.price)} от {new_date.strftime('%d.%m.%y')}."
        )
    else:
        await message.answer(f"Покупка #{purchase_id} не найдена.")


@router.message(Command("commission"))
async def cmd_commission(message: Message, command: CommandObject, db: Database) -> None:
    user_id = message.from_user.id if message.from_user else 0
    args = (command.args or "").strip().replace(",", ".")
    if not args:
        current = await db.get_commission(user_id)
        await message.answer(f"Текущая комиссия: {current:g}%. Задать: <code>/commission 0.3</code>.")
        return
    try:
        pct = float(args)
    except ValueError:
        await message.answer("Формат: <code>/commission 0.3</code>.")
        return
    if pct < 0 or pct > 10:
        await message.answer("Комиссия должна быть в пределах 0–10%.")
        return
    await db.set_commission(user_id, pct)
    await message.answer(
        f"Комиссия обновлена: {pct:g}%. Применяется к новым покупкам."
    )
