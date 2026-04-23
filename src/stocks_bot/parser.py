from __future__ import annotations

import re
from dataclasses import dataclass

_PURCHASE_RE = re.compile(
    r"""^\s*
        (?P<name>.+?)\s+
        (?P<qty>\d+(?:[.,]\d+)?)\s*
        [xх×*]\s*
        (?P<price>\d+(?:[.,]\d+)?)\s*$""",
    re.IGNORECASE | re.VERBOSE,
)

_EDIT_RE = re.compile(
    r"""^\s*
        (?P<qty>\d+(?:[.,]\d+)?)\s*
        [xх×*]\s*
        (?P<price>\d+(?:[.,]\d+)?)\s*$""",
    re.IGNORECASE | re.VERBOSE,
)


@dataclass
class ParsedPurchase:
    name: str
    qty: float
    price: float


@dataclass
class ParsedQtyPrice:
    qty: float
    price: float


def _to_float(raw: str) -> float:
    return float(raw.replace(",", "."))


def parse_purchase(text: str) -> ParsedPurchase | None:
    m = _PURCHASE_RE.match(text)
    if not m:
        return None
    name = m.group("name").strip()
    if not name:
        return None
    return ParsedPurchase(
        name=name,
        qty=_to_float(m.group("qty")),
        price=_to_float(m.group("price")),
    )


def parse_qty_price(text: str) -> ParsedQtyPrice | None:
    m = _EDIT_RE.match(text)
    if not m:
        return None
    return ParsedQtyPrice(
        qty=_to_float(m.group("qty")),
        price=_to_float(m.group("price")),
    )
