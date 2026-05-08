from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфиг приложения. Всё, что есть в .env, валидируется при старте.

    Если хоть одного обязательного значения нет — процесс падает на инициализации,
    а не «странно ведёт себя» в рантайме.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # === Telegram ===
    tg_bot_token: SecretStr
    managers_chat_id: int

    # === OpenAI ===
    openai_api_key: SecretStr
    openai_model: str = "gpt-4o-mini"
    openai_max_tokens: int = 600
    openai_temperature: float = 0.4

    # === Yandex.Disk ===
    yandex_disk_oauth_token: SecretStr
    yandex_disk_file_path: str = "/school_english_pro/kb.xlsx"
    kb_cache_ttl_seconds: int = 600

    # === Bitrix24 ===
    bitrix_webhook_url: str
    bitrix_default_stage: str = "NEW"
    bitrix_tg_user_id_field: str = "UF_CRM_TG_USER_ID"

    # === Storage ===
    sqlite_path: Path = Path("/data/state.db")

    # === Logging ===
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_path: Path = Path("/data/logs/bot.log")

    # === Misc ===
    timezone: str = "Europe/Moscow"
    notify_dedup_window_minutes: int = 60
    llm_max_tool_iterations: int = 3
    history_window_pairs: int = 20


settings = Settings()
