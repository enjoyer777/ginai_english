"""Обёртка над OpenAI Chat Completions с поддержкой function calling и циклом tool-use."""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from loguru import logger
from openai import AsyncOpenAI

from app.config import settings
from app.llm.tools import TOOLS

ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]]


class LLMClient:
    def __init__(self) -> None:
        # OPENAI_PROXY: socks5://user:pass@host:port или http://...
        # Нужно, потому что OpenAI отдаёт 403 unsupported_country_region_territory
        # для запросов с RU-IP. Прокси через non-RU выходной узел снимает блок.
        proxy = (os.getenv("OPENAI_PROXY") or "").strip() or None
        http_client: httpx.AsyncClient | None = None
        if proxy:
            http_client = httpx.AsyncClient(proxy=proxy, timeout=60.0)
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            http_client=http_client,
        )

    async def chat(
        self,
        messages: list[dict],
        tool_handlers: dict[str, ToolHandler],
        max_tool_iterations: int | None = None,
    ) -> str:
        """Отправляет messages в OpenAI; если LLM зовёт tools — выполняет и переотправляет.

        messages: список в формате OpenAI (role/content/...).
        tool_handlers: name -> async function, которая принимает dict аргументов и возвращает
                       любое JSON-сериализуемое значение.
        Возвращает финальный текст ассистента.
        """
        max_iter = max_tool_iterations or settings.llm_max_tool_iterations
        working = list(messages)

        for step in range(max_iter):
            response = await self._client.chat.completions.create(
                model=settings.openai_model,
                messages=working,  # type: ignore[arg-type]
                tools=TOOLS,  # type: ignore[arg-type]
                tool_choice="auto",
                temperature=settings.openai_temperature,
                max_tokens=settings.openai_max_tokens,
            )
            choice = response.choices[0]
            msg = choice.message

            if not msg.tool_calls:
                return msg.content or ""

            # Сохраняем сам assistant-message с tool_calls (требование протокола)
            working.append(
                {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )

            # Выполняем все вызванные tools и кладём результаты
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                logger.info("LLM tool call: {} args={}", name, args)
                handler = tool_handlers.get(name)
                if handler is None:
                    result: Any = {"error": f"Unknown tool: {name}"}
                else:
                    try:
                        result = await handler(args)
                    except Exception as e:
                        logger.exception("Tool {} failed", name)
                        result = {"error": str(e)}
                working.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": name,
                        "content": json.dumps(result, ensure_ascii=False, default=str),
                    }
                )

        # Если упёрлись в лимит — заставляем LLM вернуть текст без tools
        logger.warning("LLM tool-use loop hit iteration limit, forcing text response")
        final = await self._client.chat.completions.create(
            model=settings.openai_model,
            messages=working,  # type: ignore[arg-type]
            temperature=settings.openai_temperature,
            max_tokens=settings.openai_max_tokens,
        )
        return final.choices[0].message.content or ""

    async def summarize_for_crm(
        self,
        history_text: str,
        lead_profile_text: str,
    ) -> str:
        """Генерирует короткое резюме (2-4 строки) для поля COMMENTS в Bitrix24."""
        from app.dialog.engine import load_prompt  # локальный импорт, без цикла

        sys_prompt = load_prompt("summary_for_crm.txt")
        messages = [
            {"role": "system", "content": sys_prompt},
            {
                "role": "user",
                "content": (
                    f"=== ПРОФИЛЬ ===\n{lead_profile_text}\n\n"
                    f"=== ИСТОРИЯ ДИАЛОГА ===\n{history_text}"
                ),
            },
        ]
        response = await self._client.chat.completions.create(
            model=settings.openai_model,
            messages=messages,  # type: ignore[arg-type]
            temperature=0.3,
            max_tokens=200,
        )
        return response.choices[0].message.content or "Резюме недоступно."


llm = LLMClient()
