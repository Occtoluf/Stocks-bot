from __future__ import annotations

import os
import tempfile

import pytest

from stocks_bot.db import Database, Security
from stocks_bot.matcher import match_security


@pytest.fixture
async def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = Database(path)
    await database.connect()
    securities = [
        Security("SBER", "Сбербанк", "Сбербанк России ПАО ао", "TQBR", "share"),
        Security("SBERP", "Сбербанк-п", "Сбербанк России ПАО ап", "TQBR", "share"),
        Security("GAZP", "Газпром", "Газпром ПАО ао", "TQBR", "share"),
        Security("LKOH", "ЛУКОЙЛ", "ЛУКОЙЛ ПАО ао", "TQBR", "share"),
        Security("GLDRUB_TOM", "Золото", "Золото расчётами TOM", "CETS", "currency"),
    ]
    await database.replace_securities(securities)
    try:
        yield database
    finally:
        await database.close()
        os.unlink(path)


async def test_exact_ticker(db):
    r = await match_security(db, 1, "SBER")
    assert r.picked is not None
    assert r.picked.secid == "SBER"


async def test_exact_ticker_lowercase(db):
    r = await match_security(db, 1, "gldrub_tom")
    assert r.picked is not None
    assert r.picked.secid == "GLDRUB_TOM"


async def test_unique_name_picked(db):
    r = await match_security(db, 1, "Газпром")
    assert r.picked is not None
    assert r.picked.secid == "GAZP"


async def test_ambiguous_sber(db):
    r = await match_security(db, 1, "Сбер")
    # SBER и SBERP оба подходят — ждём уточнения
    assert r.picked is None
    assert r.suggestions is not None
    secids = {s.secid for s in r.suggestions}
    assert "SBER" in secids
    assert "SBERP" in secids


async def test_alias_remembers_choice(db):
    await db.set_alias(1, "сбер", "SBER")
    r = await match_security(db, 1, "Сбер")
    assert r.picked is not None
    assert r.picked.secid == "SBER"


async def test_alias_is_per_user(db):
    await db.set_alias(1, "сбер", "SBER")
    r = await match_security(db, 2, "Сбер")
    # другой user — алиас не применяется, снова неоднозначно
    assert r.picked is None


async def test_unknown_name_no_pick(db):
    r = await match_security(db, 1, "xyzqqq12345zz")
    # ни одна бумага уверенно не подходит — автовыбор не делаем
    assert r.picked is None
