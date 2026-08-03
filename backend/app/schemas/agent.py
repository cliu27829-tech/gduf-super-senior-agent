from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    conversation_id: str | None = None
    campus_id: str | None = None
    campus: str | None = Field(default=None, max_length=64)


class ToolResult(BaseModel):
    tool: str
    status: str = "success"
    title: str
    data: dict | list | None = None


class AgentChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    intent: str
    answer: str
    tool_results: list[ToolResult] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    requires_confirmation: bool = False
    degraded: bool = False
    error_id: str | None = None
    data_status: str = "not_applicable"
    current_time: datetime


class NotificationDraft(BaseModel):
    title: str
    deadline: datetime | None
    location: str = ""
    materials: list[str] = Field(default_factory=list)
    submission_target: str = ""
    submission_method: str = ""
    file_naming: str = ""
    notes: str = ""
    source_text: str = ""
    source_url: str = ""
    needs_confirmation: bool = False
    confidence: float = 0.0
    date_explanation: str = ""


class NotificationParseResponse(BaseModel):
    drafts: list[NotificationDraft]
    extraction_mode: str
    warning: str = ""


class NotificationConfirmRequest(BaseModel):
    drafts: list[NotificationDraft] = Field(min_length=1, max_length=50)
    confirmed: bool
