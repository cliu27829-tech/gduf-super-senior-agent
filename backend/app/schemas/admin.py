from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminDashboard(BaseModel):
    users: int
    active_users: int
    locations: int
    canteens: int
    pending_feedback: int
    stale_records: int
    recent_errors: int


class AdminUserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern=r"^(user|admin)$")
    is_active: bool | None = None


class FeedbackReview(BaseModel):
    note: str = Field(default="", max_length=5000)


class AuditLogRead(BaseModel):
    id: str
    admin_id: str
    action: str
    entity_type: str
    entity_id: str
    summary: str
    created_at: datetime


class CampusWrite(BaseModel):
    slug: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=2, max_length=64)
    address: str = Field(default="", max_length=255)
    data_notice: str = Field(default="数据待完善", max_length=2000)
    is_active: bool = True


class SourceWrite(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    url: str = Field(default="", max_length=1000)
    publisher: str = Field(default="", max_length=255)
    source_type: str = Field(default="unverified", max_length=40)
    published_at: datetime | None = None
    fetched_at: datetime | None = None
    verified_at: datetime | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    is_official: bool = False


class CampusMapWrite(BaseModel):
    campus_id: str
    image_url: str = Field(min_length=1, max_length=500)
    version: str = Field(default="", max_length=64)
    license_note: str = Field(default="待核验", max_length=2000)
    is_active: bool = True


class CampusMapRead(CampusMapWrite):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class CanteenWrite(BaseModel):
    id: str | None = None
    campus_id: str
    location_id: str | None = None
    source_id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    floors: list[str] = Field(default_factory=list)
    opening_hours: str = Field(default="", max_length=255)
    payment_methods: list[str] = Field(default_factory=list)
    verification_status: str = Field(default="needs_verification", max_length=40)
    data_status: str = Field(default="needs_verification", max_length=40)
    verified_at: datetime | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    is_active: bool = True
    evidence: str = ""
    verification_note: str = ""


class StallWrite(BaseModel):
    id: str | None = None
    canteen_id: str
    name: str = Field(min_length=1, max_length=120)
    floor: str = Field(default="", max_length=80)
    food_type: str = Field(default="", max_length=120)
    common_items: list[str] = Field(default_factory=list)
    price_range: str = Field(default="", max_length=80)
    meal_periods: list[str] = Field(default_factory=list)
    opening_hours: str = Field(default="", max_length=255)
    payment_methods: list[str] = Field(default_factory=list)
    is_operating: bool | None = None
    verification_status: str = Field(default="needs_verification", max_length=40)
    data_status: str = Field(default="needs_verification", max_length=40)
    verified_at: datetime | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    is_active: bool = True
    evidence: str = ""
    verification_note: str = ""


class ProcessWrite(BaseModel):
    id: str | None = None
    campus_id: str | None = None
    source_id: str | None = None
    title: str = Field(min_length=1, max_length=180)
    category: str = Field(default="other", max_length=80)
    steps: list[dict] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    contact: str = Field(default="", max_length=255)
    verification_status: str = Field(default="needs_verification", max_length=40)
    verified_at: datetime | None = None
    is_active: bool = True
    evidence: str = ""
    verification_note: str = ""
