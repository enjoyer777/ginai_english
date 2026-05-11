"""Описания tools для function calling OpenAI.

LLM сама решает, когда вызвать какой инструмент. Бот выполняет, кладёт результат
в историю и делает следующий step. Максимум LLM_MAX_TOOL_ITERATIONS итераций.
"""

from __future__ import annotations

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_courses",
            "description": (
                "Список курсов школы с ценами, длительностью, форматом и описанием. "
                "Вызывай, когда клиент спрашивает про программы/цены/уровни/направления. "
                "Можно фильтровать по направлению или уровню."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["работа", "переезд", "путешествия", "для себя"],
                        "description": "Фильтр по направлению. Если клиент не уточнил — не передавай.",
                    },
                    "level": {
                        "type": "string",
                        "enum": ["A0-A1", "A2", "B1", "B2"],
                        "description": "Фильтр по уровню. Если клиент не уточнил — не передавай.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_schedule",
            "description": (
                "Расписание ближайших стартов курсов: даты, дни/время, преподаватель, "
                "сколько мест осталось. Вызывай, когда клиент спрашивает «когда стартует» / "
                "«на какие даты записаться» / «есть ли места»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {
                        "type": "string",
                        "description": "ID курса. Если не известен — не передавай, верну все.",
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_teachers",
            "description": "Список преподавателей: имена, опыт, специализация, био.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_faq",
            "description": (
                "Список FAQ-вопросов и ответов из базы знаний. Вызывай, если стандартные "
                "tools (courses/schedule/teachers) не дают ответа — может быть нестандартная тема."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_lead_profile",
            "description": (
                "Записать в профиль клиента слоты квалификации, как только он сообщил новый "
                "факт о себе. Вызывай ВСЕГДА, не дожидаясь, что клиент перечислит всё сразу. "
                "Каждое новое уточнение — отдельный вызов."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": (
                            "Цель обучения: 'IELTS' / 'переезд' / 'работа' / 'путешествия' / "
                            "'для себя' или своими словами."
                        ),
                    },
                    "level_self": {
                        "type": "string",
                        "description": "Уровень своими словами: 'с нуля', 'школьный', 'A2', 'читаю Гарри Поттера'.",
                    },
                    "horizon": {
                        "type": "string",
                        "description": (
                            "Когда планирует начать: 'в этом месяце', 'к лету', 'через полгода', "
                            "'пока изучаю варианты'."
                        ),
                    },
                    "readiness": {
                        "type": "string",
                        "description": "'изучает варианты' / 'готов записываться' / 'готов оплатить'.",
                    },
                    "first_name": {
                        "type": "string",
                        "description": (
                            "Имя клиента, если он назвал его в диалоге явно. "
                            "Telegram first_name бот уже знает — записывай только если "
                            "клиент сам сказал, как к нему обращаться."
                        ),
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_hot_lead",
            "description": (
                "Пометить клиента как ГОРЯЧЕГО и инициировать передачу в CRM. "
                "Вызывай, когда из диалога ясно, что клиент готов стартовать в течение ~1 месяца, "
                "ИЛИ явно говорит про оплату/запись. Не вызывай для холодных «расскажите про курсы»."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Короткое обоснование, почему лид горячий (для лога).",
                    }
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_handover",
            "description": (
                "Клиент явно попросил связать с менеджером (написал «соедините с человеком», "
                "«хочу с менеджером», «можно живого человека?»). Запускает передачу в CRM "
                "независимо от готовности к покупке. НЕ вызывай по нажатию кнопки — на кнопку "
                "обработка идёт без LLM."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
]
