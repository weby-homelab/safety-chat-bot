FROM python:3.12-slim

# Встановлення Poetry
RUN pip install poetry==1.8.2

# Робоча директорія
WORKDIR /app

# Копіювання конфігурацій
COPY pyproject.toml poetry.lock* ./

# Встановлення залежностей (без створення віртуального середовища, оскільки це Docker)
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --without dev \
    && pip install --no-deps "aiohttp>=3.14.1"

# Копіювання коду бота
COPY . .

# Запуск
CMD ["python", "-m", "bot.main"]
