from __future__ import annotations

import re
from typing import Any

from app.agents.contracts import AgentPlan, ToolResponse
from app.agents.tool_registry import TOOL_NAMES, ToolRegistry
from app.agents.tools import AgentToolbox


QUERY_TOOLS = {
    "search_campus_locations", "list_canteens", "search_food", "search_campus_processes",
    "search_campus_knowledge", "search_learning_materials", "search_campus_facts", "list_notes",
}


class AgentExecutor:
    def __init__(self, toolbox: AgentToolbox, legacy_service: Any):
        self.toolbox = toolbox
        self.legacy = legacy_service
        self.registry = ToolRegistry()
        self.registry.register_toolbox(toolbox)
        if not self.registry.complete():
            missing = sorted(set(TOOL_NAMES) - set(self.registry.names))
            raise RuntimeError(f"Agent tools are not fully registered: {missing}")

    @staticmethod
    def _legacy(name: str, result: tuple[str, list[Any], list[dict], str]) -> ToolResponse:
        summary, display_results, sources, data_status = result
        data = display_results[0].data if display_results else None
        return ToolResponse(tool_name=name, success=True, data=data, summary=summary, sources=sources, verification={"data_status": data_status})

    @staticmethod
    def _matched_locations(results: list[ToolResponse]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for result in results:
            if result.tool_name not in {"search_campus_locations", "find_nearby_locations"}:
                continue
            values = result.data if isinstance(result.data, list) else []
            rows.extend(item for item in values if isinstance(item, dict))
        unique: dict[str, dict[str, Any]] = {str(row.get("id")): row for row in rows if row.get("id")}
        return list(unique.values())

    async def execute(
        self,
        plan: AgentPlan,
        message: str,
        campus_id: str | None,
        history: list[dict[str, str]] | None = None,
    ) -> list[ToolResponse]:
        results: list[ToolResponse] = []
        for step in plan.steps[:4]:
            arguments = {key: value for key, value in step.arguments.items() if key != "confirmed"}
            if step.tool in QUERY_TOOLS:
                arguments["query"] = str(arguments.get("query") or message)
            elif step.tool == "extract_tasks_from_notification":
                arguments["text"] = message
            elif step.tool in {"preview_reminder", "preview_note"}:
                value = message
                if step.tool == "preview_note" and "刚才" in message:
                    value = next((item["content"] for item in reversed(history or []) if item.get("role") == "user"), message)
                arguments["text"] = value
            elif step.tool in {"import_article_url"}:
                found = re.search(r"https?://\S+", message)
                if found:
                    arguments["url"] = found.group(0)
            elif step.tool == "calculate_walking_route":
                locations = self._matched_locations(results)
                if len(locations) >= 2:
                    arguments["origin_location_id"] = locations[0]["id"]
                    arguments["destination_location_id"] = locations[1]["id"]
                elif not arguments.get("origin_location_id") or not arguments.get("destination_location_id"):
                    results.append(ToolResponse(
                        tool_name=step.tool,
                        success=False,
                        error="missing_verified_endpoints",
                        summary="没有同时找到可核验的起点和终点，未生成猜测路线",
                    ))
                    continue
            elif step.tool == "build_calendar_download":
                task_rows = next((item.data for item in results if item.tool_name == "list_tasks" and isinstance(item.data, list)), [])
                arguments["task_ids"] = [row["id"] for row in task_rows if isinstance(row, dict) and row.get("id")]
            if step.tool == "search_campus_locations":
                result = self._legacy(step.tool, self.legacy._locations(message, campus_id))
            elif step.tool in {"list_canteens", "search_food"}:
                result = self._legacy(step.tool, self.legacy._canteens(message, campus_id, step.tool == "search_food"))
            elif step.tool == "search_campus_processes":
                result = self._legacy(step.tool, self.legacy._processes(message, campus_id))
            else:
                result = await self.registry.execute(step.tool, **arguments)
            results.append(result)
        return results
