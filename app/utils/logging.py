from __future__ import annotations

import sys

from loguru import logger

from app.config import settings


def setup_logging() -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
    )

    settings.log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        settings.log_path,
        level=settings.log_level,
        rotation="10 MB",
        retention=5,
        compression="zip",
        encoding="utf-8",
        enqueue=True,
    )
