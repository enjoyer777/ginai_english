"""Сборка payload для входящего вебхука Bitrix24."""

from __future__ import annotations

from app.config import settings
from app.state.models import LeadProfile, User


def build_deal_title(user: User, profile: LeadProfile) -> str:
    name = user.first_name or user.tg_username or f"tg-{user.tg_user_id}"
    if profile.goal:
        return f"{name} — {profile.goal}"
    return name


def build_contact_payload(user: User) -> dict:
    """Payload для crm.contact.add."""
    name = user.first_name or "Клиент Telegram"
    fields: dict = {
        "NAME": name,
        "OPENED": "Y",
        "TYPE_ID": "CLIENT",
        "SOURCE_ID": "OTHER",
        "SOURCE_DESCRIPTION": "AI-бот Telegram",
    }
    if user.contact_phone:
        fields["PHONE"] = [{"VALUE": user.contact_phone, "VALUE_TYPE": "MOBILE"}]
    if user.tg_username:
        fields["IM"] = [{"VALUE": f"@{user.tg_username}", "VALUE_TYPE": "TELEGRAM"}]
    return {"fields": fields}


def build_deal_payload(
    user: User,
    profile: LeadProfile,
    summary: str,
    contact_id: str | int | None = None,
) -> dict:
    """Payload для crm.deal.add."""
    fields: dict = {
        "TITLE": build_deal_title(user, profile),
        "STAGE_ID": settings.bitrix_default_stage,
        "OPENED": "Y",
        "SOURCE_ID": "OTHER",
        "SOURCE_DESCRIPTION": "AI-бот Telegram",
        "COMMENTS": summary,
        settings.bitrix_tg_user_id_field: str(user.tg_user_id),
    }
    if contact_id is not None:
        fields["CONTACT_ID"] = contact_id
    return {"fields": fields}


def build_deal_update_payload(summary: str) -> dict:
    """Payload для crm.deal.update — обновляем COMMENTS повторного захода клиента."""
    return {"fields": {"COMMENTS": summary}}
