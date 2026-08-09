from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotePreviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    source_message_id: str | None = None


class NotePreview(BaseModel):
    title: str
    content: str
    tags: list[str]
    source_message_id: str | None = None
    requires_confirmation: bool = True


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    content: str = Field(min_length=1, max_length=20000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    pinned: bool = False
    source_message_id: str | None = None
    confirmed: bool = False


class NoteUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    content: str | None = Field(default=None, min_length=1, max_length=20000)
    tags: list[str] | None = None
    pinned: bool | None = None
    confirmed: bool = False


class NoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    title: str
    content: str
    tags: list[str]
    pinned: bool
    source_message_id: str | None
    created_at: datetime
    updated_at: datetime
