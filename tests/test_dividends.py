from datetime import date

import pytest

from stocks_bot.db import Dividend, Purchase
from stocks_bot.dividends import (
    build_report,
    dividend_percent,
    dividend_rub,
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


TODAY = date(2026, 4, 24)


def test_effective_price_no_commission():
    assert effective_price(100, 0) == 100


def test_effective_price_with_commission():
    assert effective_price(100, 0.3) == pytest.approx(100.3)


def test_dividends_since_bounds():
    divs = [_d("2024-05-01", 25), _d("2025-05-01", 30), _d("2025-12-01", 40)]
    assert dividends_since(divs, date(2024, 1, 1), until=date(2025, 6, 1)) == 55
    assert dividends_since(divs, date(2024, 1, 1)) == 95


def test_dividend_percent_ignores_future():
    p = _p(1, 10, 100, "2024-01-01")
    divs = [_d("2024-05-01", 10), _d("2027-01-01", 5)]
    # 2027 — после TODAY=24.04.26, не учитываем
    assert dividend_percent(p, divs, TODAY) == 10.0


def test_dividend_percent_with_commission():
    p = _p(1, 10, 100, "2024-01-01", commission=1.0)  # eff = 101
    divs = [_d("2024-05-01", 10)]
    assert abs(dividend_percent(p, divs, TODAY) - (10 / 101 * 100)) < 1e-9


def test_dividend_rub_only_paid_counts():
    p = _p(1, 5, 100, "2024-01-01")
    divs = [_d("2024-05-01", 10), _d("2027-01-01", 7)]
    assert dividend_rub(p, divs, TODAY) == 50  # 5 qty * 10 paid


def test_next_dividend_picks_earliest_future_positive():
    divs = [
        _d("2024-05-01", 10),
        _d("2027-09-01", 0),  # объявлен, но 0 — игнорируем
        _d("2027-12-01", 8),
        _d("2028-03-01", 5),
    ]
    nxt = next_dividend(divs, TODAY)
    assert nxt is not None
    assert nxt.registry_close_date == date(2027, 12, 1)
    assert nxt.value == 8


def test_next_dividend_none_when_empty():
    assert next_dividend([], TODAY) is None
    assert next_dividend([_d("2024-05-01", 10)], TODAY) is None


def test_build_report_plzl_scenario():
    """Сценарий пользователя: покупки после первой выплаты, между ними две выплаты,
    плюс один будущий утверждённый дивиденд."""
    purchases = [
        _p(1, 7, 1705.8, "2025-06-09"),
        _p(2, 5, 1752.2, "2025-06-16"),
    ]
    divs = [
        _d("2025-04-25", 73),        # до первой покупки — не считаем
        _d("2025-10-10", 70.85),     # после обеих покупок
        _d("2025-12-19", 36),        # после обеих покупок
        _d("2026-05-15", 56.8),      # будущий (относительно TODAY=24.04.26)
    ]
    r = build_report("PLZL", purchases, divs, today=TODAY)

    assert r.total_qty == 12
    assert r.first_purchase == date(2025, 6, 9)

    # per-share сумма выплаченных дивидендов: 70.85 + 36 = 106.85
    # каждая покупка держалась через обе выплаты
    assert r.lines[0].paid_rub == pytest.approx(7 * 106.85)
    assert r.lines[1].paid_rub == pytest.approx(5 * 106.85)
    assert r.total_paid_rub == pytest.approx(12 * 106.85)

    # % на сделку #1: 106.85 / 1705.8 * 100
    assert r.lines[0].percent == pytest.approx(106.85 / 1705.8 * 100)

    # ближайший будущий — 15.05.2026
    assert r.next_date == date(2026, 5, 15)
    assert r.next_value == pytest.approx(56.8)
    assert r.next_rub == pytest.approx(12 * 56.8)
    assert r.combined_rub == pytest.approx(r.total_paid_rub + 12 * 56.8)
    assert r.combined_percent == pytest.approx(r.combined_rub / r.total_cost * 100)


def test_build_report_mid_window_purchase_not_paid_dividend():
    """Покупка #2 сделана после дивиденда — не должна его «получить»."""
    purchases = [
        _p(1, 10, 100, "2024-01-01"),
        _p(2, 10, 120, "2024-07-01"),
    ]
    divs = [_d("2024-05-01", 5), _d("2027-09-01", 5)]
    r = build_report("SBER", purchases, divs, today=TODAY)

    assert r.lines[0].paid_rub == 50   # владел 10 акциями, 5 руб/акц
    assert r.lines[1].paid_rub == 0    # куплена позже record date
    assert r.total_paid_rub == 50
    assert r.total_cost == 2200
    assert r.avg_percent == pytest.approx(50 / 2200 * 100)

    assert r.next_date == date(2027, 9, 1)
    assert r.next_rub == pytest.approx(20 * 5)
    assert r.combined_rub == pytest.approx(50 + 100)


def test_build_report_no_future_no_past():
    purchases = [_p(1, 10, 100, "2025-01-01")]
    divs: list = []
    r = build_report("SBER", purchases, divs, today=TODAY)
    assert r.total_paid_rub == 0
    assert r.avg_percent == 0
    assert r.next_percent is None
    assert r.last_paid_value is None


def test_format_report_plzl_scenario_text():
    purchases = [
        _p(2, 7, 1705.8, "2025-06-09"),
        _p(3, 5, 1752.2, "2025-06-16"),
    ]
    divs = [
        _d("2025-04-25", 73),
        _d("2025-10-10", 70.85),
        _d("2025-12-19", 36),
        _d("2026-05-15", 56.8),
    ]
    r = build_report("PLZL", purchases, divs, today=TODAY)
    text = format_report(r, "Полюс")
    assert "Полюс" in text
    assert "PLZL" in text
    assert "Выплачено дивидендов" in text
    assert "₽" in text
    assert "ближайший дивиденд" in text
    assert "15.05.26" in text
    assert "с учётом ближайшего" in text
    # per-purchase line format
    assert "#2 09.06.25 7x1705.8" in text
    assert "#3 16.06.25 5x1752.2" in text


def test_format_report_no_future_shows_last_paid():
    purchases = [_p(1, 10, 100, "2025-01-01")]
    divs = [_d("2025-06-01", 7)]
    r = build_report("SBER", purchases, divs, today=TODAY)
    text = format_report(r, "Сбер")
    assert "Ближайший дивиденд: не объявлен" in text
    assert "последний" in text
    assert "01.06.25" in text


def test_format_report_no_dividends_at_all():
    purchases = [_p(1, 10, 100, "2025-01-01")]
    r = build_report("SBER", purchases, [], today=TODAY)
    text = format_report(r, "Сбер")
    assert "Ближайший дивиденд: не объявлен" in text
    assert "последний" not in text
