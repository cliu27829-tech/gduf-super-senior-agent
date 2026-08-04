from __future__ import annotations

from sqlalchemy.orm import Session

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
    "list_canteens": ("canteen_search", "饭堂与档口"),
    "search_food": ("food_search", "饭堂与档口"),
    "extract_tasks_from_notification": ("notification_parser", "通知任务预览"),
    "list_tasks": ("task_list", "我的任务"),
    "search_campus_processes": ("process_search", "校园办事流程"),
    "build_calendar_download": ("calendar_download", "日历导出"),
}


class AgentOrchestrator:
    def __init__(self, db: Session, llm: LLMClient, legacy_service):
        self.db = db
        self.llm = llm
        self.legacy_service = legacy_service
        self.memory = Memory(db)
        self.classifier = IntentClassifier(llm)
        self.planner = Planner()
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
    ) -> AgentChatResponse:
        conversation = self.memory.conversation(user, conversation_id, campus_id, message)
        observation = self.memory.observe(user, conversation)
        decision = await self.classifier.classify(message)
        plan = self.planner.build(decision)
        user_message = Message(conversation_id=conversation.id, role="user", content=message, intent=decision.intent)
        self.db.add(user_message)
        self.db.flush()

        toolbox = AgentToolbox(self.db, user, observation.campus_id)
        tool_responses = await AgentExecutor(toolbox, self.legacy_service).execute(plan, message, observation.campus_id)
        verification = self.verifier.verify(observation, plan, tool_responses)
        trusted_tools = tool_responses if verification.valid else [
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
        answer = await self.llm.chat_completion(messages, temperature=0.6)
        display_results = [self._display(tool) for tool in tool_responses]
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
            sources=sources,
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
                verification={**tool.verification, "pipeline": ["observe", "classify", "plan", "execute", "verify", "confirm", "remember", "respond"]},
                error_code=tool.error or "",
            ))
        self.db.commit()
        self.db.refresh(assistant)
        return AgentChatResponse(
            conversation_id=conversation.id,
            message_id=assistant.id,
            intent=decision.intent,
            answer=answer,
            tool_results=display_results,
            sources=sources,
            requires_confirmation=plan.requires_confirmation or any(tool.requires_user_action for tool in tool_responses),
            degraded=False,
            error_id=None,
            data_status=verification.data_status,
            current_time=observation.current_time,
        )
