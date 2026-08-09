from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReminderPreviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    title: str = Field(default="", max_length=180)
    task_id: str | None = None
    note_id: str | None = None


class ReminderPreview(BaseModel):
    title: str
    body: str
    remind_at: datetime | None
    timezone: str = "Asia/Shanghai"
    requires_confirmation: bool = True
    explanation: str


class ReminderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    body: str = Field(default="", max_length=5000)
    remind_at: datetime
    timezone: str = Field(default="Asia/Shanghai", pattern=r"^Asia/Shanghai$")
    repeat_rule: str = Field(default="", max_length=120)
    channels: list[str] = Field(default_factory=lambda: ["in_app"], max_length=3)
    task_id: str | None = None
    note_id: str | None = None
    confirmed: bool = False

    @field_validator("channels")
    @classmethod
    def validate_channels(cls, value: list[str]) -> list[str]:
        allowed = {"in_app", "browser"}
        normalized = list(dict.fromkeys(value or ["in_app"]))
        if any(item not in allowed for item in normalized):
            raise ValueError("本地仅支持站内提醒和浏览器通知")
        return normalized


class ReminderUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    body: str | None = Field(default=None, max_length=5000)
    remind_at: datetime | None = None
    repeat_rule: str | None = Field(default=None, max_length=120)
    channels: list[str] | None = None
    status: str | None = Field(default=None, pattern=r"^(scheduled|triggered|dismissed|completed|cancelled)$")
    confirmed: bool = False


class ReminderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    task_id: str | None
    note_id: str | None
    location_id: str | None = None
    location_name: str = ""
    title: str
    body: str
    remind_at: datetime
    timezone: str
    repeat_rule: str
    status: str
    channels: list[str]
    created_at: datetime
    updated_at: datetime
    triggered_at: datetime | None
    dismissed_at: datetime | None
