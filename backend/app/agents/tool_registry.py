from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from app.agents.contracts import ToolResponse


ToolHandler = Callable[..., ToolResponse | Awaitable[ToolResponse]]

TOOL_NAMES = (
    "search_campus_locations", "get_location_details", "find_nearby_locations", "list_location_categories",
    "calculate_walking_route", "build_navigation_link", "geocode_campus_address",
    "list_canteens", "get_canteen_details", "list_food_stalls", "search_food",
    "filter_canteens_by_opening_hours", "calculate_canteen_freshness",
    "create_task", "create_tasks", "list_tasks", "get_task", "update_task", "delete_task",
    "complete_task", "reopen_task", "list_overdue_tasks", "list_upcoming_tasks",
    "extract_tasks_from_notification", "parse_deadline", "validate_extracted_tasks", "save_confirmed_tasks",
    "generate_task_ics", "generate_tasks_ics", "verify_ics", "build_calendar_download",
    "search_campus_processes", "get_process_details", "save_process_as_tasks",
    "search_campus_knowledge", "search_learning_materials", "get_source_details",
    "get_user_profile", "update_user_preference", "get_preferred_address",
)


class ToolRegistry:
    def __init__(self):
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, name: str, handler: ToolHandler) -> None:
        if name not in TOOL_NAMES:
            raise ValueError(f"unknown tool: {name}")
        self._handlers[name] = handler

    def register_toolbox(self, toolbox: object) -> None:
        for name in TOOL_NAMES:
            handler = getattr(toolbox, name, None)
            if callable(handler):
                self.register(name, handler)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    def complete(self) -> bool:
        return set(self._handlers) == set(TOOL_NAMES)

    async def execute(self, name: str, **kwargs: Any) -> ToolResponse:
        handler = self._handlers.get(name)
        if not handler:
            return ToolResponse(tool_name=name, success=False, error="工具未注册", summary="工具不可用")
        try:
            result = handler(**kwargs)
            if inspect.isawaitable(result):
                result = await result
            return result
        except Exception as exc:
            return ToolResponse(
                tool_name=name,
                success=False,
                error=type(exc).__name__,
                summary="工具执行失败，未写入未经确认的副作用",
                verification={"exception_type": type(exc).__name__},
            )
