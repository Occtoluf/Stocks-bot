from datetime import date

import pytest

from stocks_bot.db import Dividend, Purchase
from stocks_bot.dividends import (
    build_report,
    dividend_percent,
    dividends_since,
    effective_price,
    format_report,
    next_dividend,
)


def _p(pid: int, qty: float, price: float, day: str, commission: float = 0.0) -> Purchase:
    return Purchase(
        id=pid,
        user_id=1,
        secid="SBER",
        qty=qty,
        price=price,
        commission_pct=commission,
        purchased_at=date.fromisoformat(day),
    )


def _d(day: str, value: float) -> Dividend:
    return Dividend(registry_close_date=date.fromisoformat(day), value=value, currency="RUB")


TODAY = date(2025, 6, 1)


def test_effective_price_no_commission():
    assert effective_price(100, 0) == 100


def test_effective_price_with_commission():
    assert effective_price(100, 0.3) == pytest.approx(100.3)


def test_dividends_since_bounds():
    divs = [_d("2024-05-01", 25), _d("2025-05-01", 30), _d("2025-12-01", 40)]
    # только прошлые, с учётом upper bound = today
    assert dividends_since(divs, date(2024, 1, 1), until=TODAY) == 55
    # без upper bound — считает и будущие
    assert dividends_since(divs, date(2024, 1, 1)) == 95


def test_dividend_percent_ignores_future():
    p = _p(1, 10, 100, "2024-01-01")
    divs = [_d("2024-05-01", 10), _d("2025-09-01", 5)]
    # только выплаченный (05-2024), будущий (09-2025) не считаем
    assert dividend_percent(p, divs, TODAY) == 10.0


def test_dividend_percent_with_commission():
    p = _p(1, 10, 100, "2024-01-01", commission=1.0)  # eff = 101
    divs = [_d("2024-05-01", 10)]
    assert abs(dividend_percent(p, divs, TODAY) - (10 / 101 * 100)) < 1e-9


def test_next_dividend_picks_earliest_future():
    divs = [_d("2024-05-01", 10), _d("2025-09-01", 5), _d("2025-12-01", 8)]
    nxt = next_dividend(divs, TODAY)
    assert nxt is not None
    assert nxt.registry_close_date == date(2025, 9, 1)


def test_next_dividend_none_when_empty():
    assert next_dividend([], TODAY) is None
    assert next_dividend([_d("2024-05-01", 10)], TODAY) is None


def test_build_report_with_future_dividend():
    purchases = [
        _p(1, 10, 100, "2024-01-01"),
        _p(2, 10, 120, "2024-07-01"),
    ]
    divs = [_d("2024-05-01", 5), _d("2025-09-01", 5)]  # вторая в будущем
    r = build_report("SBER", purchases, divs, today=TODAY)
    assert r.total_qty == 20
    assert r.avg_price == 110
    # выплачен только дивиденд 05-2024
    assert abs(r.avg_percent - (5 / 110 * 100)) < 1e-9
    # ближайший будущий — 09-2025, 5 руб
    assert r.next_percent is not None
    assert abs(r.next_percent - (5 / 110 * 100)) < 1e-9
    assert r.next_date == date(2025, 9, 1)


def test_build_report_without_future_dividend():
    purchases = [_p(1, 10, 100, "2024-01-01")]
    divs = [_d("2024-05-01", 10)]
    r = build_report("SBER", purchases, divs, today=TODAY)
    assert r.next_percent is None
    assert r.next_date is None


def test_format_report_includes_next_dividend():
    purchases = [_p(1, 10, 100, "2024-01-02")]
    divs = [_d("2024-05-01", 10), _d("2025-09-01", 5)]
    r = build_report("SBER", purchases, divs, today=TODAY)
    text = format_report(r, "Сбер")
    assert "Выплаченные средние дивиденды" in text
    assert "+ ближайший дивиденд" in text
    assert "01.09.25" in text


def test_format_report_skips_next_when_absent():
    purchases = [_p(1, 10, 100, "2024-01-02")]
    divs = [_d("2024-05-01", 10)]
    r = build_report("SBER", purchases, divs, today=TODAY)
    text = format_report(r, "Сбер")
    assert "ближайший дивиденд" not in text


def test_format_report_has_expected_parts():
    purchases = [_p(7, 10, 100, "2024-01-02")]
    divs = [_d("2024-05-01", 10)]
    r = build_report("SBER", purchases, divs, today=TODAY)
    text = format_report(r, "Сбер")
    assert "Сбер" in text
    assert "SBER" in text
    assert "02.01.24" in text
    assert "#7" in text
    assert "10x100" in text
    assert "10.00%" in text
