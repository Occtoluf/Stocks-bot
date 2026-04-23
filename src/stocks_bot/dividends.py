from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .db import Dividend, Purchase


def effective_price(price: float, commission_pct: float) -> float:
    return price * (1 + commission_pct / 100)


def dividends_since(dividends: list[Dividend], since: date) -> float:
    return sum(d.value for d in dividends if d.registry_close_date >= since)


def dividend_percent(purchase: Purchase, dividends: list[Dividend]) -> float:
    eff = effective_price(purchase.price, purchase.commission_pct)
    if eff <= 0:
        return 0.0
    total = dividends_since(dividends, purchase.purchased_at)
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
    lines: list[PurchaseLine]


def build_report(secid: str, purchases: list[Purchase], dividends: list[Dividend]) -> DividendReport:
    if not purchases:
        raise ValueError("purchases must not be empty")
    purchases = sorted(purchases, key=lambda p: (p.purchased_at, p.id))

    total_qty = sum(p.qty for p in purchases)
    total_cost = sum(p.qty * effective_price(p.price, p.commission_pct) for p in purchases)
    avg_price = total_cost / total_qty if total_qty > 0 else 0.0

    first_purchase = purchases[0].purchased_at
    total_divs = dividends_since(dividends, first_purchase)
    avg_percent = (total_divs / avg_price * 100) if avg_price > 0 else 0.0

    lines = [
        PurchaseLine(
            id=p.id,
            purchased_at=p.purchased_at,
            qty=p.qty,
            price=p.price,
            percent=dividend_percent(p, dividends),
        )
        for p in purchases
    ]

    return DividendReport(
        secid=secid,
        first_purchase=first_purchase,
        total_qty=total_qty,
        avg_price=avg_price,
        avg_percent=avg_percent,
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
        f"Дивиденд на среднюю: {report.avg_percent:.2f}%\n"
        f"\nПокупки:"
    )
    lines = [
        f"#{ln.id} {ln.purchased_at.strftime('%d.%m.%y')} "
        f"{_fmt_num(ln.qty)}x{_fmt_num(ln.price)} {ln.percent:.2f}%"
        for ln in report.lines
    ]
    return head + "\n" + "\n".join(lines)
