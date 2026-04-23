from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .db import Dividend, Purchase


def effective_price(price: float, commission_pct: float) -> float:
    return price * (1 + commission_pct / 100)


def dividends_since(dividends: list[Dividend], since: date, until: date | None = None) -> float:
    def ok(d: Dividend) -> bool:
        if d.registry_close_date < since:
            return False
        if until is not None and d.registry_close_date > until:
            return False
        return True

    return sum(d.value for d in dividends if ok(d))


def next_dividend(dividends: list[Dividend], today: date) -> Dividend | None:
    future = [d for d in dividends if d.registry_close_date > today]
    if not future:
        return None
    return min(future, key=lambda d: d.registry_close_date)


def dividend_percent(purchase: Purchase, dividends: list[Dividend], today: date) -> float:
    """Выплаченные дивиденды с даты покупки (не считая будущих) / цену."""
    eff = effective_price(purchase.price, purchase.commission_pct)
    if eff <= 0:
        return 0.0
    total = dividends_since(dividends, purchase.purchased_at, until=today)
    return total / eff * 100


@dataclass
class PurchaseLine:
    id: int
    purchased_at: date
    qty: float
    price: float
    percent: float


@dataclass
class DividendReport:
    secid: str
    first_purchase: date
    total_qty: float
    avg_price: float
    avg_percent: float
    next_percent: float | None
    next_date: date | None
    lines: list[PurchaseLine]


def build_report(
    secid: str,
    purchases: list[Purchase],
    dividends: list[Dividend],
    today: date | None = None,
) -> DividendReport:
    if not purchases:
        raise ValueError("purchases must not be empty")
    if today is None:
        today = date.today()
    purchases = sorted(purchases, key=lambda p: (p.purchased_at, p.id))

    total_qty = sum(p.qty for p in purchases)
    total_cost = sum(p.qty * effective_price(p.price, p.commission_pct) for p in purchases)
    avg_price = total_cost / total_qty if total_qty > 0 else 0.0

    first_purchase = purchases[0].purchased_at
    
    if total_cost > 0:
    avg_percent = sum(
        dividends_since(dividends, p.purchased_at, until=today)
        * p.qty
        * effective_price(p.price, p.commission_pct)
        for p in purchases
        ) / total_cost * 100
    else:
        avg_percent = 0.0

    nxt = next_dividend(dividends, today)
    next_percent: float | None = None
    next_date: date | None = None
    if nxt is not None and avg_price > 0:
        next_percent = nxt.value / avg_price * 100
        next_date = nxt.registry_close_date

    lines = [
        PurchaseLine(
            id=p.id,
            purchased_at=p.purchased_at,
            qty=p.qty,
            price=p.price,
            percent=dividend_percent(p, dividends, today),
        )
        for p in purchases
    ]

    return DividendReport(
        secid=secid,
        first_purchase=first_purchase,
        total_qty=total_qty,
        avg_price=avg_price,
        avg_percent=avg_percent,
        next_percent=next_percent,
        next_date=next_date,
        lines=lines,
    )


def _fmt_num(v: float) -> str:
    if v == int(v):
        return f"{int(v)}"
    return f"{v:.4f}".rstrip("0").rstrip(".")


def format_report(report: DividendReport, display_name: str) -> str:
    head = (
        f"<b>{display_name}</b> ({report.secid})\n"
        f"Первая покупка: {report.first_purchase.strftime('%d.%m.%y')}\n"
        f"Всего: {_fmt_num(report.total_qty)} шт\n"
        f"Средняя цена: {report.avg_price:.2f}\n"
        f"Выплаченные средние дивиденды: {report.avg_percent:.2f}%"
    )
    if report.next_percent is not None and report.next_date is not None:
        head += (
            f"\n+ ближайший дивиденд: {report.next_percent:.2f}% "
            f"({report.next_date.strftime('%d.%m.%y')})"
        )
    head += "\n\nПокупки:"

    lines = [
        f"#{ln.id} {ln.purchased_at.strftime('%d.%m.%y')} "
        f"{_fmt_num(ln.qty)}x{_fmt_num(ln.price)} {ln.percent:.2f}%"
        for ln in report.lines
    ]
    return head + "\n" + "\n".join(lines)
