from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .config import load_settings
from .db import Database
from .handlers import build_router
from .moex import MoexClient
from .scheduler import ensure_securities_loaded, start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)


async def amain() -> None:
    settings = load_settings()

    db = Database(settings.db_path)
    await db.connect()

    moex = MoexClient()

    bot = Bot(
        settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp["db"] = db
    dp["moex"] = moex
    dp.include_router(build_router())

    await ensure_securities_loaded(db, moex)
    scheduler = start_scheduler(db, moex)

    try:
        log.info("bot started")
        await dp.start_polling(bot, db=db, moex=moex)
    finally:
        scheduler.shutdown(wait=False)
        await moex.aclose()
        await db.close()
        await bot.session.close()


def main() -> None:
    try:
        asyncio.run(amain())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
