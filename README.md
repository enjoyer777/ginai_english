# school_english_pro — AI-ассистент в Telegram

AI-ассистент для онлайн-школы английского. Отвечает на вопросы клиентов 24/7, квалифицирует горячих лидов и пушит их в Bitrix24, в рабочее время дублирует уведомлением в чат менеджеров.

📄 Бизнес-требования: [business_requirements.md](business_requirements.md)
📄 Техническое задание: [technical_specification.md](technical_specification.md)
📄 Промпты: [prompts_doc.md](prompts_doc.md)
📄 Ручные тест-кейсы: [tests/manual_test_cases.md](tests/manual_test_cases.md)

---

## Архитектура

```
Telegram ↔ aiogram bot ↔ OpenAI gpt-4o-mini (function calling)
                ↓                ↓
           SQLite state    Yandex.Disk (xlsx KB)
                ↓
           Bitrix24 webhook  →  чат менеджеров (рабочее время)
```

Один процесс Python в одном Docker-контейнере на VPS. SQLite на volume `./data`. Подробнее — раздел 2 ТЗ.

---

## Что нужно для запуска

| # | Доступ | Где взять |
|---|---|---|
| 1 | VPS (Linux, ≥1 vCPU, ≥2 GB RAM) | hetzner / timeweb / ... |
| 2 | Telegram Bot Token | `@BotFather` → `/newbot` |
| 3 | Telegram Chat ID менеджеров | добавить бота в чат, отправить сообщение, посмотреть логи |
| 4 | OpenAI API Key | platform.openai.com → API Keys |
| 5 | Yandex.Disk OAuth Token | https://yandex.ru/dev/disk/poligon/ |
| 6 | Bitrix24 входящий вебхук | портал → Разработчикам → Другое → Входящий вебхук, права `crm` |
| 7 | Кастомное поле сделки `UF_CRM_TG_USER_ID` (тип «Строка») | портал Bitrix вручную, **до** первого запуска (используется для дедупликации FR-6.2) |

---

## Структура базы знаний (xlsx на Я.Диске)

Файл (по умолчанию `/school_english_pro/kb.xlsx`) содержит 5 листов. Заказчик правит данные в любом редакторе (Excel / Я.Документы / WPS), сохраняет, перезагружает на Я.Диск с тем же путём — бот подхватит изменения за ≤10 минут (TTL кэша).

**Лист `Курсы`**

| id | name | direction | levels | duration_weeks | format | price_rub | installment | description | nearest_start |
|---|---|---|---|---|---|---|---|---|---|
| 1 | English for IT | работа | A2,B1 | 16 | онлайн групповой | 36000 | да | для разработчиков и тестировщиков | 2026-06-01 |

`direction` ∈ {работа, переезд, путешествия, для себя}. `levels` — через запятую из {A0-A1, A2, B1, B2}. `installment` ∈ {да, нет}.

**Лист `Расписание`**

| course_id | start_date | days_time | teacher_name | seats_left |
|---|---|---|---|---|
| 1 | 2026-06-01 | Пн/Ср 19:00 МСК | Анна Иванова | 4 |

**Лист `Преподаватели`**

| name | experience_years | specialization | bio |
|---|---|---|---|
| Анна Иванова | 8 | IELTS, business English | CELTA, опыт в EPAM |

**Лист `FAQ`**

| question | answer |
|---|---|
| Можно ли поменять группу? | Да, в течение первой недели курса |

**Лист `Настройки`** (две колонки `key | value`)

| key | value |
|---|---|
| working_hours_mon | 09:00-19:00 |
| working_hours_tue | 09:00-19:00 |
| working_hours_wed | 09:00-19:00 |
| working_hours_thu | 09:00-19:00 |
| working_hours_fri | 09:00-19:00 |
| working_hours_sat | 10:00-15:00 |
| working_hours_sun |  |
| greeting_text | Здравствуйте! Я — AI-ассистент школы school_english_pro... |
| pii_disclaimer | Если оставите контакт — передам менеджеру для связи. |
| contact_phone | +7 999 000 00 00 |
| contact_email | hello@school-english-pro.example |

Пустое значение `working_hours_sun` = выходной.

---

## Запуск локально (для разработки)

```bash
# 1. Зависимости
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 2. Конфиг
cp .env.example .env
# Открой .env и заполни секреты

# 3. Запуск
python -m app.main
```

---

## Запуск на VPS через Docker

Авто-рестарт при сбоях — `restart: unless-stopped` в `docker-compose.yml`. Состояние и логи лежат в `./data` (mount внутрь контейнера).

### CI/CD: GitHub Actions → VPS

В репозитории настроен workflow [.github/workflows/deploy.yml](.github/workflows/deploy.yml):
- триггер: push в `main` или ручной запуск через `workflow_dispatch`;
- что делает: `rsync` кодовой базы на VPS (без `.env` и `./data`) → `docker compose up -d --build` → выводит последние логи бота.

**Требуемые GitHub Secrets** (в Settings → Secrets and variables → Actions):

| Secret | Значение |
|---|---|
| `VPS_HOST` | IP или DNS-имя VPS |
| `VPS_USER` | SSH-пользователь на VPS (с правом на докер) |
| `VPS_SSH_PRIVATE_KEY` | приватный SSH-ключ (полный текст, включая BEGIN/END-маркеры) |
| `VPS_KNOWN_HOSTS` | вывод `ssh-keyscan -H <host>` (опционально — без него CI делает keyscan на лету) |
| `VPS_DEPLOY_PATH` | абсолютный путь на VPS, например `/home/enjoyer777/ginai_english` |

**Bootstrap VPS** (один раз перед первым деплоем):

```bash
ssh <user>@<host>
mkdir -p /home/<user>/ginai_english/data
cd /home/<user>/ginai_english
# скопировать .env.example в .env и заполнить
nano .env
```

После этого любой push в `main` → автодеплой. Если `.env` пустой/отсутствует, шаг `Build and restart Docker` упадёт с понятным сообщением — поправьте `.env` и перезапустите workflow вручную.

### Запуск вручную (без CI)

```bash
ssh <user>@<host>
cd /home/<user>/ginai_english
docker compose up -d --build
docker compose logs -f bot
```

### Прокси через Xray для обхода блокировок (важно при размещении в РФ)

Бот ходит к двум сервисам, которые с RU-VPS работают плохо или вообще не работают:

| Сервис | Что не так на RU-IP | Лечение |
|---|---|---|
| `api.telegram.org` | RU-провайдер режет часть IP-адресов Telegram | По умолчанию: `extra_hosts` в [docker-compose.yml](docker-compose.yml) пиннит DC4. Если перестанет помогать — `TELEGRAM_PROXY` |
| `api.openai.com` | OpenAI возвращает `403 unsupported_country_region_territory` | **`OPENAI_PROXY` обязателен**, иначе LLM-ответы падают |

Готовый fallback — Xray-сайдкар: терминирует SOCKS5 локально и тоннелирует только нужные домены через твой не-RU VPS, остальное (Я.Диск, Битрикс) — напрямую.

**Включение** (один раз):

1. Скопируй [`xray-config.example.json`](xray-config.example.json) → `xray-config.json` на VPS, подставь UUID/`publicKey`/`shortId` от своего Xray-сервера (или замени блок `outbounds[0]` на свой VLESS/Trojan/VMess клиент-конфиг).
2. Раскомментируй секцию `xray:` в `docker-compose.yml`.
3. В `.env` на VPS добавь:
   ```env
   TELEGRAM_PROXY=socks5://xray:1080
   OPENAI_PROXY=socks5://xray:1080
   ```
   `OPENAI_PROXY` — обязательно при RU-хостинге; `TELEGRAM_PROXY` — пока работает `extra_hosts`, можно не задавать (тогда бот пойдёт в TG напрямую).
4. Перезапусти: `docker compose up -d --build`.

Файл `xray-config.json` лежит в `.gitignore` и исключён из rsync — реальные ключи в репозиторий не утекают и не перетираются деплоем.

Выключить прокси — стереть `TELEGRAM_PROXY`/`OPENAI_PROXY` в `.env` и перезапустить; сайдкар можно потушить через `docker compose stop xray`.

---

## Тесты

```bash
pytest
```

Юнит-тесты в `tests/unit/` — рабочие часы, дедуп сделок, парсинг xlsx, кэш. Ручные сценарии приёмки — [tests/manual_test_cases.md](tests/manual_test_cases.md).

## Сброс памяти бота (для отладки и повторных прогонов)

CLI-скрипт [app/scripts/reset_memory.py](app/scripts/reset_memory.py) запускается внутри контейнера. С VPS:

```bash
cd /home/enjoyer777/ginai_english

# 1. Список всех известных пользователей (id, username, телефон, кол-во сообщений, hot)
docker compose exec bot python -m app.scripts.reset_memory

# 2. Что удалится у конкретного юзера, без удаления
docker compose exec bot python -m app.scripts.reset_memory --user 128657277 --dry-run

# 3. Реально вычистить одного юзера
docker compose exec bot python -m app.scripts.reset_memory --user 128657277

# 4. Снести ВСЮ память (требует --force как защиту от случайностей)
docker compose exec bot python -m app.scripts.reset_memory --all --force
```

Что чистится: история диалога, профиль квалификации, локальная ссылка на сделку Bitrix24, дедуп уведомлений, запись о пользователе. Сама сделка в Битрикс24 при этом **не удаляется** — её надо стереть в CRM руками, если хочешь полностью чистый прогон (иначе при следующем hot-интенте бот создаст новую сделку рядом со старой).

---

## Структура репозитория

```
ginai_english/
├── app/                      # Python-код бота
│   ├── main.py               # entrypoint, запуск aiogram polling
│   ├── config.py             # pydantic-settings, чтение .env
│   ├── bot/                  # aiogram handlers, клавиатуры, middlewares
│   ├── dialog/               # «мозг» бота: engine, qualification, guardrails, prompts
│   ├── kb/                   # клиент Я.Диска, парсер xlsx, TTL-кэш
│   ├── llm/                  # обёртка над OpenAI с function calling
│   ├── crm/                  # клиент Bitrix24 + сборка payload сделки
│   ├── notifications/        # уведомления в чат менеджеров
│   ├── state/                # SQLite, репозиторий диалогов
│   └── utils/                # рабочие часы, логирование, время МСК
├── tests/
│   ├── unit/
│   └── manual_test_cases.md  # ручные сценарии приёмки (Deliverable #8)
├── docs/                     # Deliverables 4–6 (диаграмма, скриншоты, видео)
├── business_requirements.md
├── technical_specification.md
├── prompts_doc.md            # все промпты с комментариями (Deliverable #7)
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── .env.example
└── .gitignore
```

---

## Лицензия

Internal / учебный проект.
