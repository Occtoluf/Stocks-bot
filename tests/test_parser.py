from stocks_bot.parser import parse_purchase, parse_qty_price


def test_parse_cyrillic_x():
    p = parse_purchase("Сбер 10х315")
    assert p is not None
    assert p.name == "Сбер"
    assert p.qty == 10
    assert p.price == 315


def test_parse_latin_x_and_decimals():
    p = parse_purchase("SBER 5x320.5")
    assert p is not None
    assert p.name == "SBER"
    assert p.qty == 5
    assert p.price == 320.5


def test_parse_comma_decimal():
    p = parse_purchase("gldrub_tom 1,5x9000")
    assert p is not None
    assert p.name == "gldrub_tom"
    assert p.qty == 1.5
    assert p.price == 9000


def test_parse_multi_word_name():
    p = parse_purchase("Газпром нефть 10x500")
    assert p is not None
    assert p.name == "Газпром нефть"
    assert p.qty == 10
    assert p.price == 500


def test_parse_times_sign():
    p = parse_purchase("Сбер 10×315")
    assert p is not None
    assert p.qty == 10


def test_parse_garbage():
    assert parse_purchase("просто какой-то текст") is None
    assert parse_purchase("") is None
    assert parse_purchase("10х315") is None  # no name


def test_parse_qty_price():
    p = parse_qty_price("10x320.5")
    assert p is not None
    assert p.qty == 10
    assert p.price == 320.5


def test_parse_qty_price_invalid():
    assert parse_qty_price("Сбер 10x315") is None
    assert parse_qty_price("abc") is None
