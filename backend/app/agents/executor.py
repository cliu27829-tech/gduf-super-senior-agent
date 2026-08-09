from __future__ import annotations

import re
from typing import Any

from app.agents.contracts import AgentPlan, ToolResponse
from app.agents.tool_registry import ToolRegistry
from app.agents.tools import AgentToolbox


class AgentExecutor:
    def __init__(self, toolbox: AgentToolbox, legacy_service: Any):
        self.toolbox = toolbox
        self.legacy = legacy_service
        self.registry = ToolRegistry()
        self.registry.register_toolbox(toolbox)
        if not self.registry.complete():
            missing = sorted(set(__import__("app.agents.tool_registry", fromlist=["TOOL_NAMES"]).TOOL_NAMES) - set(self.registry.names))
            raise RuntimeError(f"Agent tools are not fully registered: {missing}")

    @staticmethod
    def _legacy(name: str, result: tuple[str, list[Any], list[dict], str]) -> ToolResponse:
        summary, display_results, sources, data_status = result
        data = display_results[0].data if display_results else None
        return ToolResponse(
            tool_name=name,
            success=True,
            data=data,
            summary=summary,
            sources=sources,
            verification={"data_status": data_status},
        )

    async def execute(self, plan: AgentPlan, message: str, campus_id: str | None) -> list[ToolResponse]:
        intent = plan.intent
        if intent == "campus_location_search":
            return [self._legacy("search_campus_locations", self.legacy._locations(message, campus_id))]
        if intent == "nearby_location_search":
            return [await self.registry.execute("find_nearby_locations")]
        if intent == "campus_navigation":
            location_result = self._legacy("search_campus_locations", self.legacy._locations(message, campus_id))
            results = [location_result]
            rows = location_result.data if isinstance(location_result.data, list) else []
            coordinates = [row for row in rows if row.get("latitude") is not None and row.get("longitude") is not None]
            if len(coordinates) >= 2:
                results.append(await self.registry.execute(
                    "calculate_walking_route",
                    origin_location_id=coordinates[0]["id"],
                    destination_location_id=coordinates[1]["id"],
                ))
            elif len(coordinates) == 1:
                results.append(await self.registry.execute("build_navigation_link", location_id=coordinates[0]["id"]))
            else:
                results.append(ToolResponse(
                    tool_name="calculate_walking_route", success=False,
                    error="unverified_coordinates",
                    summary="匹配地点不足两个，或地点缺少经过核验的真实 GPS 坐标，不能生成路线",
                ))
            return results
        if intent in {"canteen_search", "food_search"}:
            tool = "search_food" if intent == "food_search" else "list_canteens"
            return [self._legacy(tool, self.legacy._canteens(message, campus_id, intent == "food_search"))]
        if intent in {"notification_to_tasks", "document_analysis"}:
            extracted = await self.registry.execute("extract_tasks_from_notification", text=message)
            return [extracted]
        if intent == "task_management":
            return [await self.registry.execute("list_tasks")]
        if intent == "campus_process":
            return [self._legacy("search_campus_processes", self.legacy._processes(message, campus_id))]
        if intent == "knowledge_search":
            return [await self.registry.execute("search_campus_knowledge", query=message)]
        if intent == "knowledge_import":
            article_url = re.search(r"https?://\S+", message)
            if article_url:
                return [await self.registry.execute("import_article_url", url=article_url.group(0))]
            return [await self.registry.execute("import_local_documents")]
        if intent == "calendar_export":
            tasks = await self.registry.execute("list_tasks")
            download = await self.registry.execute("build_calendar_download", task_ids=[row["id"] for row in tasks.data])
            download.requires_user_action = True
            download.summary = "已准备日历下载地址；批量导出需要用户点击确认"
            return [tasks, download]
        if intent == "data_feedback":
            result = await self.registry.execute("search_campus_locations", query=message)
            result.requires_user_action = True
            result.summary += "；提交纠错必须由用户在地点详情中确认"
            return [result]
        return []
