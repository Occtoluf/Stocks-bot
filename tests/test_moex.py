from datetime import date

from stocks_bot.moex import MoexClient


def _make_payload(columns: list, data: list) -> dict:
    return {"dividends": {"columns": columns, "data": data}}


def test_parse_dividendnetperms_field():
    """MOEX ISS uses dividendnetperms, not value."""
    columns = ["secid", "isin", "registryclosedate", "dividendnetperms", "currencyid"]
    data = [
        ["PLZL", "RU000A0JP7J7", "2024-07-05", 301.74, "RUB"],
        ["PLZL", "RU000A0JP7J7", "2025-05-16", 150.0, "RUB"],
    ]
    client = MoexClient.__new__(MoexClient)

    from stocks_bot.moex import _rows_from_block
    rows = _rows_from_block(_make_payload(columns, data), "dividends")

    # simulate the parse loop from fetch_dividends
    from stocks_bot.db import Dividend
    out = []
    for row in rows:
        raw_date = row.get("registryclosedate") or row.get("REGISTRYCLOSEDATE")
        value = (
            row.get("dividendnetperms")
            or row.get("DIVIDENDNETPERMS")
            or row.get("value")
            or row.get("VALUE")
        )
        currency = row.get("currencyid") or "RUB"
        if not raw_date or value is None:
            continue
        d = date.fromisoformat(str(raw_date)[:10])
        out.append(Dividend(registry_close_date=d, value=float(value), currency=str(currency)))

    assert len(out) == 2
    assert out[0].value == 301.74
    assert out[0].registry_close_date == date(2024, 7, 5)
    assert out[1].value == 150.0
    assert out[1].registry_close_date == date(2025, 5, 16)


def test_old_value_field_still_works():
    """Fallback to 'value' field for future compatibility."""
    columns = ["secid", "registryclosedate", "value", "currencyid"]
    data = [["SBER", "2024-07-05", 25.0, "RUB"]]

    from stocks_bot.moex import _rows_from_block
    from stocks_bot.db import Dividend
    rows = _rows_from_block({"dividends": {"columns": columns, "data": data}}, "dividends")
    row = rows[0]
    value = (
        row.get("dividendnetperms")
        or row.get("DIVIDENDNETPERMS")
        or row.get("value")
        or row.get("VALUE")
    )
    assert value == 25.0


def test_missing_date_skipped():
    columns = ["secid", "registryclosedate", "dividendnetperms", "currencyid"]
    data = [
        ["PLZL", None, 100.0, "RUB"],
        ["PLZL", "2024-07-05", 301.74, "RUB"],
    ]
    from stocks_bot.moex import _rows_from_block
    rows = _rows_from_block({"dividends": {"columns": columns, "data": data}}, "dividends")
    parsed = []
    for row in rows:
        raw_date = row.get("registryclosedate")
        value = row.get("dividendnetperms")
        if not raw_date or value is None:
            continue
        parsed.append(row)
    assert len(parsed) == 1
    assert parsed[0]["registryclosedate"] == "2024-07-05"
