from datetime import date

import pytest

from stocks_bot.db import Dividend, Purchase
from stocks_bot.dividends import (
    build_report,
    dividend_percent,
    dividends_since,
    effective_price,
    format_report,
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


def test_effective_price_no_commission():
    assert effective_price(100, 0) == 100


def test_effective_price_with_commission():
    assert effective_price(100, 0.3) == pytest.approx(100.3)


def test_dividends_since_includes_equal_date():
    divs = [_d("2024-05-01", 25), _d("2025-05-01", 30)]
    assert dividends_since(divs, date(2024, 5, 1)) == 55
    assert dividends_since(divs, date(2024, 5, 2)) == 30


def test_dividend_percent_simple():
    p = _p(1, 10, 100, "2024-01-01")
    divs = [_d("2024-05-01", 10)]
    assert dividend_percent(p, divs) == 10.0


def test_dividend_percent_with_commission():
    p = _p(1, 10, 100, "2024-01-01", commission=1.0)  # eff = 101
    divs = [_d("2024-05-01", 10)]
    assert abs(dividend_percent(p, divs) - (10 / 101 * 100)) < 1e-9


def test_dividend_percent_ignores_older_dividends():
    p = _p(1, 10, 100, "2024-06-01")
    divs = [_d("2024-05-01", 10)]
    assert dividend_percent(p, divs) == 0.0


def test_build_report_averages_and_lines():
    purchases = [
        _p(1, 10, 100, "2024-01-01"),
        _p(2, 10, 120, "2024-07-01"),
    ]
    divs = [_d("2024-05-01", 5), _d("2024-09-01", 5)]
    r = build_report("SBER", purchases, divs)
    assert r.first_purchase == date(2024, 1, 1)
    assert r.total_qty == 20
    assert r.avg_price == 110
    # both dividends relevant for avg (first purchase 01.01)
    assert abs(r.avg_percent - (10 / 110 * 100)) < 1e-9
    assert len(r.lines) == 2
    # first purchase gets both divs
    assert abs(r.lines[0].percent - 10.0) < 1e-9
    # second purchase gets only the Sep one on 120
    assert abs(r.lines[1].percent - (5 / 120 * 100)) < 1e-9


def test_format_report_has_expected_parts():
    purchases = [_p(7, 10, 100, "2024-01-02")]
    divs = [_d("2024-05-01", 10)]
    r = build_report("SBER", purchases, divs)
    text = format_report(r, "Сбер")
    assert "Сбер" in text
    assert "SBER" in text
    assert "02.01.24" in text
    assert "#7" in text
    assert "10x100" in text
    assert "10.00%" in text
