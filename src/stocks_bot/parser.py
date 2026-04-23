from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

_DATE_RE = r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"

_PURCHASE_RE = re.compile(
    rf"""^\s*
        (?P<name>.+?)\s+
        (?P<qty>\d+(?:[.,]\d+)?)\s*
        [xх×*]\s*
        (?P<price>\d+(?:[.,]\d+)?)
        (?:\s+(?P<date>{_DATE_RE}))?
        \s*$""",
    re.IGNORECASE | re.VERBOSE,
)

_EDIT_RE = re.compile(
    rf"""^\s*
        (?P<qty>\d+(?:[.,]\d+)?)\s*
        [xх×*]\s*
        (?P<price>\d+(?:[.,]\d+)?)
        (?:\s+(?P<date>{_DATE_RE}))?
        \s*$""",
    re.IGNORECASE | re.VERBOSE,
)


@dataclass
class ParsedPurchase:
    name: str
    qty: float
    price: float
    purchased_at: date | None


@dataclass
class ParsedQtyPrice:
    qty: float
    price: float
    purchased_at: date | None


_DATE_FORMATS = ("%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y")


def _to_float(raw: str) -> float:
    return float(raw.replace(",", "."))


def parse_date(raw: str) -> date | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_purchase(text: str) -> ParsedPurchase | None:
    m = _PURCHASE_RE.match(text)
    if not m:
        return None
    name = m.group("name").strip()
    if not name:
        return None
    raw_date = m.group("date")
    purchased_at: date | None = None
    if raw_date:
        purchased_at = parse_date(raw_date)
        if purchased_at is None:
            return None
    return ParsedPurchase(
        name=name,
        qty=_to_float(m.group("qty")),
        price=_to_float(m.group("price")),
        purchased_at=purchased_at,
    )


def parse_qty_price(text: str) -> ParsedQtyPrice | None:
    m = _EDIT_RE.match(text)
    if not m:
        return None
    raw_date = m.group("date")
    purchased_at: date | None = None
    if raw_date:
        purchased_at = parse_date(raw_date)
        if purchased_at is None:
            return None
    return ParsedQtyPrice(
        qty=_to_float(m.group("qty")),
        price=_to_float(m.group("price")),
        purchased_at=purchased_at,
    )
