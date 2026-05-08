FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Сначала только manifest — кэш слоёв при пересборке
COPY pyproject.toml README.md ./

# Ставим только runtime-зависимости (без dev)
RUN pip install \
    "aiogram>=3.13.0" \
    "aiosqlite>=0.20.0" \
    "httpx>=0.27.0" \
    "loguru>=0.7.2" \
    "openai>=1.40.0" \
    "openpyxl>=3.1.5" \
    "pydantic>=2.8.0" \
    "pydantic-settings>=2.5.0" \
    "python-dotenv>=1.0.1" \
    "tzdata>=2024.1"

# Код приложения
COPY app ./app

# Состояние и логи — на volume
VOLUME ["/data"]

CMD ["python", "-m", "app.main"]
