"""Typed domain models shared by services, tools, and Streamlit pages."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


CAMPUSES = ("广州校本部", "肇庆校区", "清远校区")
LOCATION_CATEGORIES = (
    "canteen",
    "food_stall",
    "teaching_building",
    "dormitory",
    "library",
    "medical",
    "express_station",
    "supermarket",
    "sports",
    "campus_gate",
    "administrative_service",
    "campus_card_service",
    "atm",
    "printing",
    "other",
)


@dataclass
class SourceReference:
    title: str
    url: str
    publisher: str = ""
    published_at: str | None = None
    fetched_at: str | None = None
    source_level: int = 8
    is_official: bool = False
    source_status: str = "unverified"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SourceReference":
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value.get(key) for key in allowed if key in value})


@dataclass
class CampusLocation:
    id: str
    name: str
    aliases: list[str]
    campus: str
    category: str
    sub_category: str = ""
    description: str = ""
    building: str = ""
    floor: str = ""
    area: str = ""
    latitude: float | None = None
    longitude: float | None = None
    map_x: float | None = None
    map_y: float | None = None
    address: str = ""
    opening_hours: str = ""
    phone: str = ""
    services: list[str] = field(default_factory=list)
    payment_methods: list[str] = field(default_factory=list)
    navigation_url: str = ""
    source_references: list[SourceReference] = field(default_factory=list)
    verification_method: str = "unverified_seed"
    verified_at: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None
    freshness_status: str = "needs_verification"
    confidence: float = 0.0
    is_active: bool = True
    data_status: str = "demo_fixture"
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        if self.campus not in CAMPUSES:
            raise ValueError(f"Unsupported campus: {self.campus}")
        if self.category not in LOCATION_CATEGORIES:
            raise ValueError(f"Unsupported location category: {self.category}")
        self.confidence = max(0.0, min(float(self.confidence), 1.0))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CampusLocation":
        data = dict(value)
        data["aliases"] = list(data.get("aliases") or [])
        data["services"] = list(data.get("services") or [])
        data["payment_methods"] = list(data.get("payment_methods") or [])
        data["source_references"] = [
            item if isinstance(item, SourceReference) else SourceReference.from_dict(item)
            for item in data.get("source_references") or []
        ]
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: data.get(key) for key in allowed if key in data})


@dataclass
class CanteenInfo:
    id: str
    canteen_id: str
    name: str
    campus: str
    floor: str = ""
    food_type: str = ""
    common_items: list[str] = field(default_factory=list)
    price_range: str = ""
    meal_periods: list[str] = field(default_factory=list)
    opening_hours: str = ""
    payment_methods: list[str] = field(default_factory=list)
    is_operating: bool | None = None
    verified_at: str | None = None
    source_references: list[SourceReference] = field(default_factory=list)
    confidence: float = 0.0
    data_status: str = "demo_fixture"
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CanteenInfo":
        data = dict(value)
        for key in ("common_items", "meal_periods", "payment_methods"):
            data[key] = list(data.get(key) or [])
        data["source_references"] = [
            item if isinstance(item, SourceReference) else SourceReference.from_dict(item)
            for item in data.get("source_references") or []
        ]
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: data.get(key) for key in allowed if key in data})


@dataclass
class FreshnessResult:
    status: str
    age_days: int | None
    threshold_days: int
    warning: str


@dataclass
class TaskItem:
    id: str
    user_id: str
    title: str
    deadline: str | None = None
    location: str = ""
    materials: list[str] = field(default_factory=list)
    submission_method: str = ""
    source_text: str = ""
    source_url: str = ""
    status: str = "pending"
    needs_confirmation: bool = False
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
