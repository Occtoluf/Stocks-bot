from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router()

HELP_TEXT = (
    "<b>Stocks Bot</b> — учёт покупок и реального дивидендного дохода.\n\n"
    "<b>Ввод покупки</b>:\n"
    "<code>Сбер 10х315</code> — сегодняшняя дата\n"
    "<code>Сбер 10х315 1.1.2025</code> — с указанием даты\n"
    "Поддерживается также формат <code>SBER 5x320.5</code>, <code>Gold 1x9000</code>.\n\n"
    "<b>Команды</b>\n"
    "/dividends <i>название</i> — отчёт по бумаге\n"
    "/list — все бумаги с количеством и средней ценой\n"
    "/delete <i>id</i> — удалить покупку\n"
    "/edit <i>id qtyxprice [дата]</i> — изменить покупку "
    "(если дата не указана — остаётся прежняя)\n"
    "/commission <i>pct</i> — задать комиссию брокера в % (по умолчанию 0)\n"
    "/help — эта справка"
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)
