FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Prefer IPv4 over IPv6 in getaddrinfo (VPS has no IPv6 connectivity,
# but DNS returns AAAA for api.telegram.org → blocks until timeout).
COPY gai.conf /etc/gai.conf

# Сначала только manifest — кэш слоёв при пересборке
COPY pyproject.toml README.md ./

# Ставим только runtime-зависимости (без dev)
RUN pip install \
    "aiogram>=3.13.0" \
    "aiohttp-socks>=0.10.0" \
    "aiosqlite>=0.20.0" \
    "httpx[socks]>=0.27.0" \
    "loguru>=0.7.2" \
    "openai>=1.40.0" \
    "openpyxl>=3.1.5" \
    "python-calamine>=0.2.3" \
    "pydantic>=2.8.0" \
    "pydantic-settings>=2.5.0" \
    "python-dotenv>=1.0.1" \
    "tzdata>=2024.1" \
    "pytest>=8.3.0" \
    "pytest-asyncio>=0.24.0"

# Код приложения
COPY app ./app

# Тесты + фикстуры (юнит-тесты используют docs/kb_template.xlsx).
# Не нужно для рантайма, но делает образ self-contained для запуска
# `docker compose exec bot pytest tests/unit` без отдельного билда.
COPY tests ./tests
COPY docs ./docs
COPY pyproject.toml ./pyproject.toml

# Состояние и логи — на volume
VOLUME ["/data"]

CMD ["python", "-m", "app.main"]
