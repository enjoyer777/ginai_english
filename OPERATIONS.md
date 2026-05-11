# Эксплуатация бота — повседневные команды

Шпаргалка для ежедневной работы: посмотреть что происходит, починить, обновить базу знаний, очистить память. Установка с нуля — в [README.md](README.md).

> Все команды запускаются с твоей машины. SSH-алиас на VPS — `onedash2-enjoyer777`. Путь до проекта на VPS — `/home/enjoyer777/ginai_english`. Можешь сохранить два шортката в shell:
> ```bash
> alias bot-ssh='ssh onedash2-enjoyer777'
> alias bot-cd='cd /home/enjoyer777/ginai_english'
> ```

---

## 1. Проверить что бот живой

### 1.1 Статус контейнеров

```bash
ssh onedash2-enjoyer777 "cd /home/enjoyer777/ginai_english && docker compose ps"
```

Должны быть оба `Up`:
- `school-english-pro-bot` — сам бот
- `school-english-pro-xray` — прокси-сайдкар

Если `bot` показывает `Restarting` или `Exit` — смотри логи (раздел 2).

### 1.2 Smoke-проверка из Telegram

Отправь боту `@ginai_english_bot` команду `/start`. Должен ответить приветствием за 1-3 секунды.

### 1.3 Что должно быть в логах после старта

```bash
ssh onedash2-enjoyer777 "cd /home/enjoyer777/ginai_english && docker compose logs --tail=20 bot | grep -E 'authorized|warmed|proxy'"
```

Три ключевые строки:
- `Using outbound proxy for OpenAI: socks5://xray:1080` — прокси к OpenAI подцеплен
- `KB warmed: N courses, M schedule slots` — база знаний из xlsx подгрузилась
- `Bot authorized as @ginai_english_bot` — Telegram принял токен

Если хотя бы одной нет — что-то сломалось.

---

## 2. Логи

### 2.1 Последние строки

```bash
ssh onedash2-enjoyer777 "cd /home/enjoyer777/ginai_english && docker compose logs --tail=60 bot"
```

### 2.2 Поток в реальном времени

```bash
ssh onedash2-enjoyer777 "cd /home/enjoyer777/ginai_english && docker compose logs -f bot"
```

`Ctrl+C` — выход (контейнер продолжит работать).

### 2.3 Только ошибки за последний час

```bash
ssh onedash2-enjoyer777 "cd /home/enjoyer777/ginai_english && docker compose logs --since=1h bot 2>&1 | grep -iE 'error|warn|fail|exception' | tail -30"
```

### 2.4 Логи Xray (если подозреваешь проблемы с прокси)

```bash
ssh onedash2-enjoyer777 "cd /home/enjoyer777/ginai_english && docker compose logs --tail=40 xray"
```

---

## 3. Перезапуски

| Когда | Команда | Что делает |
|---|---|---|
| Поправил `.env` | `docker compose up -d` | Пересоздаёт контейнер с новым окружением, образ не пересобирает |
| Поправил xlsx и нет терпения ждать TTL | `docker compose restart bot` | Перечитывает KB при старте |
| Бот завис на Telegram | `docker compose restart bot` | Чистый рестарт |
| Поправил Python-код локально и хочешь без CI | `docker compose up -d --build` | Пересобирает образ + рестарт (3-4 мин) |
| Глобальная авария | `docker compose down && docker compose up -d --build` | С нуля |

**По-человечески запустить с VPS:**

```bash
ssh onedash2-enjoyer777
cd /home/enjoyer777/ginai_english
docker compose up -d
docker compose logs --tail=15 bot
```

---

## 4. Память бота (SQLite-стейт)

Память — это история диалогов, профили квалификации, ссылки на сделки в Битриксе, дедуп-очередь уведомлений. Хранится в `/data/state.db` внутри контейнера, на хосте — в `/home/enjoyer777/ginai_english/data/state.db`.

### 4.1 Список всех известных пользователей

```bash
ssh onedash2-enjoyer777 "cd /home/enjoyer777/ginai_english && docker compose exec -T bot python -m app.scripts.reset_memory"
```

Покажет таблицу:

```
tg_user_id    username       name        phone           msgs  hot  last_seen
128657277     @enjoyer777    Alexander   +79182324222    46    ✓    2026-05-10 08:24:09
```

Колонка **hot** = ✓ если бот определил пользователя как горячего лида.

### 4.2 Что бы удалилось у конкретного юзера (без удаления)

```bash
ssh onedash2-enjoyer777 "cd /home/enjoyer777/ginai_english && docker compose exec -T bot python -m app.scripts.reset_memory --user 128657277 --dry-run"
```

### 4.3 Реально вычистить одного юзера

```bash
ssh onedash2-enjoyer777 "cd /home/enjoyer777/ginai_english && docker compose exec -T bot python -m app.scripts.reset_memory --user 128657277"
```

После этого бот при следующем сообщении от этого `tg_user_id` подумает, что видит его впервые: представится приветствием, заново соберёт квалификацию.

> ⚠️ Сделка в Битрикс24 при этом **не удаляется** — её надо стереть вручную в **CRM → Сделки**, иначе следующий горячий интент создаст НОВУЮ сделку (потому что локальная дедуп-запись стёрта).

### 4.4 Снести ВСЮ память (нужно для чистого пилота с нуля)

```bash
ssh onedash2-enjoyer777 "cd /home/enjoyer777/ginai_english && docker compose exec -T bot python -m app.scripts.reset_memory --all --force"
```

`--force` обязателен как защита от случайностей.

---

## 5. Обновить базу знаний (xlsx на Я.Диске)

### 5.1 Что и где править

База знаний — единственный xlsx-файл на Я.Диске по пути из `.env` (`YANDEX_DISK_FILE_PATH`, по умолчанию `/school_english_pro/kb.xlsx`). Заказчик правит её в любом редакторе (Excel, Я.Документы, LibreOffice). Структура листов — в [README.md](README.md#структура-базы-знаний-xlsx-на-ядиске).

### 5.2 Когда подхватятся изменения

- **Автоматически:** в течение **10 минут** после сохранения файла на Я.Диск (TTL кэша).
- **Принудительно:** `docker compose restart bot` на VPS — KB перечитается при старте.

### 5.3 Убедиться, что обновление дошло

```bash
ssh onedash2-enjoyer777 "cd /home/enjoyer777/ginai_english && docker compose logs bot --since=15m | grep -E 'KB (parsed|cache|warmed|refresh)'"
```

Хочется увидеть свежую строку:
```
KB parsed: 6 courses, 8 schedule slots, 3 teachers, 6 faq, 6 date overrides
KB cache refreshed
```

Если `date overrides` показывает не то число, что ожидал по листу `Праздники` — пересохрани файл, проверь что лист называется ровно `Праздники` (с большой буквы, без опечаток).

Если в логах `KB refresh failed, using stale cache` — значит проблема с Я.Диском (битый токен, сеть). Бот в этом случае продолжает работать на прошлом валидном снимке.

### 5.4 Особые даты (праздники, переносы)

Создай в xlsx лист `Праздники` с тремя колонками:

| date | hours | note |
|---|---|---|
| 2026-05-09 |  | День Победы — нерабочий |
| 2026-12-31 | 09:00-15:00 | Сокращённый предновогодний |

Пустое поле `hours` = весь день нерабочий. Подробнее в README.

---

## 6. Деплой кода

### 6.1 Через GitHub Actions (стандартно)

1. Локально: правишь код, `git commit && git push origin main`.
2. GitHub автоматически запускает workflow `Deploy to VPS` ([.github/workflows/deploy.yml](.github/workflows/deploy.yml)).
3. Через 1-2 минуты — бот пересобран и перезапущен.

Посмотреть статус последнего деплоя:
```bash
gh run list --repo enjoyer777/ginai_english --limit 3
```

Запустить вручную без коммита:
```bash
gh workflow run deploy.yml --repo enjoyer777/ginai_english
```

### 6.2 Что НЕ перетирается при деплое

CI rsync'ит репу на VPS, но из этого исключены:
- `.env` (локальные секреты)
- `xray-config.json` (приватные ключи Reality)
- `docker-compose.override.yml` (локальный сайдкар)
- `data/` (БД и логи)

Так что менять прокси/секреты можно прямо на VPS, деплой их не сломает.

### 6.3 Откатить плохой деплой

```bash
git revert HEAD
git push origin main
```

GitHub задеплоит обратное состояние. Никакой «магии» нет — просто новый коммит.

---

## 7. Прокси (Xray) — управление

Когда нужно: OpenAI блокирует RU-IP, прокси разрешает.

### 7.1 Статус и логи

```bash
ssh onedash2-enjoyer777 "cd /home/enjoyer777/ginai_english && docker compose ps xray && docker compose logs --tail=20 xray"
```

В норме видишь `Xray X.X.X started` и (когда бот делает запрос к OpenAI) строки типа:
```
from tcp:172.20.0.3:... accepted tcp:api.openai.com:443 [socks-in -> proxy]
```

### 7.2 Тест end-to-end из VPS

```bash
ssh onedash2-enjoyer777 "docker run --rm --network ginai_english_default curlimages/curl:latest -m 12 -x socks5h://xray:1080 -sS -o /dev/null -w 'http=%{http_code} time=%{time_total}\n' https://api.openai.com/"
```

`http=421` или `http=401` за <1 секунды = прокси живой и доходит до OpenAI.
`Connection reset` или `unexpected eof` = проблема с Reality auth (см. xray-config.json).
`Connection timed out` = проблема с сетью / файрволом.

### 7.3 Поправить `xray-config.json`

Файл лежит на VPS в `/home/enjoyer777/ginai_english/xray-config.json` (НЕ в репо). Редактируй там же:

```bash
ssh onedash2-enjoyer777
cd /home/enjoyer777/ginai_english
nano xray-config.json
docker compose restart xray
```

### 7.4 Временно отключить прокси

Если хочешь убедиться, что бот работает «голым» (только если ты на не-RU VPS):

```bash
ssh onedash2-enjoyer777
cd /home/enjoyer777/ginai_english
sed -i 's|^OPENAI_PROXY=.*|OPENAI_PROXY=|' .env
docker compose up -d
```

Бот перестанет ходить через xray, при первом hot-вопросе словит `403 unsupported_country_region_territory` от OpenAI. Возвращай `OPENAI_PROXY=socks5://xray:1080` и `up -d`.

---

## 8. Битрикс24

### 8.1 Найти все сделки, созданные ботом

В CRM → Сделки → Фильтр → Источник = «AI-бот Telegram».

### 8.2 Удалить тестовую сделку

В карточке сделки → меню (⋯) → Удалить. После этого нужно стереть и **локальную дедуп-запись** в SQLite, иначе бот при повторном hot-интенте попытается обновить уже несуществующую сделку:

```bash
ssh onedash2-enjoyer777 "cd /home/enjoyer777/ginai_english && docker compose exec -T bot python -m app.scripts.reset_memory --user <TG_ID>"
```

(этот CLI заодно вычищает и `deals` table — см. раздел 4)

### 8.3 Тест вебхука вручную

```bash
curl -m 5 -sS "https://b24-e1y7cx.bitrix24.ru/rest/1/<TOKEN>/crm.deal.fields.json" | head -c 200
```

Должен прийти JSON. `403`/`ACCESS_DENIED` = токен битый или нет прав `crm`.

---

## 9. Проверить, что ПДн не уходят в OpenAI

Бот маскирует телефоны/email/имена перед отправкой в OpenAI (см. раздел 2.7 в [CUSTOMER_REPORT.md](CUSTOMER_REPORT.md)). Чтобы убедиться, что это работает:

1. Напиши боту в Telegram любое сообщение с телефоном или email, например:
   > Мой номер +79991234567
2. На VPS посмотри лог:
   ```bash
   ssh onedash2-enjoyer777 "docker logs school-english-pro-bot --tail=20 | grep 'OpenAI'"
   ```
3. В строке вида:
   ```
   INFO  | app.dialog.engine:process_user_message:80 - User msg → OpenAI (tg_user=128657277): 'Мой номер <phone>'
   ```
   должно стоять **`<phone>`** вместо реальных цифр (или `<email>` вместо email, `<имя>` для сохранённого имени). Это то, что физически уходит в OpenAI.

Если вместо токена видишь реальный номер — значит regex не зацепил формат, нужно расширить паттерн в [app/utils/pii_mask.py](app/utils/pii_mask.py).

Для разового аудита всей истории в БД (поиск утечек по всем юзерам):

```bash
ssh onedash2-enjoyer777 'docker exec school-english-pro-bot python -c "
import asyncio, aiosqlite, re
from app.config import settings

PHONE = re.compile(r\"(?<!\w)(?:\+\s*\d|8(?=[\s\-\(]?\d)|7(?=[\s\-\(]?\d))(?:[\s\-\(\)\.]*\d){9,14}(?!\w)\")
EMAIL = re.compile(r\"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b\")

async def main():
    async with aiosqlite.connect(settings.sqlite_path) as db:
        cur = await db.execute(\"SELECT id, role, content FROM messages WHERE role=\\\"user\\\" ORDER BY id DESC LIMIT 50\")
        rows = await cur.fetchall()
    leaks = 0
    for id_, role, content in reversed(rows):
        bad = bool(PHONE.search(content) or EMAIL.search(content))
        marker = \"  !!!\" if bad else \"  OK \"
        leaks += int(bad)
        print(f\"{marker} #{id_}: {content[:120]}\")
    print(f\"\\nУтечек ПДн: {leaks} из {len(rows)} сообщений\")

asyncio.run(main())
"'
```

Здоровый ответ: `Утечек ПДн: 0 из N сообщений`, и все строки начинаются с `OK`.

---

## 10. Типовые проблемы

| Симптом | Где смотреть | Что делать |
|---|---|---|
| Бот молчит на любые сообщения | `docker compose ps` | Если контейнер `Up` — `docker compose logs bot`, ищи timeout/exception |
| `TelegramNetworkError: Request timeout` | Логи бота | Проверь Telegram-IP в `extra_hosts` (см. README), Xray (раздел 7) |
| Бот говорит «техническая заминка» на каждый вопрос | Логи | Скорее всего `OpenAI APIConnectionError` — Xray умер или ключ битый |
| `KB snapshot is empty at startup` | Логи | Проблема с Я.Диском: токен, путь, сеть |
| `unsupported_country_region_territory` в логах | OpenAI | `OPENAI_PROXY` пустой или Xray не работает |
| Сделка в Битриксе не появилась после hot lead | Логи + CRM | Проверь `BITRIX_WEBHOOK_URL` (полный URL до `/`) и `BITRIX_TG_USER_ID_FIELD` |
| Уведомления в чат менеджеров не приходят | Логи + чат | Проверь `MANAGERS_CHAT_ID` (с минусом, для групп), бот добавлен в чат |
| Бот ответил, но память всё равно «помнит» прошлое | — | Сбрось память: раздел 4.3 |

---

## 11. Тесты

### 11.1 Автоматические юнит-тесты

```bash
ssh onedash2-enjoyer777 "cd /home/enjoyer777/ginai_english && docker compose exec -T bot pytest -q tests/unit"
```

Должно пройти всё. Если не проходит — что-то сломалось в коде, не деплоить дальше.

### 10.2 Ручные сценарии приёмки

Полный чек-лист — [tests/manual_test_cases.md](tests/manual_test_cases.md). Помеченные `[x]` пункты уже закрыты юнит-тестами, можно не проверять руками.
