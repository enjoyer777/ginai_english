from __future__ import annotations

from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field


Direction = Literal["работа", "переезд", "путешествия", "для себя"]
Level = Literal["A0-A1", "A2", "B1", "B2"]


class Course(BaseModel):
    id: str
    name: str
    direction: Direction
    levels: list[Level]
    duration_weeks: int
    format: str
    price_rub: int
    installment: bool
    description: str
    nearest_start: date | None = None


class ScheduleSlot(BaseModel):
    course_id: str
    start_date: date
    days_time: str
    teacher_name: str
    seats_left: int


class Teacher(BaseModel):
    name: str
    experience_years: int
    specialization: str
    bio: str


class FAQItem(BaseModel):
    question: str
    answer: str


class Settings(BaseModel):
    """Настройки школы: рабочие часы, контакты, тексты приветствия и disclaimer."""

    working_hours: dict[str, tuple[time, time] | None] = Field(default_factory=dict)
    contacts: dict[str, str] = Field(default_factory=dict)
    socials: dict[str, str] = Field(default_factory=dict)
    greeting_text: str = ""
    pii_disclaimer: str = ""


class KBSnapshot(BaseModel):
    """Полный снимок базы знаний на момент загрузки."""

    courses: list[Course] = Field(default_factory=list)
    schedules: list[ScheduleSlot] = Field(default_factory=list)
    teachers: list[Teacher] = Field(default_factory=list)
    faq: list[FAQItem] = Field(default_factory=list)
    settings: Settings = Field(default_factory=Settings)
