from __future__ import annotations

import json

from app.agents.contracts import AgentPlan, AgentPlanStep, IntentDecision, ToolResponse
from app.agents.tool_registry import TOOL_NAMES
from app.core.llm_client import LLMClient


FACT_TOOLS = {
    "campus_location_search": ["search_campus_locations"],
    "nearby_location_search": ["find_nearby_locations"],
    "campus_navigation": ["search_campus_locations", "calculate_walking_route"],
    "canteen_search": ["list_canteens"],
    "food_search": ["search_food"],
    "notification_to_tasks": ["extract_tasks_from_notification", "validate_extracted_tasks"],
    "task_management": ["list_tasks"],
    "campus_process": ["search_campus_processes"],
    "knowledge_search": ["search_campus_knowledge"],
    "document_analysis": ["extract_tasks_from_notification"],
    "calendar_export": ["list_tasks", "build_calendar_download"],
    "campus_fact_search": ["search_campus_facts", "list_campus_colleges"],
    "reminder_management": ["preview_reminder"],
    "note_management": ["preview_note"],
    "daily_summary": ["get_daily_summary"],
}

STRICT_INTENT_TOOLS = {
    "notification_to_tasks": ["extract_tasks_from_notification", "validate_extracted_tasks"],
    "reminder_management": ["preview_reminder"],
    "note_management": ["preview_note"],
    "campus_fact_search": ["search_campus_facts", "list_campus_colleges"],
    "daily_summary": ["get_daily_summary"],
}


class Planner:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    @staticmethod
    def _fallback(decision: IntentDecision, message: str, round_number: int = 1) -> AgentPlan:
        names = [name for name in decision.tool_plan if name in TOOL_NAMES]
        if not names:
            names = FACT_TOOLS.get(decision.intent, [])
        if decision.intent == "campus_navigation":
            requested = ["search_campus_locations"]
            if any(term in message for term in ("吃", "饭堂", "食堂", "饭")):
                requested.append("list_canteens")
            if any(term in message for term in ("快递", "取件", "驿站")):
                requested.append("search_express_locations")
            requested.append("calculate_walking_route")
            names = requested
        names = list(dict.fromkeys(names))[:4]
        steps = [AgentPlanStep(tool=name, purpose="获取回答所需的可核验信息", arguments={"query": message}) for name in names]
        confirmation = decision.intent in {"notification_to_tasks", "document_analysis", "knowledge_import", "data_feedback", "reminder_management", "note_management"}
        return AgentPlan(
            intent=decision.intent,
            goal=message[:200],
            steps=steps,
            required_tools=names,
            requires_knowledge=bool(names),
            requires_confirmation=confirmation,
            risk_level="medium" if confirmation else "low",
            risks=["涉及写入的动作只能返回预览，必须由用户再次确认"] if confirmation else [],
            agent_round=round_number,
        )

    async def build(self, decision: IntentDecision, message: str) -> AgentPlan:
        allowed = sorted(TOOL_NAMES)
        prompt = (
            "你是广金大师兄的执行规划器。只输出 JSON，不回答用户。"
            "字段必须是 intent,goal,steps,required_tools,requires_knowledge,requires_confirmation,"
            "missing_information,risk_level,risks,agent_round。"
            "steps 每项必须有 tool,purpose,arguments，最多4步。tool只能来自允许列表。"
            "地点、路线、饭堂、学院、校内事实必须使用工具；复杂行程要组合地点、饭堂/快递和路线工具。"
            "创建、修改、删除、保存、取消只规划预览，不得把 confirmed 设为 true。"
            f"允许工具：{allowed}"
        )
        try:
            raw = await self.llm.chat_completion(
                [{"role": "system", "content": prompt}, {
                    "role": "user",
                    "content": json.dumps({"message": message, "intent": decision.model_dump()}, ensure_ascii=False),
                }],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            plan = AgentPlan.model_validate(json.loads(raw))
            valid_steps = [step for step in plan.steps if step.tool in TOOL_NAMES][:4]
            if len(valid_steps) != len(plan.steps):
                raise ValueError("plan contains unknown tools")
            if required := STRICT_INTENT_TOOLS.get(decision.intent):
                by_tool = {step.tool: step for step in valid_steps}
                valid_steps = [
                    by_tool.get(name) or AgentPlanStep(
                        tool=name,
                        purpose="执行该意图要求的安全预览或只读查询",
                        arguments={"query": message},
                    )
                    for name in required
                ]
            if decision.intent == "campus_navigation":
                by_tool = {step.tool: step for step in valid_steps}
                by_tool.setdefault("search_campus_locations", AgentPlanStep(tool="search_campus_locations", purpose="查找行程中的校内地点", arguments={"query": message}))
                if any(term in message for term in ("吃", "饭堂", "食堂", "饭")):
                    by_tool.setdefault("list_canteens", AgentPlanStep(tool="list_canteens", purpose="查找途中可用的饭堂资料", arguments={"query": message}))
                if any(term in message for term in ("快递", "取件", "驿站")):
                    by_tool.setdefault("search_express_locations", AgentPlanStep(tool="search_express_locations", purpose="查找快递服务地点", arguments={}))
                by_tool.setdefault("calculate_walking_route", AgentPlanStep(tool="calculate_walking_route", purpose="使用核验坐标或校内路径图计算路线", arguments={}))
                order = ["search_campus_locations", "list_canteens", "search_express_locations", "calculate_walking_route"]
                valid_steps = [by_tool[name] for name in order if name in by_tool][:4]
            plan.steps = valid_steps
            plan.required_tools = list(dict.fromkeys(step.tool for step in valid_steps))
            plan.agent_round = 1
            return plan
        except Exception:
            return self._fallback(decision, message)

    async def replan(
        self,
        decision: IntentDecision,
        message: str,
        previous: AgentPlan,
        results: list[ToolResponse],
    ) -> AgentPlan | None:
        failed = [result.tool_name for result in results if not result.success]
        missing = [name for name in previous.required_tools if name not in {result.tool_name for result in results}]
        if not failed and not missing:
            return None
        fallback = self._fallback(decision, message, min(previous.agent_round + 1, 4))
        attempted = {result.tool_name for result in results}
        fallback.steps = [step for step in fallback.steps if step.tool not in attempted][:4]
        fallback.required_tools = [step.tool for step in fallback.steps]
        return fallback if fallback.steps else None
