from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timezone

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id        INTEGER PRIMARY KEY,
    commission_pct REAL    NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS purchases (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    secid          TEXT    NOT NULL,
    qty            REAL    NOT NULL,
    price          REAL    NOT NULL,
    commission_pct REAL    NOT NULL DEFAULT 0,
    purchased_at   TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_purchases_user_secid ON purchases(user_id, secid);

CREATE TABLE IF NOT EXISTS aliases (
    user_id  INTEGER NOT NULL,
    raw_name TEXT    NOT NULL,
    secid    TEXT    NOT NULL,
    PRIMARY KEY (user_id, raw_name)
);

CREATE TABLE IF NOT EXISTS securities_cache (
    secid       TEXT PRIMARY KEY,
    shortname   TEXT NOT NULL,
    secname     TEXT NOT NULL,
    board       TEXT NOT NULL,
    type        TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dividends_cache (
    secid               TEXT NOT NULL,
    registry_close_date TEXT NOT NULL,
    value               REAL NOT NULL,
    currency            TEXT NOT NULL DEFAULT 'RUB',
    PRIMARY KEY (secid, registry_close_date)
);

CREATE TABLE IF NOT EXISTS dividends_meta (
    secid      TEXT PRIMARY KEY,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS securities_meta (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    updated_at TEXT NOT NULL
);
"""


@dataclass
class Security:
    secid: str
    shortname: str
    secname: str
    board: str
    type: str


@dataclass
class Purchase:
    id: int
    user_id: int
    secid: str
    qty: float
    price: float
    commission_pct: float
    purchased_at: date


@dataclass
class Dividend:
    registry_close_date: date
    value: float
    currency: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_security(row: aiosqlite.Row) -> Security:
    return Security(
        secid=row["secid"],
        shortname=row["shortname"],
        secname=row["secname"],
        board=row["board"],
        type=row["type"],
    )


def _row_to_purchase(row: aiosqlite.Row) -> Purchase:
    return Purchase(
        id=row["id"],
        user_id=row["user_id"],
        secid=row["secid"],
        qty=row["qty"],
        price=row["price"],
        commission_pct=row["commission_pct"],
        purchased_at=date.fromisoformat(row["purchased_at"]),
    )


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "Database not connected"
        return self._conn

    # ---- users ----
    async def get_commission(self, user_id: int) -> float:
        async with self.conn.execute(
            "SELECT commission_pct FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return float(row["commission_pct"]) if row else 0.0

    async def set_commission(self, user_id: int, pct: float) -> None:
        await self.conn.execute(
            "INSERT INTO users(user_id, commission_pct) VALUES(?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET commission_pct = excluded.commission_pct",
            (user_id, pct),
        )
        await self.conn.commit()

    # ---- aliases ----
    async def get_alias(self, user_id: int, raw_name: str) -> str | None:
        async with self.conn.execute(
            "SELECT secid FROM aliases WHERE user_id = ? AND raw_name = ?",
            (user_id, raw_name.lower()),
        ) as cur:
            row = await cur.fetchone()
        return row["secid"] if row else None

    async def set_alias(self, user_id: int, raw_name: str, secid: str) -> None:
        await self.conn.execute(
            "INSERT INTO aliases(user_id, raw_name, secid) VALUES(?, ?, ?) "
            "ON CONFLICT(user_id, raw_name) DO UPDATE SET secid = excluded.secid",
            (user_id, raw_name.lower(), secid),
        )
        await self.conn.commit()

    # ---- purchases ----
    async def add_purchase(
        self,
        user_id: int,
        secid: str,
        qty: float,
        price: float,
        commission_pct: float,
        purchased_at: date,
    ) -> int:
        cur = await self.conn.execute(
            "INSERT INTO purchases(user_id, secid, qty, price, commission_pct, purchased_at) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (user_id, secid, qty, price, commission_pct, purchased_at.isoformat()),
        )
        await self.conn.commit()
        return cur.lastrowid or 0

    async def list_purchases(self, user_id: int, secid: str) -> list[Purchase]:
        async with self.conn.execute(
            "SELECT * FROM purchases WHERE user_id = ? AND secid = ? ORDER BY purchased_at, id",
            (user_id, secid),
        ) as cur:
            rows = await cur.fetchall()
        return [_row_to_purchase(r) for r in rows]

    async def list_user_secids(self, user_id: int) -> list[str]:
        async with self.conn.execute(
            "SELECT DISTINCT secid FROM purchases WHERE user_id = ?", (user_id,)
        ) as cur:
            rows = await cur.fetchall()
        return [r["secid"] for r in rows]

    async def list_all_secids(self) -> list[str]:
        async with self.conn.execute("SELECT DISTINCT secid FROM purchases") as cur:
            rows = await cur.fetchall()
        return [r["secid"] for r in rows]

    async def get_purchase(self, purchase_id: int, user_id: int) -> Purchase | None:
        async with self.conn.execute(
            "SELECT * FROM purchases WHERE id = ? AND user_id = ?",
            (purchase_id, user_id),
        ) as cur:
            row = await cur.fetchone()
        return _row_to_purchase(row) if row else None

    async def delete_purchase(self, purchase_id: int, user_id: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM purchases WHERE id = ? AND user_id = ?",
            (purchase_id, user_id),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def update_purchase(
        self,
        purchase_id: int,
        user_id: int,
        qty: float,
        price: float,
        purchased_at: date,
    ) -> bool:
        cur = await self.conn.execute(
            "UPDATE purchases SET qty = ?, price = ?, purchased_at = ? "
            "WHERE id = ? AND user_id = ?",
            (qty, price, purchased_at.isoformat(), purchase_id, user_id),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    # ---- securities ----
    async def replace_securities(self, securities: list[Security]) -> None:
        await self.conn.execute("DELETE FROM securities_cache")
        await self.conn.executemany(
            "INSERT INTO securities_cache(secid, shortname, secname, board, type, updated_at) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            [
                (s.secid, s.shortname, s.secname, s.board, s.type, _now_iso())
                for s in securities
            ],
        )
        await self.conn.execute(
            "INSERT INTO securities_meta(id, updated_at) VALUES(1, ?) "
            "ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at",
            (_now_iso(),),
        )
        await self.conn.commit()

    async def securities_updated_at(self) -> datetime | None:
        async with self.conn.execute(
            "SELECT updated_at FROM securities_meta WHERE id = 1"
        ) as cur:
            row = await cur.fetchone()
        return datetime.fromisoformat(row["updated_at"]) if row else None

    async def all_securities(self) -> list[Security]:
        async with self.conn.execute(
            "SELECT * FROM securities_cache"
        ) as cur:
            rows = await cur.fetchall()
        return [_row_to_security(r) for r in rows]

    async def get_security(self, secid: str) -> Security | None:
        async with self.conn.execute(
            "SELECT * FROM securities_cache WHERE secid = ?", (secid,)
        ) as cur:
            row = await cur.fetchone()
        return _row_to_security(row) if row else None

    # ---- dividends ----
    async def replace_dividends(self, secid: str, dividends: list[Dividend]) -> None:
        await self.conn.execute(
            "DELETE FROM dividends_cache WHERE secid = ?", (secid,)
        )
        await self.conn.executemany(
            "INSERT INTO dividends_cache(secid, registry_close_date, value, currency) "
            "VALUES(?, ?, ?, ?)",
            [
                (secid, d.registry_close_date.isoformat(), d.value, d.currency)
                for d in dividends
            ],
        )
        await self.conn.execute(
            "INSERT INTO dividends_meta(secid, updated_at) VALUES(?, ?) "
            "ON CONFLICT(secid) DO UPDATE SET updated_at = excluded.updated_at",
            (secid, _now_iso()),
        )
        await self.conn.commit()

    async def dividends_updated_at(self, secid: str) -> datetime | None:
        async with self.conn.execute(
            "SELECT updated_at FROM dividends_meta WHERE secid = ?", (secid,)
        ) as cur:
            row = await cur.fetchone()
        return datetime.fromisoformat(row["updated_at"]) if row else None

    async def get_dividends(self, secid: str) -> list[Dividend]:
        async with self.conn.execute(
            "SELECT registry_close_date, value, currency FROM dividends_cache "
            "WHERE secid = ? ORDER BY registry_close_date",
            (secid,),
        ) as cur:
            rows = await cur.fetchall()
        return [
            Dividend(
                registry_close_date=date.fromisoformat(r["registry_close_date"]),
                value=r["value"],
                currency=r["currency"],
            )
            for r in rows
        ]
