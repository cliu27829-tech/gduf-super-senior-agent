from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=5000)
    deadline: datetime | None = None
    location: str = Field(default="", max_length=255)
    course: str = Field(default="", max_length=120)
    task_type: str = Field(default="general", max_length=80)
    materials: list[str] = Field(default_factory=list, max_length=50)
    submission_target: str = Field(default="", max_length=255)
    submission_method: str = Field(default="", max_length=255)
    file_naming: str = Field(default="", max_length=255)
    source_text: str = Field(default="", max_length=20000)
    source_url: str = Field(default="", max_length=1000)
    needs_confirmation: bool = False
    reminder_minutes: list[int] = Field(default_factory=lambda: [1440, 180], max_length=10)


class TaskCreate(TaskBase):
    confirmed: bool = True


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = Field(default=None, max_length=5000)
    deadline: datetime | None = None
    location: str | None = Field(default=None, max_length=255)
    course: str | None = Field(default=None, max_length=120)
    task_type: str | None = Field(default=None, max_length=80)
    materials: list[str] | None = None
    submission_target: str | None = Field(default=None, max_length=255)
    submission_method: str | None = Field(default=None, max_length=255)
    file_naming: str | None = Field(default=None, max_length=255)
    source_text: str | None = Field(default=None, max_length=20000)
    source_url: str | None = Field(default=None, max_length=1000)
    status: str | None = Field(default=None, pattern=r"^(pending|completed)$")


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    title: str
    description: str
    deadline: datetime | None
    location: str
    course: str
    task_type: str
    materials: list[str]
    submission_target: str
    submission_method: str
    file_naming: str
    source_text: str
    source_url: str
    status: str
    needs_confirmation: bool
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BulkTaskAction(BaseModel):
    task_ids: list[str] = Field(min_length=1, max_length=100)
    action: str = Field(pattern=r"^(complete|reopen|delete)$")
