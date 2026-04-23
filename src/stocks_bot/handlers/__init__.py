from aiogram import Router

from . import common, dividends, manage, purchase


def build_router() -> Router:
    router = Router()
    router.include_router(common.router)
    router.include_router(manage.router)
    router.include_router(dividends.router)
    router.include_router(purchase.router)  # последний — ловит «всё остальное»
    return router
