from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .db import Database
from .moex import MoexClient

log = logging.getLogger(__name__)

SECURITIES_STALE_HOURS = 24


async def refresh_securities(db: Database, moex: MoexClient) -> None:
    log.info("refreshing securities cache")
    try:
        securities = await moex.fetch_all_securities()
    except Exception as e:
        log.exception("failed to fetch securities: %s", e)
        return
    if not securities:
        log.warning("MOEX returned empty securities list; skipping replace")
        return
    await db.replace_securities(securities)
    log.info("securities cache updated: %d entries", len(securities))


async def refresh_dividends_for_tracked(db: Database, moex: MoexClient) -> None:
    secids = await db.list_all_secids()
    log.info("refreshing dividends for %d tracked securities", len(secids))
    for secid in secids:
        try:
            divs = await moex.fetch_dividends(secid)
        except Exception as e:
            log.warning("dividends fetch failed for %s: %s", secid, e)
            continue
        await db.replace_dividends(secid, divs)


async def ensure_securities_loaded(db: Database, moex: MoexClient) -> None:
    updated = await db.securities_updated_at()
    if updated is not None:
        age = datetime.now(timezone.utc) - updated
        if age < timedelta(hours=SECURITIES_STALE_HOURS):
            return
    await refresh_securities(db, moex)


def start_scheduler(db: Database, moex: MoexClient) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(
        refresh_securities,
        CronTrigger(hour=3, minute=0),
        args=(db, moex),
        id="refresh_securities",
        replace_existing=True,
    )
    scheduler.add_job(
        refresh_dividends_for_tracked,
        CronTrigger(hour=3, minute=15),
        args=(db, moex),
        id="refresh_dividends",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler
