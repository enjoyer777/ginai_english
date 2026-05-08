"""Бутстрап env-переменных для тестов: иначе pydantic-settings упадёт при импорте app.config."""

import os

os.environ.setdefault("TG_BOT_TOKEN", "test-token")
os.environ.setdefault("MANAGERS_CHAT_ID", "0")
os.environ.setdefault("OPENAI_API_KEY", "test-openai")
os.environ.setdefault("YANDEX_DISK_OAUTH_TOKEN", "test-yandex")
os.environ.setdefault("BITRIX_WEBHOOK_URL", "https://test.bitrix24.ru/rest/1/abc/")
os.environ.setdefault("SQLITE_PATH", "test_data/state.db")
os.environ.setdefault("LOG_PATH", "test_data/logs/bot.log")
