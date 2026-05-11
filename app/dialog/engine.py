"""Главный «мозг» бота: маршрутизация сообщений, цикл LLM tool-use, hot lead flow."""

from __future__ import annotations

from datetime import date, time, timedelta
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
from app.utils.pii_mask import mask_message, pre_extract_email, pre_extract_phone
from app.utils.time import now
from app.utils.working_hours import WEEKDAY_KEYS, default_schedule, is_within, is_working_now

WEEKDAY_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

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

    # 2. PII pre-extraction — телефон/email вытаскиваем ДО LLM и сохраняем в БД.
    #    Это нужно, чтобы реальные ПДн НЕ улетали на серверы OpenAI (трансгран
    #    под 152-ФЗ).
    extracted_phone = pre_extract_phone(text)
    if extracted_phone and not user.contact_phone:
        await repo.set_contact_phone(user.tg_user_id, extracted_phone)
        user.contact_phone = extracted_phone
        logger.info("Pre-extracted phone for tg_user={} (masked in LLM context)", user.tg_user_id)

    # 3. В БД пишем РАВНО маскированную версию — даже если БД утечёт (это RU),
    #    в истории не будет повторяющихся номеров.
    text_for_history = mask_message(text, saved_name=user.first_name)
    await repo.append_message(user.tg_user_id, "user", text_for_history)

    # 4. Готовим контекст для LLM
    snapshot = await get_snapshot()
    history = await repo.get_recent_messages(user.tg_user_id)
    profile = await repo.get_lead_profile(user.tg_user_id)

    # 5. Состояние, разделяемое с tool-handler'ами
    state = _ToolState(bot=bot, user=user, profile=profile, snapshot=snapshot)
    handlers = _build_tool_handlers(state)

    # 6. Системное сообщение собирается из system.txt + плашки контекста
    system_text = _compose_system(snapshot, profile)

    # 7. История ДОПОЛНИТЕЛЬНО маскируется при формировании контекста —
    #    защита от того, что в БД могло сохраниться что-то немаскированное
    #    (старые сообщения до этого фикса, или новые типы ПДн).
    serialized = _serialize_history(history, saved_name=user.first_name)

    # 8. Если мы только что извлекли телефон — подскажем LLM системным сообщением,
    #    чтобы она не просила его повторно.
    if extracted_phone and pre_extract_phone(text):
        serialized.append({
            "role": "system",
            "content": (
                "Клиент только что прислал свой номер телефона. Он СОХРАНЁН на стороне "
                "бота. НЕ нужно его повторно спрашивать. Если был ожидающий горячий лид — "
                "вызови mark_hot_lead для финальной передачи в CRM. Не показывай номер "
                "клиенту обратно."
            ),
        })

    messages = [{"role": "system", "content": system_text}] + serialized

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

    # Менеджеру нужен телефон для звонка. Telegram-username не считаем достаточным:
    # у клиента может быть закрытая возможность писать в TG, плюс менеджер обычно звонит.
    if not user.contact_phone:
        return (
            "Чтобы менеджер мог позвонить, пришлите, пожалуйста, ваш номер телефона "
            "сообщением — следующее ваше сообщение я сохраню как контакт. "
            "Можно в любом удобном формате: +7..., 8..., с пробелами или без."
        )

    success = await _push_to_crm(state, reason="handover_button")
    if not success:
        return (
            "Сейчас не получилось передать заявку — попробуйте, пожалуйста, чуть позже. "
            "Менеджер всё равно свяжется."
        )
    if is_working_now(_schedule_from(snapshot), _overrides_from(snapshot)):
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

    phone_raw = args.get("contact_phone")
    if phone_raw and phone_raw.strip() not in ("<phone>", ""):
        # Запасной канал: если LLM откуда-то всё-таки увидела номер (не должна),
        # сохраним. В нормальном flow телефон извлекается pre-extractor'ом из
        # сообщения клиента ДО LLM — этот код не должен сработать.
        phone = _normalize_phone(phone_raw)
        if phone:
            await repo.set_contact_phone(state.user.tg_user_id, phone)
            state.user.contact_phone = phone
            logger.warning("Phone arrived via LLM tool (unexpected after PII masking) for tg_user={}", state.user.tg_user_id)

    name_raw = args.get("first_name")
    if name_raw and name_raw.strip():
        # Клиент явно сказал, как к нему обращаться — это важнее, чем имя из TG-профиля.
        # Перезаписываем И в БД, И в локальном state (нужно для последующего push_to_crm
        # в том же сообщении).
        cleaned_name = name_raw.strip()[:64]
        await repo.set_first_name(state.user.tg_user_id, cleaned_name)
        state.user.first_name = cleaned_name
        logger.info("Saved first_name='{}' for tg_user={}", cleaned_name, state.user.tg_user_id)

    return {"ok": True, "profile": _profile_to_dict(state.profile)}


async def _t_mark_hot(state: _ToolState, args: dict) -> Any:
    reason = args.get("reason", "")
    logger.info("LLM marked hot lead: tg_user={} reason={}", state.user.tg_user_id, reason)
    await repo.mark_hot(state.user.tg_user_id)
    state.profile.is_hot = True
    state.hot_triggered = True

    # Гард: без телефона в CRM не пушим. LLM по промпту попросит у клиента и
    # запишет через update_lead_profile с contact_phone, потом снова вызовет mark_hot_lead.
    if not state.user.contact_phone:
        logger.info("mark_hot_lead deferred: phone not yet collected for tg_user={}", state.user.tg_user_id)
        return {
            "ok": False,
            "status": "phone_required",
            "instruction": (
                "Лид помечен как горячий, но телефон ещё не собран. Спроси у клиента "
                "номер телефона для связи, запиши его через update_lead_profile с "
                "параметром contact_phone, затем снова вызови mark_hot_lead."
            ),
        }

    success = await _push_to_crm(state, reason=f"hot:{reason}")
    return {"ok": success}


def _normalize_phone(raw: str) -> str | None:
    """Принимает что угодно (+7 999 ..., 8(999)..., +79991234567), оставляет только цифры/+.

    Минимум 10 цифр, максимум 15 (E.164). Если не похоже на номер — возвращает None.
    """
    cleaned = "".join(c for c in raw if c.isdigit() or c == "+")
    if cleaned.startswith("+"):
        digits = cleaned[1:]
    else:
        digits = cleaned
    if not digits.isdigit():
        return None
    if len(digits) < 10 or len(digits) > 15:
        return None
    # Российские номера, начатые с 8 — нормализуем в +7
    if len(digits) == 11 and digits.startswith("8"):
        return "+7" + digits[1:]
    if cleaned.startswith("+"):
        return "+" + digits
    if len(digits) == 11 and digits.startswith("7"):
        return "+" + digits
    return digits


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
    # _history_to_text сам по себе берёт уже-маскированную историю из БД, но
    # на всякий случай прогоняем ещё раз — двойная защита перед отправкой в OpenAI.
    history_text = mask_message(_history_to_text(history), saved_name=user.first_name)
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

    # Уведомление в чат менеджеров — только в рабочее время (с учётом праздников)
    snapshot = state.snapshot
    if is_working_now(_schedule_from(snapshot), _overrides_from(snapshot)):
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


def _overrides_from(snapshot: KBSnapshot | None) -> dict:
    if snapshot:
        return dict(snapshot.settings.date_overrides)
    return {}


def _notes_from(snapshot: KBSnapshot | None) -> dict:
    if snapshot:
        return dict(snapshot.settings.date_notes)
    return {}


def _off_hours_message(snapshot: KBSnapshot | None) -> str:
    return (
        "Принял заявку. Менеджер свяжется в ближайшие рабочие часы — "
        "Пн-Пт 9:00–19:00, Сб 10:00–15:00 МСК."
    )


def _compose_system(snapshot: KBSnapshot | None, profile: LeadProfile) -> str:
    base = load_prompt("system.txt")
    schedule = _schedule_from(snapshot)
    overrides = _overrides_from(snapshot)
    notes = _notes_from(snapshot)
    moment = now()  # МСК

    profile_block = _profile_to_text(profile) or "(пока пусто)"
    calendar_block = _compose_calendar_block(schedule, overrides, notes, moment)

    extras = (
        f"\n\n# КАЛЕНДАРЬ (используй ТОЛЬКО эти данные, не вычисляй даты сам)\n"
        f"{calendar_block}\n\n"
        f"# ПРОФИЛЬ КЛИЕНТА (что уже знаем)\n{profile_block}\n"
    )

    if is_within(moment, schedule, overrides):
        extras += (
            "\n# КОГДА ПЕРЕДАЁШЬ В CRM (СЕЙЧАС РАБОЧЕЕ ВРЕМЯ)\n"
            "После успешного mark_hot_lead / request_handover пиши клиенту: "
            "«Передал заявку менеджеру, он свяжется в ближайшее время». "
            "НЕ упоминай «рабочие часы», «менеджер ответит в Пн-Пт» и т.п. — "
            "мы УЖЕ в рабочем времени, менеджер на связи прямо сейчас.\n"
        )
    else:
        extras += (
            "\n# КОГДА ПЕРЕДАЁШЬ В CRM (СЕЙЧАС НЕРАБОЧЕЕ ВРЕМЯ)\n"
            "После успешного mark_hot_lead / request_handover пиши клиенту "
            "конкретное время следующей связи. Используй ТОЧНУЮ строку из блока "
            "КАЛЕНДАРЬ → «Ближайшее рабочее окно» (там уже посчитан день недели, "
            "число и часы). Пример формулировки:\n"
            "  «Передал заявку менеджеру. Свяжется в <строка из 'Ближайшее рабочее окно'>».\n"
            "НЕ пиши «в ближайшие рабочие часы» без конкретики — клиенту это бесполезно. "
            "НЕ обещай мгновенный ответ.\n"
        )
    return base + extras


def _compose_calendar_block(
    schedule: dict[str, tuple[time, time] | None],
    overrides: dict[date, tuple[time, time] | None],
    notes: dict[date, str],
    moment,
) -> str:
    """Готовый блок «сегодня/завтра/неделя/ближайшее окно» — чтобы LLM не считала даты сама."""
    today_idx = moment.weekday()
    today_date = moment.date()
    is_now_working = is_within(moment, schedule, overrides)

    # Сегодня
    today_state = _format_day_state(
        today_date,
        schedule,
        overrides,
        notes,
        is_today=True,
        is_working_now_flag=is_now_working,
        current_time=moment.time(),
    )
    today_line = f"Сегодня: {today_date.isoformat()} ({WEEKDAY_RU[today_idx]}) — {today_state}"

    # Завтра
    tomorrow_date = today_date + timedelta(days=1)
    tomorrow_idx = (today_idx + 1) % 7
    tomorrow_line = (
        f"Завтра: {tomorrow_date.isoformat()} ({WEEKDAY_RU[tomorrow_idx]}) — "
        f"{_format_day_state(tomorrow_date, schedule, overrides, notes, is_today=False)}"
    )

    # Расписание недели — без оверрайдов (это «обычный» базовый график школы)
    weekly = ["Расписание недели (обычное, без праздников):"]
    for i, key in enumerate(WEEKDAY_KEYS):
        weekly.append(f"  - {WEEKDAY_RU[i].capitalize()}: {_format_window(schedule.get(key))}")

    # Праздники / исключения на ближайшие 30 дней
    upcoming = _format_upcoming_overrides(overrides, notes, today_date, days_ahead=30)
    holiday_block = []
    if upcoming:
        holiday_block.append("Особые даты в ближайшие 30 дней:")
        holiday_block.extend(upcoming)
    else:
        holiday_block.append("Особые даты: на ближайший месяц не заданы.")

    # Ближайшее доступное рабочее окно (с учётом праздников)
    nxt = _next_working_window(schedule, overrides, notes, moment)
    next_line = f"Ближайшее рабочее окно: {nxt}" if nxt else "Ближайшее рабочее окно: расписание не задано."

    return "\n".join([today_line, tomorrow_line, *weekly, *holiday_block, next_line])


def _format_window(window: tuple[time, time] | None) -> str:
    if window is None:
        return "выходной"
    s, e = window
    return f"{s.strftime('%H:%M')}–{e.strftime('%H:%M')} МСК"


def _format_upcoming_overrides(
    overrides: dict[date, tuple[time, time] | None],
    notes: dict[date, str],
    from_date: date,
    days_ahead: int,
) -> list[str]:
    horizon = from_date + timedelta(days=days_ahead)
    relevant = sorted(d for d in overrides if from_date <= d <= horizon)
    out = []
    for d in relevant:
        wd = WEEKDAY_RU[d.weekday()]
        win = overrides[d]
        win_str = _format_window(win)
        note = notes.get(d, "")
        line = f"  - {d.isoformat()} ({wd}): {win_str}"
        if note:
            line += f" — {note}"
        out.append(line)
    return out


def _format_day_state(
    target_date: date,
    schedule: dict[str, tuple[time, time] | None],
    overrides: dict[date, tuple[time, time] | None],
    notes: dict[date, str],
    *,
    is_today: bool,
    is_working_now_flag: bool = False,
    current_time: time | None = None,
) -> str:
    from app.utils.working_hours import effective_window_for

    window = effective_window_for(target_date, schedule, overrides)
    is_overridden = target_date in overrides
    note = notes.get(target_date, "")

    base = _format_window(window)
    suffix_parts = []
    if is_overridden:
        suffix_parts.append("особая дата")
        if note:
            suffix_parts.append(note)

    if not is_today:
        if suffix_parts:
            return f"{base} ({'; '.join(suffix_parts)})"
        return base

    if window is None:
        if suffix_parts:
            return f"{base} (нерабочий день; {'; '.join(suffix_parts)})"
        return f"{base} (нерабочий день)"
    if is_working_now_flag:
        tail = f", СЕЙЧАС рабочее время"
        if suffix_parts:
            tail += f" ({'; '.join(suffix_parts)})"
        return f"{base}{tail}"
    cur = current_time.strftime("%H:%M") if current_time else "?"
    s, e = window
    if current_time and current_time < s:
        tail = f", сейчас {cur} (ещё рано — менеджеры с {s.strftime('%H:%M')})"
    elif current_time and current_time >= e:
        tail = f", сейчас {cur} (уже поздно — менеджеры до {e.strftime('%H:%M')})"
    else:
        tail = f", сейчас {cur}"
    if suffix_parts:
        tail += f" ({'; '.join(suffix_parts)})"
    return f"{base}{tail}"


def _next_working_window(
    schedule: dict[str, tuple[time, time] | None],
    overrides: dict[date, tuple[time, time] | None],
    notes: dict[date, str],
    moment,
) -> str | None:
    """Возвращает «вторник, 12 мая, 09:00–19:00 МСК» — ближайшая точка, где менеджер ответит,
    с учётом праздничных переопределений (день полностью выпал / часы укорочены)."""
    from app.utils.working_hours import effective_window_for

    cur_dt = moment
    cur_date = cur_dt.date()
    for offset in range(0, 14):  # запас на длинные праздники
        d = cur_date + timedelta(days=offset)
        wd_idx = d.weekday()
        window = effective_window_for(d, schedule, overrides)
        if window is None:
            continue
        s, e = window
        note_suffix = f" ({notes[d]})" if d in notes and notes[d] else ""
        if offset == 0:
            if cur_dt.time() < s:
                return (
                    f"{WEEKDAY_RU[wd_idx]}, {d.isoformat()}, "
                    f"{s.strftime('%H:%M')}–{e.strftime('%H:%M')} МСК{note_suffix}"
                )
            if cur_dt.time() < e:
                return f"сейчас (до {e.strftime('%H:%M')} МСК){note_suffix}"
            continue
        return (
            f"{WEEKDAY_RU[wd_idx]}, {d.isoformat()}, "
            f"{s.strftime('%H:%M')}–{e.strftime('%H:%M')} МСК{note_suffix}"
        )
    return None


def _serialize_history(history: list[Message], saved_name: str | None = None) -> list[dict]:
    """Готовит историю для LLM. Дополнительно прогоняет маскирование на каждом сообщении —
    защита от утечки ПДн в OpenAI, если в БД сохранилось что-то немаскированное."""
    out: list[dict] = []
    for m in history:
        if m.role in ("user", "assistant"):
            out.append({"role": m.role, "content": mask_message(m.content, saved_name=saved_name)})
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
