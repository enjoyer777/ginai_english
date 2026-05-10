"""CLI: показать или сбросить память бота (SQLite-стейт).

Запускается ВНУТРИ контейнера бота, чтобы не подбирать пути к файлу БД руками:

    docker compose exec bot python -m app.scripts.reset_memory                     # список юзеров
    docker compose exec bot python -m app.scripts.reset_memory --user 128657277    # вайп одного
    docker compose exec bot python -m app.scripts.reset_memory --user 128657277 --dry-run
    docker compose exec bot python -m app.scripts.reset_memory --all --force       # вайп всех

Что чистится при --user / --all:
    - users               — запись о пользователе (имя, телефон, username)
    - lead_profiles       — слоты квалификации (цель/уровень/срок/готовность/is_hot)
    - messages            — вся история диалога
    - deals               — ЛОКАЛЬНАЯ ссылка на сделку Bitrix24
                            (саму сделку в Битриксе скрипт НЕ удаляет —
                             если хочешь чистый прогон, удали её в CRM руками)
    - notify_events       — история уведомлений в чат менеджеров (для дедупа)
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import aiosqlite

from app.config import settings


PER_USER_TABLES = ["messages", "lead_profiles", "deals", "notify_events", "users"]
ALL_TABLES = ["messages", "lead_profiles", "deals", "notify_events", "users"]


async def list_users() -> None:
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT
                u.tg_user_id,
                u.tg_username,
                u.first_name,
                u.contact_phone,
                COUNT(m.id)        AS messages,
                MAX(m.created_at)  AS last_seen,
                p.is_hot
            FROM users u
            LEFT JOIN messages m       ON m.tg_user_id = u.tg_user_id
            LEFT JOIN lead_profiles p  ON p.tg_user_id = u.tg_user_id
            GROUP BY u.tg_user_id
            ORDER BY last_seen DESC
            """
        )
        rows = await cur.fetchall()

    if not rows:
        print("В базе нет ни одного пользователя.")
        return

    print(f"{'tg_user_id':<13} {'username':<22} {'name':<20} {'phone':<16} {'msgs':>5}  {'hot':<3} last_seen")
    print("-" * 105)
    for r in rows:
        username = f"@{r['tg_username']}" if r["tg_username"] else "—"
        name = r["first_name"] or "—"
        phone = r["contact_phone"] or "—"
        hot = "✓" if r["is_hot"] else ""
        last_seen = r["last_seen"] or ""
        print(
            f"{r['tg_user_id']:<13} {username:<22} {name:<20} {phone:<16} "
            f"{r['messages']:>5}  {hot:<3} {last_seen}"
        )


async def wipe_user(tg_user_id: int, dry_run: bool) -> None:
    async with aiosqlite.connect(settings.sqlite_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE tg_user_id = ?", (tg_user_id,))
        user = await cur.fetchone()
        if not user:
            print(f"Пользователь tg_user_id={tg_user_id} не найден в БД.")
            return

        print(
            f"Найден: tg_user_id={tg_user_id}, "
            f"username=@{user['tg_username'] or '—'}, "
            f"name={user['first_name'] or '—'}"
        )
        print()
        print("К удалению:")
        for tbl in PER_USER_TABLES:
            cur = await db.execute(
                f"SELECT COUNT(*) FROM {tbl} WHERE tg_user_id = ?", (tg_user_id,)
            )
            row = await cur.fetchone()
            count = row[0] if row else 0
            print(f"  {tbl:<16} {count:>5}")

        if dry_run:
            print("\nDry run — ничего не удалено.")
            return

        for tbl in PER_USER_TABLES:
            await db.execute(f"DELETE FROM {tbl} WHERE tg_user_id = ?", (tg_user_id,))
        await db.commit()

    print(f"\nПамять для tg_user_id={tg_user_id} очищена. Бот забудет этого пользователя при следующем сообщении.")
    print(
        "Связанная сделка в Битрикс24 (если была) — НЕ удалена. Если нужен чистый прогон — "
        "удали её в CRM руками, иначе бот при следующем горячем интенте создаст НОВУЮ сделку."
    )


async def wipe_all(dry_run: bool) -> None:
    async with aiosqlite.connect(settings.sqlite_path) as db:
        print("К удалению (все строки):")
        for tbl in ALL_TABLES:
            cur = await db.execute(f"SELECT COUNT(*) FROM {tbl}")
            row = await cur.fetchone()
            count = row[0] if row else 0
            print(f"  {tbl:<16} {count:>5}")

        if dry_run:
            print("\nDry run — ничего не удалено.")
            return

        for tbl in ALL_TABLES:
            await db.execute(f"DELETE FROM {tbl}")
        await db.commit()

    print("\nВсё снесено. Бот стартует «с нуля» при следующем сообщении любого юзера.")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Сброс памяти бота. Без аргументов = просто список пользователей.",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--user",
        type=int,
        metavar="TG_USER_ID",
        help="Сбросить данные одного пользователя по его Telegram user_id.",
    )
    g.add_argument(
        "--all",
        action="store_true",
        help="Сбросить ВСЮ память (требует --force во избежание случайностей).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Показать, что было бы удалено, но не удалять.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Подтверждение для --all (без него --all откажет).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if args.user is not None:
        asyncio.run(wipe_user(args.user, args.dry_run))
        return 0

    if args.all:
        if not args.dry_run and not args.force:
            print(
                "Ошибка: --all без --dry-run требует флага --force. "
                "Это защита от случайного полного вайпа.",
                file=sys.stderr,
            )
            return 2
        asyncio.run(wipe_all(args.dry_run))
        return 0

    asyncio.run(list_users())
    return 0


if __name__ == "__main__":
    sys.exit(main())
