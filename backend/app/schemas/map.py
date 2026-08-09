from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class LocationContext(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy: float = Field(gt=0, le=10_000)
    captured_at: datetime | None = None


class RouteFromCurrentRequest(BaseModel):
    origin: LocationContext
    destination_location_id: str = Field(min_length=1, max_length=64)
    mode: str = "walking"

    @field_validator("mode")
    @classmethod
    def walking_only(cls, value: str) -> str:
        if value != "walking":
            raise ValueError("当前仅支持步行路线")
        return value


class RouteFromCurrentResponse(BaseModel):
    provider: str
    origin: LocationContext
    destination_location_id: str
    destination_name: str
    destination_longitude: float
    destination_latitude: float
    distance_meters: int
    duration_seconds: int
    steps: list[dict] = Field(default_factory=list)
    polyline: list[list[float]] = Field(default_factory=list)
    accuracy_status: str
    accuracy_message: str
    off_campus: bool
    privacy: str = "当前位置仅用于本次路线规划，服务端不会保存 GPS。"
