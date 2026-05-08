from datetime import datetime, timezone

from app.config import settings
from app.crm.deal_builder import (
    build_contact_payload,
    build_deal_payload,
    build_deal_title,
    build_deal_update_payload,
)
from app.state.models import LeadProfile, User


def make_user(**overrides) -> User:
    base = dict(
        tg_user_id=12345,
        tg_username="ivan_p",
        first_name="Иван",
        contact_phone=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return User(**base)


def test_deal_title_with_goal():
    user = make_user()
    profile = LeadProfile(tg_user_id=12345, goal="IELTS")
    assert build_deal_title(user, profile) == "Иван — IELTS"


def test_deal_title_without_goal():
    user = make_user()
    profile = LeadProfile(tg_user_id=12345)
    assert build_deal_title(user, profile) == "Иван"


def test_deal_title_falls_back_to_username():
    user = make_user(first_name=None)
    profile = LeadProfile(tg_user_id=12345)
    assert build_deal_title(user, profile) == "ivan_p"


def test_deal_title_falls_back_to_tg_id():
    user = make_user(first_name=None, tg_username=None)
    profile = LeadProfile(tg_user_id=12345)
    assert build_deal_title(user, profile) == "tg-12345"


def test_contact_payload_with_phone():
    user = make_user(contact_phone="+79991234567")
    payload = build_contact_payload(user)
    assert payload["fields"]["NAME"] == "Иван"
    assert payload["fields"]["PHONE"] == [{"VALUE": "+79991234567", "VALUE_TYPE": "MOBILE"}]
    assert payload["fields"]["IM"][0]["VALUE"] == "@ivan_p"


def test_contact_payload_without_phone_uses_telegram():
    user = make_user(contact_phone=None)
    payload = build_contact_payload(user)
    assert "PHONE" not in payload["fields"]
    assert payload["fields"]["IM"][0]["VALUE"] == "@ivan_p"


def test_deal_payload_carries_summary_and_dedup_field():
    user = make_user()
    profile = LeadProfile(tg_user_id=12345, goal="IELTS")
    payload = build_deal_payload(user, profile, "Хочет IELTS к лету.", contact_id="42")
    fields = payload["fields"]
    assert fields["TITLE"] == "Иван — IELTS"
    assert fields["COMMENTS"] == "Хочет IELTS к лету."
    assert fields["CONTACT_ID"] == "42"
    assert fields[settings.bitrix_tg_user_id_field] == "12345"
    assert fields["STAGE_ID"] == settings.bitrix_default_stage
    assert fields["SOURCE_DESCRIPTION"] == "AI-бот Telegram"


def test_deal_update_only_updates_comments():
    payload = build_deal_update_payload("Новое резюме")
    assert payload == {"fields": {"COMMENTS": "Новое резюме"}}
