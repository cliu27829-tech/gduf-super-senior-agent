from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.orm import Session
from fastapi.encoders import jsonable_encoder

from app.agents.contracts import ToolResponse
from app.agents.executor import AgentExecutor
from app.agents.intent_classifier import IntentClassifier
from app.agents.memory import Memory
from app.agents.planner import Planner
from app.agents.prompts import system_prompt
from app.agents.tools import AgentToolbox
from app.agents.verifier import Verifier
from app.core.llm_client import LLMClient
from app.models.entities import Message, ToolExecution, User
from app.schemas.agent import AgentChatResponse, ToolResult


DISPLAY = {
    "search_campus_locations": ("location_search", "校园地点"),
    "find_nearby_locations": ("nearby_location_search", "附近地点"),
    "calculate_walking_route": ("walking_route", "步行路线"),
    "build_navigation_link": ("navigation_link", "开始导航"),
    "list_canteens": ("canteen_search", "饭堂与档口"),
    "search_food": ("food_search", "饭堂与档口"),
    "extract_tasks_from_notification": ("notification_parser", "通知任务预览"),
    "list_tasks": ("task_list", "我的任务"),
    "search_campus_processes": ("process_search", "校园办事流程"),
    "search_campus_knowledge": ("knowledge_search", "知识库检索"),
    "import_local_documents": ("knowledge_import", "导入私有知识"),
    "import_article_url": ("knowledge_import", "导入文章链接"),
    "build_calendar_download": ("calendar_download", "日历导出"),
    "search_campus_facts": ("campus_fact_search", "校园事实"),
    "list_campus_colleges": ("campus_colleges", "学院口径"),
    "preview_reminder": ("reminder_preview", "提醒预览"),
    "list_reminders": ("reminder_list", "我的提醒"),
    "preview_note": ("note_preview", "便签预览"),
    "list_notes": ("note_list", "我的便签"),
    "get_daily_summary": ("daily_summary", "近期安排"),
    "search_express_locations": ("express_locations", "快递地点"),
}


class AgentOrchestrator:
    def __init__(self, db: Session, llm: LLMClient, legacy_service):
        self.db = db
        self.llm = llm
        self.legacy_service = legacy_service
        self.memory = Memory(db)
        self.classifier = IntentClassifier(llm)
        self.planner = Planner(llm)
        self.verifier = Verifier()

    @staticmethod
    def _display(tool: ToolResponse) -> ToolResult:
        name, title = DISPLAY.get(tool.tool_name, (tool.tool_name, tool.tool_name.replace("_", " ")))
        return ToolResult(tool=name, status="success" if tool.success else "error", title=title, data=tool.data)

    async def run(
        self,
        user: User,
        message: str,
        conversation_id: str | None,
        campus_id: str | None,
        on_event: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
    ) -> AgentChatResponse:
        async def emit(event: str, data: dict[str, Any]) -> None:
            if on_event:
                await on_event(event, data)

        conversation = self.memory.conversation(user, conversation_id, campus_id, message)
        observation = self.memory.observe(user, conversation)
        await emit("stage", {"stage": "classify", "label": "正在理解你的问题"})
        decision = await self.classifier.classify(message)
        await emit("stage", {"stage": "plan", "label": "正在规划需要核对的信息"})
        plan = await self.planner.build(decision, message)
        user_message = Message(conversation_id=conversation.id, role="user", content=message, intent=decision.intent)
        self.db.add(user_message)
        self.db.flush()

        toolbox = AgentToolbox(self.db, user, observation.campus_id)
        executor = AgentExecutor(toolbox, self.legacy_service)
        await emit("stage", {"stage": "execute", "label": "正在查询校园资料" if plan.steps else "正在组织回答"})
        tool_responses = await executor.execute(plan, message, observation.campus_id, observation.history)
        for tool in tool_responses:
            await emit("tool", {"tool": tool.tool_name, "success": tool.success, "summary": tool.summary})
        if replan := await self.planner.replan(decision, message, plan, tool_responses):
            await emit("stage", {"stage": "replan", "label": "正在根据查询结果调整计划"})
            tool_responses.extend(await executor.execute(replan, message, observation.campus_id, observation.history))
            plan = replan
        await emit("stage", {"stage": "verify", "label": "正在核对来源与校区"})
        verification = self.verifier.verify(observation, plan, tool_responses)
        trusted_tools = tool_responses if verification.checks.get("campus_isolated", False) else [
            ToolResponse(
                tool_name=tool.tool_name, success=False, summary="工具结果未通过校区或完整性校验",
                error="verification_failed", verification=verification.model_dump(mode="json"),
            ) for tool in tool_responses
        ]
        messages = [
            {"role": "system", "content": system_prompt(observation, trusted_tools, verification)},
            *observation.history,
            {"role": "user", "content": message},
        ]
        await emit("stage", {"stage": "respond", "label": "正在生成回答"})
        if on_event:
            chunks: list[str] = []
            async for token in self.llm.stream_completion(messages):
                chunks.append(token)
                await emit("token", {"content": token})
            answer = "".join(chunks).strip()
            if not answer:
                from app.core.llm_client import LLMProviderError
                raise LLMProviderError()
        else:
            answer = await self.llm.chat_completion(messages, temperature=0.6)
        display_results = [self._display(tool) for tool in tool_responses]
        locations: list[dict] = []
        route: dict | None = None
        for tool in tool_responses:
            if tool.tool_name in {"search_campus_locations", "find_nearby_locations"}:
                rows = tool.data if isinstance(tool.data, list) else [tool.data] if isinstance(tool.data, dict) else []
                locations.extend(row for row in rows if isinstance(row, dict))
            if tool.tool_name == "calculate_walking_route" and tool.success and isinstance(tool.data, dict):
                route = tool.data
        map_action = None
        if route:
            map_action = {
                "type": "route",
                "url": f"/map?origin={route.get('origin_location_id', '')}&destination={route.get('destination_location_id', '')}",
                "campus_id": observation.campus_id,
            }
        elif locations:
            map_action = {
                "type": "focus_location",
                "url": f"/map?location={locations[0].get('id', '')}",
                "location_id": locations[0].get("id"),
                "campus_id": observation.campus_id,
            }
        sources: list[dict] = []
        seen: set[str] = set()
        for tool in tool_responses:
            for source in tool.sources:
                key = str(source.get("id") or source.get("url") or source.get("title"))
                if key not in seen:
                    seen.add(key); sources.append(source)
        assistant = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            intent=decision.intent,
            tool_results=[item.model_dump(mode="json") for item in display_results],
            sources=jsonable_encoder(sources),
        )
        self.db.add(assistant)
        self.db.flush()
        for tool in tool_responses:
            self.db.add(ToolExecution(
                conversation_id=conversation.id,
                message_id=assistant.id,
                tool_name=tool.tool_name,
                success=tool.success,
                summary=tool.summary,
                verification={
                    **tool.verification,
                    "intent": decision.intent,
                    "plan": [step.model_dump(mode="json") for step in plan.steps],
                    "agent_round": plan.agent_round,
                    "tools_called": [item.tool_name for item in tool_responses],
                    "tool_success": {item.tool_name: item.success for item in tool_responses},
                    "verification": verification.model_dump(mode="json"),
                    "final_status": "success" if verification.valid else "verification_failed",
                    "pipeline": ["observe", "reason", "plan", "execute", "observe_tool", "replan", "verify", "respond"],
                },
                error_code=tool.error or "",
            ))
        self.db.commit()
        self.db.refresh(assistant)
        response = AgentChatResponse(
            conversation_id=conversation.id,
            message_id=assistant.id,
            intent=decision.intent,
            plan=plan.required_tools,
            tools_called=[tool.tool_name for tool in tool_responses],
            tool_success={tool.tool_name: tool.success for tool in tool_responses},
            answer=answer,
            tool_results=display_results,
            sources=sources,
            locations=locations,
            route=route,
            map_action=map_action,
            requires_confirmation=plan.requires_confirmation or any(tool.requires_user_action for tool in tool_responses),
            degraded=False,
            error_id=None,
            data_status=verification.data_status,
            current_time=observation.current_time,
        )
        await emit("final", response.model_dump(mode="json"))
        return response
