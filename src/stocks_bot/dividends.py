from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .db import Dividend, Purchase


def effective_price(price: float, commission_pct: float) -> float:
    return price * (1 + commission_pct / 100)


def dividends_since(dividends: list[Dividend], since: date, until: date | None = None) -> float:
    """Сумма выплат на акцию, у которых record date в [since, until]."""
    total = 0.0
    for d in dividends:
        if d.registry_close_date < since:
            continue
        if until is not None and d.registry_close_date > until:
            continue
        total += d.value
    return total


def next_dividend(dividends: list[Dividend], today: date) -> Dividend | None:
    future = [d for d in dividends if d.registry_close_date > today and d.value > 0]
    if not future:
        return None
    return min(future, key=lambda d: d.registry_close_date)


def last_paid_dividend(dividends: list[Dividend], today: date) -> Dividend | None:
    past = [d for d in dividends if d.registry_close_date <= today and d.value > 0]
    if not past:
        return None
    return max(past, key=lambda d: d.registry_close_date)


def dividend_percent(purchase: Purchase, dividends: list[Dividend], today: date) -> float:
    eff = effective_price(purchase.price, purchase.commission_pct)
    if eff <= 0:
        return 0.0
    per_share = dividends_since(dividends, purchase.purchased_at, until=today)
    return per_share / eff * 100


def dividend_rub(purchase: Purchase, dividends: list[Dividend], today: date) -> float:
    """Сколько рублей дивидендов реально принесла именно эта покупка."""
    per_share = dividends_since(dividends, purchase.purchased_at, until=today)
    return per_share * purchase.qty


@dataclass
class PurchaseLine:
    id: int
    purchased_at: date
    qty: float
    price: float
    paid_rub: float
    percent: float


@dataclass
class DividendReport:
    secid: str
    first_purchase: date
    total_qty: float
    total_cost: float
    avg_price: float
    total_paid_rub: float
    avg_percent: float
    next_value: float | None
    next_rub: float | None
    next_percent: float | None
    next_date: date | None
    combined_rub: float | None
    combined_percent: float | None
    last_paid_value: float | None
    last_paid_date: date | None
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

    lines = [
        PurchaseLine(
            id=p.id,
            purchased_at=p.purchased_at,
            qty=p.qty,
            price=p.price,
            paid_rub=dividend_rub(p, dividends, today),
            percent=dividend_percent(p, dividends, today),
        )
        for p in purchases
    ]

    total_paid_rub = sum(ln.paid_rub for ln in lines)
    avg_percent = total_paid_rub / total_cost * 100 if total_cost > 0 else 0.0

    nxt = next_dividend(dividends, today)
    next_value: float | None = None
    next_rub: float | None = None
    next_percent: float | None = None
    next_date: date | None = None
    combined_rub: float | None = None
    combined_percent: float | None = None
    if nxt is not None:
        next_value = nxt.value
        next_rub = nxt.value * total_qty
        next_date = nxt.registry_close_date
        if total_cost > 0:
            next_percent = next_rub / total_cost * 100
            combined_rub = total_paid_rub + next_rub
            combined_percent = combined_rub / total_cost * 100

    last = last_paid_dividend(dividends, today)
    last_paid_value = last.value if last else None
    last_paid_date = last.registry_close_date if last else None

    return DividendReport(
        secid=secid,
        first_purchase=first_purchase,
        total_qty=total_qty,
        total_cost=total_cost,
        avg_price=avg_price,
        total_paid_rub=total_paid_rub,
        avg_percent=avg_percent,
        next_value=next_value,
        next_rub=next_rub,
        next_percent=next_percent,
        next_date=next_date,
        combined_rub=combined_rub,
        combined_percent=combined_percent,
        last_paid_value=last_paid_value,
        last_paid_date=last_paid_date,
        lines=lines,
    )


def _fmt_num(v: float) -> str:
    if v == int(v):
        return f"{int(v)}"
    return f"{v:.4f}".rstrip("0").rstrip(".")


def _fmt_rub(v: float) -> str:
    rounded = round(v, 2)
    if abs(rounded - round(rounded)) < 1e-9:
        return f"{int(round(rounded)):,}".replace(",", " ")
    return f"{rounded:,.2f}".replace(",", " ")


def format_report(report: DividendReport, display_name: str) -> str:
    head = (
        f"<b>{display_name}</b> ({report.secid})\n"
        f"Первая покупка: {report.first_purchase.strftime('%d.%m.%y')}\n"
        f"Всего: {_fmt_num(report.total_qty)} шт\n"
        f"Средняя цена: {report.avg_price:.2f}\n"
        f"Выплачено дивидендов: {_fmt_rub(report.total_paid_rub)} ₽ "
        f"({report.avg_percent:.2f}%)"
    )

    if (
        report.next_rub is not None
        and report.next_percent is not None
        and report.next_date is not None
    ):
        head += (
            f"\n+ ближайший дивиденд: {_fmt_rub(report.next_rub)} ₽ "
            f"({report.next_date.strftime('%d.%m.%y')}, +{report.next_percent:.2f}%)"
        )
        if report.combined_rub is not None and report.combined_percent is not None:
            head += (
                f"\n= с учётом ближайшего: {_fmt_rub(report.combined_rub)} ₽ "
                f"({report.combined_percent:.2f}%)"
            )
    elif report.last_paid_date is not None and report.last_paid_value is not None:
        head += (
            f"\nБлижайший дивиденд: не объявлен "
            f"(последний — {_fmt_rub(report.last_paid_value)} ₽/акц. "
            f"на {report.last_paid_date.strftime('%d.%m.%y')})"
        )
    else:
        head += "\nБлижайший дивиденд: не объявлен"

    head += "\n\nПокупки:"

    lines = [
        f"#{ln.id} {ln.purchased_at.strftime('%d.%m.%y')} "
        f"{_fmt_num(ln.qty)}x{_fmt_num(ln.price)} → "
        f"{_fmt_rub(ln.paid_rub)} ₽ ({ln.percent:.2f}%)"
        for ln in report.lines
    ]
    return head + "\n" + "\n".join(lines)
