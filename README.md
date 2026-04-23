# Stocks Bot

Минимальный Telegram-бот для учёта покупок акций МосБиржи и золота `GLDRUB_TOM`,
с расчётом реального дивидендного дохода на цену каждой покупки.

## Возможности
- Свободный ввод покупок: `Сбер 10х315`, `SBER 5x320.5`, `Gold 1x9000`.
- Команда `/dividends Сбер` — дата первой покупки, средняя цена, средний %, история.
- Управление: `/list`, `/delete <id>`, `/edit <id> <qty>x<price>`, `/commission <pct>`.
- Распознавание тикера через MOEX ISS + fuzzy-матч; при неоднозначности —
  inline-выбор, далее запоминается как алиас пользователя.
- Дивиденды и справочник бумаг подтягиваются из публичного API
  `iss.moex.com` и обновляются раз в сутки фоновой задачей.

## Запуск

1. Получить токен у [@BotFather](https://t.me/BotFather).
2. `cp .env.example .env` и вставить токен.
3. `docker compose up --build -d`.

Локально без Docker:

```bash
pip install -e .
BOT_TOKEN=... python -m stocks_bot.main
```

## Тесты

```bash
pip install -e ".[dev]"
pytest
```

## Формула дивиденда на покупку

```
effective_price = price * (1 + commission_pct / 100)
divs            = SUM(d.value for d if d.registry_close_date >= purchased_at)
percent         = divs / effective_price * 100
```
