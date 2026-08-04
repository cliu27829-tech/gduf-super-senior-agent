from __future__ import annotations

from app.agents.contracts import AgentPlan, IntentDecision


INTENT_TOOLS = {
    "campus_location_search": ["search_campus_locations"],
    "nearby_location_search": ["find_nearby_locations"],
    "campus_navigation": ["search_campus_locations", "calculate_walking_route"],
    "canteen_search": ["list_canteens"],
    "food_search": ["search_food"],
    "notification_to_tasks": ["extract_tasks_from_notification", "validate_extracted_tasks"],
    "task_management": ["list_tasks"],
    "campus_process": ["search_campus_processes"],
    "document_analysis": ["extract_tasks_from_notification"],
    "calendar_export": ["generate_tasks_ics", "verify_ics", "build_calendar_download"],
    "data_feedback": ["get_location_details"],
}


class Planner:
    def build(self, decision: IntentDecision) -> AgentPlan:
        tools = INTENT_TOOLS.get(decision.intent, [])
        confirmation = decision.intent in {"notification_to_tasks", "document_analysis", "data_feedback"}
        risks = ["副作用必须由用户在预览界面明确确认"] if confirmation else []
        if decision.intent == "campus_navigation":
            risks.append("只能使用经过核验的真实坐标和后端地图结果")
        return AgentPlan(
            intent=decision.intent,
            tool_names=tools,
            requires_knowledge=decision.intent in {"campus_process"},
            requires_confirmation=confirmation,
            risks=risks,
        )
