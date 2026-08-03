"""Pure map helpers kept testable without Streamlit."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Iterable

from core.models import CampusLocation
from core.time_service import now_china


def is_currently_open(location: CampusLocation, reference_time: datetime | None = None) -> bool:
    if location.freshness_status != "current" or not location.opening_hours:
        return False
    match = re.search(r"(\d{1,2}):(\d{2})\s*[-~至]\s*(\d{1,2}):(\d{2})", location.opening_hours)
    if not match:
        return False
    current = now_china(reference_time)
    current_minutes = current.hour * 60 + current.minute
    start = int(match.group(1)) * 60 + int(match.group(2))
    end = int(match.group(3)) * 60 + int(match.group(4))
    return start <= current_minutes <= end


def filter_locations(
    locations: Iterable[CampusLocation],
    query: str = "",
    category: str | None = None,
    canteen_only: bool = False,
    open_only: bool = False,
    reference_time: datetime | None = None,
) -> list[CampusLocation]:
    needle = query.strip().casefold()
    results = []
    for location in locations:
        if category and location.category != category:
            continue
        if canteen_only and location.category != "canteen":
            continue
        if open_only and not is_currently_open(location, reference_time):
            continue
        haystack = " ".join([location.name, *location.aliases, location.description]).casefold()
        if needle and needle not in haystack:
            continue
        results.append(location)
    return results


def build_map_rows(locations: Iterable[CampusLocation]) -> list[dict]:
    return [
        {
            "id": item.id,
            "name": item.name,
            "campus": item.campus,
            "category": item.category,
            "latitude": item.latitude,
            "longitude": item.longitude,
            "map_x": item.map_x,
            "map_y": item.map_y,
            "freshness_status": item.freshness_status,
            "coordinate_type": "gps" if item.latitude is not None and item.longitude is not None else "schematic",
        }
        for item in locations
        if (item.latitude is not None and item.longitude is not None)
        or (item.map_x is not None and item.map_y is not None)
    ]
