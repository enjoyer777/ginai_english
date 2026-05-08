"""Главный «мозг» бота: маршрутизация сообщений, цикл LLM tool-use, hot lead flow."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from aiogram import Bot
from loguru import logger

from app.config import settings
from app.crm.bitrix_client import BitrixError, bitrix
from app.crm.deal_builder import (
    build_contact_payload,
    build_deal_payload,
    build_deal_update_payload,
)
from app.dialog import guardrails
from app.kb.cache import get_snapshot
from app.kb.schema import KBSnapshot
from app.llm.client import llm
from app.notifications.managers_chat import notify_hot_lead
from app.state import repository as repo
from app.state.models import LeadProfile, Message, User
from app.utils.working_hours import default_schedule, is_working_now

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


# ---------- main entry: process inbound text ----------

async def process_user_message(bot: Bot, user: User, text: str) -> str:
    """Полный цикл обработки одного текстового сообщения от клиента.

    Возвращает текст, который надо отправить клиенту (handlers сами шлют).
    """
    # 1. Дешёвый предфильтр
    if guardrails.is_jailbreak_attempt(text):
        await repo.append_message(user.tg_user_id, "user", text)
        await repo.append_message(user.tg_user_id, "assistant", guardrails.JAILBREAK_RESPONSE)
        return guardrails.JAILBREAK_RESPONSE

    if guardrails.is_empty_or_garbage(text):
        await repo.append_message(user.tg_user_id, "user", text)
        await repo.append_message(user.tg_user_id, "assistant", guardrails.GARBAGE_RESPONSE)
        return guardrails.GARBAGE_RESPONSE

    # 2. Записываем сообщение клиента
    await repo.append_message(user.tg_user_id, "user", text)

    # 3. Готовим контекст для LLM
    snapshot = await get_snapshot()
    history = await repo.get_recent_messages(user.tg_user_id)
    profile = await repo.get_lead_profile(user.tg_user_id)

    # 4. Состояние, разделяемое с tool-handler'ами
    state = _ToolState(bot=bot, user=user, profile=profile, snapshot=snapshot)
    handlers = _build_tool_handlers(state)

    # 5. Системное сообщение собирается из system.txt + плашки контекста
    system_text = _compose_system(snapshot, profile)
    messages = [{"role": "system", "content": system_text}] + _serialize_history(history)

    # 6. Сам поход в LLM
    try:
        reply = await llm.chat(messages, handlers)
    except Exception:
        logger.exception("LLM chat failed")
        reply = (
            "Кажется, у меня небольшая техническая заминка. "
            "Хотите, я соединю вас с менеджером?"
        )

    # 7. Если в ходе tool-use был запущен hot lead flow — он сам послал текст,
    #    но финальное сообщение модели всё равно отдадим клиенту.
    await repo.append_message(user.tg_user_id, "assistant", reply)
    return reply


# ---------- handover triggered by button ----------

async def handover_flow(bot: Bot, user: User) -> str:
    """Принудительная передача в CRM по нажатию кнопки 'Связаться с менеджером' (FR-7)."""
    profile = await repo.get_lead_profile(user.tg_user_id)
    snapshot = await get_snapshot()
    state = _ToolState(bot=bot, user=user, profile=profile, snapshot=snapshot)

    if not user.contact_phone and not user.tg_username:
        # Контакта нет — нечего отправлять. Просим контакт.
        return (
            "Чтобы менеджер мог связаться, поделитесь, пожалуйста, телефоном или "
            "разрешите написать в Telegram — для этого можно прислать любое сообщение, "
            "и мы свяжемся с вами по нему."
        )

    success = await _push_to_crm(state, reason="handover_button")
    if not success:
        return (
            "Сейчас не получилось передать заявку — попробуйте, пожалуйста, чуть позже. "
            "Менеджер всё равно свяжется."
        )
    if is_working_now(_schedule_from(snapshot)):
        return "Передал менеджеру, скоро свяжется."
    return _off_hours_message(snapshot)


# ---------- internal: tool handlers ----------


class _ToolState:
    """Изменяемое состояние, к которому имеют доступ tool-обработчики."""

    def __init__(
        self,
        bot: Bot,
        user: User,
        profile: LeadProfile,
        snapshot: KBSnapshot | None,
    ) -> None:
        self.bot = bot
        self.user = user
        self.profile = profile
        self.snapshot = snapshot
        self.hot_triggered = False
        self.handover_triggered = False


def _build_tool_handlers(state: _ToolState) -> dict[str, Any]:
    return {
        "get_courses": lambda args: _t_get_courses(state, args),
        "get_schedule": lambda args: _t_get_schedule(state, args),
        "get_teachers": lambda args: _t_get_teachers(state, args),
        "get_faq": lambda args: _t_get_faq(state, args),
        "update_lead_profile": lambda args: _t_update_profile(state, args),
        "mark_hot_lead": lambda args: _t_mark_hot(state, args),
        "request_handover": lambda args: _t_request_handover(state, args),
    }


async def _t_get_courses(state: _ToolState, args: dict) -> Any:
    if not state.snapshot:
        return {"error": "База знаний временно недоступна. Предложи связаться с менеджером."}
    direction = args.get("direction")
    level = args.get("level")
    items = state.snapshot.courses
    if direction:
        items = [c for c in items if c.direction == direction]
    if level:
        items = [c for c in items if level in c.levels]
    return [_course_to_dict(c) for c in items]


async def _t_get_schedule(state: _ToolState, args: dict) -> Any:
    if not state.snapshot:
        return {"error": "База знаний временно недоступна."}
    course_id = args.get("course_id")
    items = state.snapshot.schedules
    if course_id:
        items = [s for s in items if s.course_id == course_id]
    return [
        {
            "course_id": s.course_id,
            "start_date": s.start_date.isoformat(),
            "days_time": s.days_time,
            "teacher_name": s.teacher_name,
            "seats_left": s.seats_left,
        }
        for s in items
    ]


async def _t_get_teachers(state: _ToolState, args: dict) -> Any:
    if not state.snapshot:
        return {"error": "База знаний временно недоступна."}
    return [
        {
            "name": t.name,
            "experience_years": t.experience_years,
            "specialization": t.specialization,
            "bio": t.bio,
        }
        for t in state.snapshot.teachers
    ]


async def _t_get_faq(state: _ToolState, args: dict) -> Any:
    if not state.snapshot:
        return {"error": "База знаний временно недоступна."}
    return [{"question": f.question, "answer": f.answer} for f in state.snapshot.faq]


async def _t_update_profile(state: _ToolState, args: dict) -> Any:
    state.profile = await repo.update_lead_profile(
        state.user.tg_user_id,
        goal=args.get("goal"),
        level_self=args.get("level_self"),
        horizon=args.get("horizon"),
        readiness=args.get("readiness"),
    )
    return {"ok": True, "profile": _profile_to_dict(state.profile)}


async def _t_mark_hot(state: _ToolState, args: dict) -> Any:
    reason = args.get("reason", "")
    logger.info("LLM marked hot lead: tg_user={} reason={}", state.user.tg_user_id, reason)
    await repo.mark_hot(state.user.tg_user_id)
    state.profile.is_hot = True
    state.hot_triggered = True
    success = await _push_to_crm(state, reason=f"hot:{reason}")
    return {"ok": success}


async def _t_request_handover(state: _ToolState, args: dict) -> Any:
    state.handover_triggered = True
    success = await _push_to_crm(state, reason="explicit_handover")
    return {"ok": success}


# ---------- internal: hot lead push ----------


async def _push_to_crm(state: _ToolState, reason: str) -> bool:
    """Создаёт/обновляет сделку Bitrix24 и (если рабочие часы) шлёт уведомление в чат менеджеров."""
    user = state.user
    profile = state.profile

    history = await repo.get_recent_messages(user.tg_user_id)
    history_text = _history_to_text(history)
    profile_text = _profile_to_text(profile)
    summary = await llm.summarize_for_crm(history_text, profile_text)

    try:
        existing = await repo.find_deal_by_user(user.tg_user_id)
        if existing:
            await bitrix.update_deal(existing.bitrix_deal_id, build_deal_update_payload(summary))
            deal_id = existing.bitrix_deal_id
            logger.info("Updated existing Bitrix deal {} for tg_user={}", deal_id, user.tg_user_id)
        else:
            contact_id: str | None = None
            if user.contact_phone:
                contact_id = await bitrix.find_contact_by_phone(user.contact_phone)
                if not contact_id:
                    contact_id = await bitrix.add_contact(build_contact_payload(user))
            else:
                contact_id = await bitrix.add_contact(build_contact_payload(user))
            deal_id = await bitrix.add_deal(build_deal_payload(user, profile, summary, contact_id))
            logger.info("Created Bitrix deal {} for tg_user={} (reason={})", deal_id, user.tg_user_id, reason)
        await repo.save_deal_ref(user.tg_user_id, deal_id, summary)
    except BitrixError as e:
        logger.error("Bitrix push failed: {}", e)
        return False
    except Exception:
        logger.exception("Unexpected Bitrix error")
        return False

    # Уведомление в чат менеджеров — только в рабочее время
    snapshot = state.snapshot
    if is_working_now(_schedule_from(snapshot)):
        deal_url = bitrix.deal_url(deal_id)
        await notify_hot_lead(state.bot, user, deal_url)

    return True


# ---------- helpers ----------


def _schedule_from(snapshot: KBSnapshot | None):
    if snapshot and snapshot.settings.working_hours and any(
        v is not None for v in snapshot.settings.working_hours.values()
    ):
        return snapshot.settings.working_hours
    return default_schedule()


def _off_hours_message(snapshot: KBSnapshot | None) -> str:
    return (
        "Принял заявку. Менеджер свяжется в ближайшие рабочие часы — "
        "Пн-Пт 9:00–19:00, Сб 10:00–15:00 МСК."
    )


def _compose_system(snapshot: KBSnapshot | None, profile: LeadProfile) -> str:
    base = load_prompt("system.txt")
    today = date.today().isoformat()
    profile_block = _profile_to_text(profile) or "(пока пусто)"
    work_state = "сейчас рабочее время" if is_working_now(_schedule_from(snapshot)) else "сейчас НЕ рабочее время"
    extras = (
        f"\n\n# КОНТЕКСТ\nСегодня: {today}. {work_state}.\n\n"
        f"# ПРОФИЛЬ КЛИЕНТА (что уже знаем)\n{profile_block}\n"
    )
    if not is_working_now(_schedule_from(snapshot)):
        extras += (
            "\nЕсли клиент горячий или просит менеджера: предупреди, что с ним свяжутся "
            "в ближайшие рабочие часы (Пн-Пт 9-19, Сб 10-15 МСК). Не обещай мгновенный ответ."
        )
    return base + extras


def _serialize_history(history: list[Message]) -> list[dict]:
    out: list[dict] = []
    for m in history:
        if m.role in ("user", "assistant"):
            out.append({"role": m.role, "content": m.content})
    return out


def _course_to_dict(c) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "direction": c.direction,
        "levels": c.levels,
        "duration_weeks": c.duration_weeks,
        "format": c.format,
        "price_rub": c.price_rub,
        "installment": c.installment,
        "description": c.description,
        "nearest_start": c.nearest_start.isoformat() if c.nearest_start else None,
    }


def _profile_to_dict(p: LeadProfile) -> dict:
    return {
        "goal": p.goal,
        "level_self": p.level_self,
        "horizon": p.horizon,
        "readiness": p.readiness,
        "is_hot": p.is_hot,
    }


def _profile_to_text(p: LeadProfile) -> str:
    parts = []
    if p.goal:
        parts.append(f"Цель: {p.goal}")
    if p.level_self:
        parts.append(f"Уровень: {p.level_self}")
    if p.horizon:
        parts.append(f"Сроки: {p.horizon}")
    if p.readiness:
        parts.append(f"Готовность: {p.readiness}")
    if p.is_hot:
        parts.append("Статус: ГОРЯЧИЙ")
    return "; ".join(parts)


def _history_to_text(history: list[Message]) -> str:
    lines = []
    for m in history:
        if m.role in ("user", "assistant"):
            who = "Клиент" if m.role == "user" else "Бот"
            lines.append(f"{who}: {m.content}")
    return "\n".join(lines)
