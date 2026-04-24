from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .db import Database
from .tbank import TBankAuthError, TBankClient

log = logging.getLogger(__name__)

SECURITIES_STALE_HOURS = 24
DIVIDENDS_HISTORY_MARGIN_DAYS = 365 * 5
DIVIDENDS_FUTURE_MARGIN_DAYS = 365


async def refresh_securities(db: Database, tbank: TBankClient) -> None:
    log.info("refreshing securities cache from T-Invest")
    try:
        securities = await tbank.fetch_shares()
    except TBankAuthError:
        log.error("T-Invest token invalid; skipping refresh")
        return
    except Exception as e:
        log.exception("failed to fetch shares: %s", e)
        return
    if not securities:
        log.warning("T-Invest returned empty securities list; skipping replace")
        return
    await db.replace_securities(securities)
    log.info("securities cache updated: %d entries", len(securities))


async def refresh_dividends_for_tracked(db: Database, tbank: TBankClient) -> None:
    secids = await db.list_all_secids()
    log.info("refreshing dividends for %d tracked securities", len(secids))
    today = date.today()
    from_date = today - timedelta(days=DIVIDENDS_HISTORY_MARGIN_DAYS)
    to_date = today + timedelta(days=DIVIDENDS_FUTURE_MARGIN_DAYS)
    for secid in secids:
        sec = await db.get_security(secid)
        if sec is None or not sec.figi:
            log.warning("no FIGI cached for %s; skipping dividends fetch", secid)
            continue
        try:
            divs = await tbank.fetch_dividends(sec.figi, from_date, to_date)
        except TBankAuthError:
            log.error("T-Invest token invalid; aborting dividends refresh")
            return
        except Exception as e:
            log.warning("dividends fetch failed for %s: %s", secid, e)
            continue
        if divs:
            await db.replace_dividends(secid, divs)


async def ensure_securities_loaded(db: Database, tbank: TBankClient) -> None:
    updated = await db.securities_updated_at()
    if updated is not None:
        age = datetime.now(timezone.utc) - updated
        if age < timedelta(hours=SECURITIES_STALE_HOURS):
            return
    await refresh_securities(db, tbank)


def start_scheduler(db: Database, tbank: TBankClient) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(
        refresh_securities,
        CronTrigger(hour=3, minute=0),
        args=(db, tbank),
        id="refresh_securities",
        replace_existing=True,
    )
    scheduler.add_job(
        refresh_dividends_for_tracked,
        CronTrigger(hour=3, minute=15),
        args=(db, tbank),
        id="refresh_dividends",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler
