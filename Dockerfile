FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY src ./src

RUN mkdir -p /app/data
VOLUME ["/app/data"]

CMD ["python", "-m", "stocks_bot.main"]
