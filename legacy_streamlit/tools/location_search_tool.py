"""Thin, serializable adapters exposed to the Agent orchestrator."""

from __future__ import annotations

from typing import Any

from services.location_service import LocationService


def search_locations(query: str, campus: str | None = None, category: str | None = None) -> list[dict[str, Any]]:
    return [item.to_dict() for item in LocationService().search_locations(query, campus, category)]


def get_location(location_id: str) -> dict[str, Any] | None:
    item = LocationService().get_location(location_id)
    return item.to_dict() if item else None


def list_canteens(campus: str | None = None) -> list[dict[str, Any]]:
    return [item.to_dict() for item in LocationService().list_canteens(campus)]


def get_canteen_details(canteen_id: str) -> dict[str, Any] | None:
    return LocationService().get_canteen_details(canteen_id)


def list_food_stalls(**kwargs: Any) -> list[dict[str, Any]]:
    return [item.to_dict() for item in LocationService().list_food_stalls(**kwargs)]


def find_nearby_locations(**kwargs: Any) -> list[dict[str, Any]]:
    return LocationService().find_nearby_locations(**kwargs)


def find_locations_by_category(category: str, campus: str | None = None) -> list[dict[str, Any]]:
    return [
        item.to_dict()
        for item in LocationService().find_locations_by_category(category, campus)
    ]


def build_navigation_link(location_id: str) -> str:
    return LocationService().build_navigation_link(location_id)


def submit_location_feedback(**kwargs: Any) -> str:
    return LocationService().submit_location_feedback(**kwargs)
