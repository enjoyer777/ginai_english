# Архитектура (Deliverable #4)

## Компоненты и потоки

```mermaid
flowchart LR
    subgraph User["Внешние участники"]
        client["Клиент<br/>(Telegram)"]
        managers["Чат менеджеров<br/>(Telegram group)"]
    end

    subgraph VPS["VPS (Docker)"]
        direction TB
        bot[["Python-процесс бота<br/>(aiogram)"]]
        sqlite[("SQLite<br/>state.db")]
        cache[(KB cache<br/>TTL 10 мин)]
        bot --- sqlite
        bot --- cache
    end

    subgraph Cloud["Внешние сервисы"]
        openai[OpenAI<br/>gpt-4o-mini]
        ydisk[Яндекс.Диск<br/>kb.xlsx]
        bitrix[Bitrix24<br/>входящий вебхук]
    end

    client <-->|сообщения| bot
    bot -->|уведомление<br/>в раб. часы| managers
    bot -->|tool calls| openai
    cache -->|обновление<br/>каждые 10 мин| ydisk
    bot -->|crm.deal.add/update<br/>сразу, всегда| bitrix
```

## Поток обработки сообщения

```mermaid
sequenceDiagram
    autonumber
    participant C as Клиент
    participant B as aiogram bot
    participant G as Guardrails
    participant L as OpenAI
    participant K as KB cache
    participant S as SQLite
    participant X as Bitrix24
    participant M as Чат менеджеров

    C->>B: Текст («Хочу IELTS к лету»)
    B->>G: Проверка jailbreak / мусор
    alt Триггер фильтра
        B-->>C: Шаблонный ответ
    else Нормальный текст
        B->>S: append message
        B->>K: get_snapshot()
        B->>L: chat(messages, tools)
        L-->>B: tool_calls: update_lead_profile, mark_hot_lead
        B->>S: update lead_profile, mark hot
        B->>L: summarize_for_crm(history, profile)
        L-->>B: «Хочет IELTS к лету, B1, готов в мае»
        B->>X: crm.contact.add → crm.deal.add (или update по UF_CRM_TG_USER_ID)
        X-->>B: deal_id
        B->>S: save_deal_ref
        alt Рабочее время
            B->>M: «🔥 Новый горячий лид» + ссылка на сделку
        else Нерабочее время
            B-->>C: «Менеджер свяжется в раб. часы»
        end
        B->>L: финальный текст ответа клиенту
        L-->>B: «Передал менеджеру, он свяжется»
        B-->>C: ответ
    end
```

## Стек одной фразой

`Python 3.11 · aiogram 3 · OpenAI gpt-4o-mini (function calling) · Яндекс.Диск REST → openpyxl · SQLite (aiosqlite) · Bitrix24 webhook · Docker · GitHub`

## Ключевые архитектурные решения

| Решение | Альтернатива | Почему так |
|---|---|---|
| Function calling, не отдельный классификатор интентов | Промпт-классификатор → промпт-ответчик | Меньше промптов = меньше дрейфа; модель сама решает, когда дернуть KB |
| Полная xlsx-таблица в кэше памяти | Векторная БД / RAG | 5-8 курсов умещается в один tool-ответ; векторка = лишняя зависимость |
| SQLite на volume | Redis / Postgres | NFR-13 запрещает лишние сервисы; одного процесса хватает |
| Один контейнер | Микросервисы | Учебный проект, ~200 сообщений/мин потолок; нет смысла дробить |
| Дедуп сделок через `UF_CRM_TG_USER_ID` + локальная таблица `deals` | Только Bitrix-поиск | Дешевле и быстрее: при повторном заходе клиента сразу знаем deal_id |
| Дедуп уведомлений в чат | Без дедупа | FR-9.4: не засоряем чат менеджеров одинаковыми сигналами по одному клиенту |
