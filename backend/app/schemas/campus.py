from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CampusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    address: str
    data_notice: str
    is_active: bool
    updated_at: datetime


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    url: str
    publisher: str
    source_type: str
    published_at: datetime | None
    fetched_at: datetime | None
    verified_at: datetime | None
    confidence: float
    is_official: bool
    created_at: datetime
    updated_at: datetime


class LocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    campus_id: str
    name: str
    aliases: list[str]
    category: str
    sub_category: str
    description: str
    address: str
    area: str
    floor: str
    latitude: float | None
    longitude: float | None
    map_x: float | None
    map_y: float | None
    opening_hours: str
    phone: str
    services: list[str]
    payment_methods: list[str]
    verification_status: str
    verification_method: str
    verified_at: datetime | None
    verified_by: str
    confidence: float
    freshness_status: str
    data_status: str
    is_active: bool
    updated_at: datetime
    sources: list[SourceRead] = Field(default_factory=list)


class LocationCreate(BaseModel):
    id: str | None = None
    campus_id: str
    name: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list)
    category: str = Field(min_length=1, max_length=50)
    sub_category: str = ""
    description: str = ""
    address: str = ""
    area: str = ""
    floor: str = ""
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    map_x: float | None = Field(default=None, ge=0, le=1)
    map_y: float | None = Field(default=None, ge=0, le=1)
    opening_hours: str = ""
    phone: str = ""
    services: list[str] = Field(default_factory=list)
    payment_methods: list[str] = Field(default_factory=list)
    verification_status: str = "needs_verification"
    verification_method: str = "admin_entry"
    verified_at: datetime | None = None
    verified_by: str = ""
    confidence: float = Field(default=0.0, ge=0, le=1)
    freshness_status: str = "needs_verification"
    data_status: str = "admin_entry"
    is_active: bool = True
    source_ids: list[str] = Field(default_factory=list)
    evidence: str = ""
    verification_note: str = ""


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    aliases: list[str] | None = None
    category: str | None = None
    description: str | None = None
    address: str | None = None
    area: str | None = None
    floor: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    map_x: float | None = Field(default=None, ge=0, le=1)
    map_y: float | None = Field(default=None, ge=0, le=1)
    opening_hours: str | None = None
    verification_status: str | None = None
    verification_method: str | None = None
    verified_at: datetime | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    freshness_status: str | None = None
    data_status: str | None = None
    is_active: bool | None = None
    source_ids: list[str] | None = None
    evidence: str = ""
    verification_note: str = ""


class StallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    canteen_id: str
    name: str
    floor: str
    food_type: str
    common_items: list[str]
    price_range: str
    meal_periods: list[str]
    opening_hours: str
    payment_methods: list[str]
    is_operating: bool | None
    verification_status: str
    data_status: str
    verified_at: datetime | None
    confidence: float
    is_active: bool


class CanteenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    campus_id: str
    location_id: str | None
    name: str
    floors: list[str]
    opening_hours: str
    payment_methods: list[str]
    verification_status: str
    data_status: str
    verified_at: datetime | None
    confidence: float
    is_active: bool
    source: SourceRead | None = None
    stalls: list[StallRead] = Field(default_factory=list)
    today_menu_available: bool = False
    today_menu_message: str = "没有可靠的今日菜单数据；档口与常见餐品不代表今日供应。"


class FeedbackCreate(BaseModel):
    campus_id: str
    location_id: str | None = None
    content: str = Field(min_length=5, max_length=5000)
    evidence_url: str = Field(default="", max_length=1000)


class ProcessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    campus_id: str | None
    title: str
    category: str
    steps: list[dict]
    materials: list[str]
    contact: str
    verification_status: str
    verified_at: datetime | None
    is_active: bool
    source: SourceRead | None = None
