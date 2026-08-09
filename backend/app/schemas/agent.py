from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.map import LocationContext


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    conversation_id: str | None = None
    campus_id: str | None = None
    campus: str | None = Field(default=None, max_length=64)
    location_context: LocationContext | None = None
    resume_navigation: bool = False

    @field_validator("message")
    @classmethod
    def reject_blank_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("消息不能为空")
        return normalized


class AgentStatusResponse(BaseModel):
    backend: str
    llm_configured: bool
    model: str
    database: str


class ToolResult(BaseModel):
    tool: str
    status: str = "success"
    title: str
    data: dict | list | None = None


class AgentChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    intent: str
    plan: list[str] = Field(default_factory=list)
    tools_called: list[str] = Field(default_factory=list)
    tool_success: dict[str, bool] = Field(default_factory=dict)
    answer: str
    tool_results: list[ToolResult] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    locations: list[dict] = Field(default_factory=list)
    route: dict | None = None
    map_action: dict | None = None
    requires_confirmation: bool = False
    degraded: bool = False
    error_id: str | None = None
    data_status: str = "not_applicable"
    current_time: datetime


class NotificationNotice(BaseModel):
    title: str = Field(default="", max_length=255)
    notice_date_text: str = Field(default="", max_length=80)
    notice_date: datetime | None = None
    publisher: str = Field(default="", max_length=255)
    campuses: list[str] = Field(default_factory=list, max_length=10)
    audience: list[str] = Field(default_factory=list, max_length=30)
    category: str = Field(default="", max_length=100)
    summary: str = Field(default="", max_length=1000)


class NotificationActionItem(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    action: str = Field(default="", max_length=2000)
    audience: list[str] = Field(default_factory=list, max_length=30)
    conditions: list[str] = Field(default_factory=list, max_length=30)
    deadline_text: str = Field(default="", max_length=120)
    deadline: datetime | None = None
    location: str = Field(default="", max_length=255)
    submission_method: str = Field(default="", max_length=255)
    submission_target: str = Field(default="", max_length=255)
    file_naming: str = Field(default="", max_length=255)
    materials: list[str] = Field(default_factory=list, max_length=50)
    evidence_requirements: list[str] = Field(default_factory=list, max_length=50)
    notes: list[str] = Field(default_factory=list, max_length=50)
    confidence: float = Field(default=0.0, ge=0, le=1)
    needs_confirmation: bool = False
    is_expired: bool = False
    date_explanation: str = Field(default="", max_length=1000)
    source_title: str = Field(default="", max_length=255)
    source_text: str = Field(default="", max_length=20000)
    source_url: str = Field(default="", max_length=1000)


class NotificationDeadline(BaseModel):
    text: str = Field(default="", max_length=120)
    deadline: datetime | None = None
    action_title: str = Field(default="", max_length=180)
    is_expired: bool = False
    needs_confirmation: bool = False


class NotificationParseResponse(BaseModel):
    notice: NotificationNotice
    rules: list[str] = Field(default_factory=list, max_length=100)
    action_items: list[NotificationActionItem] = Field(default_factory=list, max_length=50)
    deadlines: list[NotificationDeadline] = Field(default_factory=list, max_length=50)
    warnings: list[str] = Field(default_factory=list, max_length=50)
    extraction_mode: str


class NotificationConfirmRequest(BaseModel):
    action_items: list[NotificationActionItem] = Field(min_length=1, max_length=50)
    confirmed: bool
    allow_expired: bool = False
