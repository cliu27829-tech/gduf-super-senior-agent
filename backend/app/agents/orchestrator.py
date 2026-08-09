from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi.encoders import jsonable_encoder

from app.agents.contracts import ToolResponse
from app.agents.executor import AgentExecutor
from app.agents.intent_classifier import IntentClassifier
from app.agents.memory import Memory
from app.agents.planner import Planner
from app.agents.prompts import system_prompt
from app.agents.run_store import AgentRunStore, public_step
from app.agents.tools import AgentToolbox
from app.agents.verifier import Verifier
from app.core.llm_client import LLMClient
from app.models.entities import Campus, Location, Message, ToolExecution, User
from app.schemas.map import LocationContext
from app.schemas.agent import AgentAction, AgentChatResponse, ToolResult
from app.services.map_service import MapService, MapServiceError
from app.services.navigation_service import resolve_navigation_destination


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

    @staticmethod
    def _actions(tool_responses: list[ToolResponse], map_action: dict[str, Any] | None) -> list[AgentAction]:
        actions: list[AgentAction] = []
        if map_action and map_action.get("url"):
            actions.append(AgentAction(
                id="open-map",
                type="navigation",
                label="开始导航" if map_action.get("type") in {"route", "client_route"} else "在地图中查看",
                url=str(map_action["url"]),
            ))
        for tool in tool_responses:
            data = tool.data if isinstance(tool.data, dict) else {}
            if tool.tool_name == "preview_reminder" and data.get("remind_at"):
                actions.append(AgentAction(
                    id="save-reminder", type="reminder", label="确认保存提醒",
                    api_path="/reminders", method="POST", payload={**data, "confirmed": True},
                    requires_confirmation=True,
                ))
            elif tool.tool_name == "preview_note" and data:
                actions.append(AgentAction(
                    id="save-note", type="note", label="确认保存便签",
                    api_path="/notes", method="POST", payload={**data, "confirmed": True},
                    requires_confirmation=True,
                ))
            elif tool.tool_name == "extract_tasks_from_notification" and data.get("action_items"):
                actions.append(AgentAction(
                    id="save-notification-tasks", type="task", label="保存任务并设置提醒",
                    api_path="/notifications/confirm", method="POST",
                    payload={"action_items": data["action_items"], "confirmed": True, "allow_expired": False},
                    requires_confirmation=True,
                ))
        return actions

    async def run(
        self,
        user: User,
        message: str,
        conversation_id: str | None,
        campus_id: str | None,
        on_event: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        location_context: LocationContext | None = None,
        resume_navigation: bool = False,
        agent_run_id: str | None = None,
    ) -> AgentChatResponse:
        async def emit(event: str, data: dict[str, Any]) -> None:
            if on_event:
                await on_event(event, data)

        effective_campus_id = campus_id or user.campus_id
        navigation_destination = resolve_navigation_destination(self.db, effective_campus_id, message)
        if navigation_destination:
            return await self._navigation(
                user,
                message,
                conversation_id,
                effective_campus_id,
                navigation_destination,
                location_context,
                resume_navigation,
                emit,
                agent_run_id,
            )

        conversation = self.memory.conversation(user, conversation_id, campus_id, message)
        observation = self.memory.observe(user, conversation)
        run_store = AgentRunStore(self.db)
        agent_run = run_store.create_or_resume(
            user,
            conversation,
            message,
            run_id=agent_run_id,
            context={"campus_id": observation.campus_id, "conversation_id": conversation.id},
        )
        await emit("run", {"id": agent_run.id, "status": agent_run.status, "goal": agent_run.goal})
        await emit("stage", {"stage": "classify", "label": "正在理解你的问题"})
        decision = await self.classifier.classify(message)
        await emit("stage", {"stage": "plan", "label": "正在规划需要核对的信息"})
        plan = await self.planner.build(decision, message)
        agent_run.intent = decision.intent
        agent_run.completion_condition = plan.completion_condition
        run_store.transition(agent_run, "executing")
        await emit("plan", {
            "run_id": agent_run.id,
            "goal": plan.goal,
            "completion_condition": plan.completion_condition,
            "steps": [{"tool": step.tool, "label": step.purpose, "reason": step.reason} for step in plan.steps],
        })
        user_message = Message(conversation_id=conversation.id, role="user", content=message, intent=decision.intent)
        self.db.add(user_message)
        self.db.flush()

        toolbox = AgentToolbox(self.db, user, observation.campus_id)
        executor = AgentExecutor(toolbox, self.legacy_service)
        await emit("stage", {"stage": "execute", "label": "正在查询校园资料" if plan.steps else "正在组织回答"})
        tool_responses: list[ToolResponse] = []
        pending_steps = list(plan.steps)
        executed_tools: set[str] = set()
        while pending_steps and len(tool_responses) < 6:
            step = pending_steps.pop(0)
            if step.tool in executed_tools:
                continue
            executed_tools.add(step.tool)
            persisted_step = run_store.start_step(
                agent_run,
                step_type="tool",
                tool_name=step.tool,
                public_label=step.purpose or DISPLAY.get(step.tool, ("", step.tool))[1],
                round_number=plan.agent_round,
            )
            await emit("tool_start", {
                "run_id": agent_run.id, "step_id": persisted_step.id,
                "tool": step.tool, "label": persisted_step.public_label,
            })
            tool = await executor.execute_step(
                step, message, observation.campus_id, observation.history, tool_responses
            )
            tool_responses.append(tool)
            run_store.finish_step(persisted_step, tool.success, tool.summary or tool.error or "")
            await emit("tool_end", {
                "run_id": agent_run.id, "step_id": persisted_step.id,
                "tool": tool.tool_name, "success": tool.success, "summary": tool.summary,
            })
            # The next step receives every prior result through execute_step. This
            # makes routing/calendar steps depend on observed IDs, not a frozen plan.
        if replan := await self.planner.replan(decision, message, plan, tool_responses):
            await emit("stage", {"stage": "replan", "label": "正在根据查询结果调整计划"})
            await emit("plan", {
                "run_id": agent_run.id, "round": replan.agent_round,
                "steps": [{"tool": step.tool, "label": step.purpose, "reason": step.reason} for step in replan.steps],
            })
            for step in replan.steps:
                if len(tool_responses) >= 6 or step.tool in executed_tools:
                    continue
                executed_tools.add(step.tool)
                persisted_step = run_store.start_step(
                    agent_run, step_type="tool", tool_name=step.tool,
                    public_label=step.purpose, round_number=replan.agent_round,
                )
                await emit("tool_start", {"run_id": agent_run.id, "step_id": persisted_step.id, "tool": step.tool, "label": persisted_step.public_label})
                tool = await executor.execute_step(step, message, observation.campus_id, observation.history, tool_responses)
                tool_responses.append(tool)
                run_store.finish_step(persisted_step, tool.success, tool.summary or tool.error or "")
                await emit("tool_end", {"run_id": agent_run.id, "step_id": persisted_step.id, "tool": tool.tool_name, "success": tool.success, "summary": tool.summary})
            plan = replan
        await emit("stage", {"stage": "verify", "label": "正在核对来源与校区"})
        run_store.transition(agent_run, "verifying")
        verify_step = run_store.start_step(agent_run, step_type="verify", public_label="核对来源、校区和结果完整性")
        verification = self.verifier.verify(observation, plan, tool_responses)
        run_store.finish_step(verify_step, verification.valid, "；".join(verification.warnings) or "核验通过")
        await emit("verify", {
            "run_id": agent_run.id, "step_id": verify_step.id,
            "success": verification.valid, "checks": verification.checks,
            "warnings": verification.warnings,
        })
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
            waypoint_ids = route.get("waypoint_location_ids") or []
            waypoint_query = f"&waypoints={','.join(waypoint_ids)}" if waypoint_ids else ""
            map_action = {
                "type": "multi_route" if waypoint_ids else "route",
                "url": f"/map?origin={route.get('origin_location_id', '')}&destination={route.get('destination_location_id', '')}{waypoint_query}",
                "campus_id": observation.campus_id,
            }
        elif locations:
            map_action = {
                "type": "focus_location",
                "url": f"/map?location={locations[0].get('id', '')}",
                "location_id": locations[0].get("id"),
                "campus_id": observation.campus_id,
            }
        actions = self._actions(tool_responses, map_action)
        if decision.intent == "learning_guidance" and answer:
            actions.append(AgentAction(
                id="save-learning-note", type="note", label="保存为学习便签",
                api_path="/notes", method="POST",
                payload={"title": "大师兄学习建议", "content": answer, "tags": ["学习计划"], "confirmed": True},
            ))
        if any(tool.tool_name == "search_campus_processes" and tool.success for tool in tool_responses):
            actions.append(AgentAction(
                id="open-process", type="process", label="打开办事流程", url="/processes",
            ))
        if any(tool.tool_name == "extract_tasks_from_notification" and tool.success for tool in tool_responses):
            actions.append(AgentAction(
                id="open-tasks", type="calendar", label="查看任务与日历", url="/tasks",
            ))
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
        waiting_for_confirmation = any(action.requires_confirmation for action in actions)
        waiting_for_input = any(tool.requires_user_action and not tool.success for tool in tool_responses)
        if waiting_for_confirmation:
            run_store.transition(
                agent_run,
                "waiting_for_confirmation",
                required_input=[{"type": "confirmation", "label": action.label, "action_id": action.id} for action in actions if action.requires_confirmation],
                summary="工具预览已完成，等待用户确认写入。",
            )
        elif waiting_for_input:
            run_store.transition(
                agent_run,
                "waiting_for_user_input",
                required_input=[{"type": "missing_input", "label": "请补充执行所需信息"}],
                summary="缺少完成目标所需的用户输入。",
            )
        elif verification.valid:
            run_store.transition(agent_run, "completed", summary="目标已完成并通过核验。")
        else:
            run_store.transition(agent_run, "failed", summary="执行结果未通过核验，未冒充成功。")
        self.db.commit()
        self.db.refresh(assistant)
        self.db.refresh(agent_run, attribute_names=["steps"])
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
            agent_run_id=agent_run.id,
            agent_status=agent_run.status,
            agent_steps=[public_step(step) for step in agent_run.steps],
            actions=actions,
        )
        await emit("final", response.model_dump(mode="json"))
        return response

    async def _navigation(
        self,
        user: User,
        message: str,
        conversation_id: str | None,
        campus_id: str | None,
        destination: Location,
        location_context: LocationContext | None,
        resume_navigation: bool,
        emit: Callable[[str, dict[str, Any]], Awaitable[None]],
        agent_run_id: str | None,
    ) -> AgentChatResponse:
        conversation = self.memory.conversation(user, conversation_id, campus_id, message)
        run_store = AgentRunStore(self.db)
        agent_run = run_store.create_or_resume(
            user,
            conversation,
            message,
            run_id=agent_run_id,
            intent="campus_navigation",
            completion_condition="获得当前位置后生成并核验到目的地的真实步行路线",
            context={
                "campus_id": destination.campus_id,
                "conversation_id": conversation.id,
                "destination_location_id": destination.id,
            },
        )
        await emit("run", {"id": agent_run.id, "status": agent_run.status, "goal": agent_run.goal})
        if not resume_navigation:
            self.db.add(Message(conversation_id=conversation.id, role="user", content=message, intent="campus_navigation"))
        resolve_step = run_store.start_step(
            agent_run,
            step_type="observe",
            tool_name="search_campus_locations",
            public_label=f"确认目的地：{destination.name}",
            input_summary={"destination_location_id": destination.id},
        )
        run_store.finish_step(resolve_step, True, f"已匹配 {destination.name}")
        await emit("tool_end", {
            "run_id": agent_run.id, "step_id": resolve_step.id,
            "tool": "search_campus_locations", "success": True,
            "summary": f"已匹配 {destination.name}",
        })
        await emit("stage", {"stage": "navigation", "label": "正在核对目的地和定位权限"})
        route: dict[str, Any] | None = None
        tool_status = "success"
        map_action: dict[str, Any]
        requires_confirmation = False
        if location_context is None:
            answer = f"我已经找到{destination.name}。需要你的当前位置才能计算真实步行路线。"
            map_action = {
                "type": "request_location",
                "destination_location_id": destination.id,
                "location_id": destination.id,
                "campus_id": destination.campus_id,
                "reason": "需要当前位置为你规划路线",
            }
            requires_confirmation = True
            safe_tool_data = {"destination_location_id": destination.id, "destination_name": destination.name}
        elif (
            destination.latitude is None
            or destination.longitude is None
            or destination.coordinate_accuracy != "exact"
            or destination.coordinate_verified_at is None
        ):
            answer = f"{destination.name}目前还没有经过核验的精确坐标，我不能编造路线。你可以先在地图中查看地点资料或选择其他起点。"
            map_action = {
                "type": "focus_location",
                "url": f"/map?location={destination.id}",
                "location_id": destination.id,
                "campus_id": destination.campus_id,
            }
            tool_status = "error"
            safe_tool_data = {"destination_location_id": destination.id, "coordinate_status": "unverified"}
        else:
            await emit("stage", {"stage": "route", "label": "正在计算真实步行路线"})
            run_store.transition(agent_run, "executing", required_input=[])
            route_step = run_store.start_step(
                agent_run,
                step_type="tool",
                tool_name="calculate_walking_route",
                public_label=f"计算到{destination.name}的真实步行路线",
                input_summary={"destination_location_id": destination.id},
            )
            await emit("tool_start", {
                "run_id": agent_run.id, "step_id": route_step.id,
                "tool": "calculate_walking_route", "label": route_step.public_label,
            })
            try:
                route = await MapService.configured().walking_route(
                    location_context.longitude,
                    location_context.latitude,
                    float(destination.longitude),
                    float(destination.latitude),
                )
            except MapServiceError as exc:
                answer = f"{exc.public_message}。我没有生成估算距离，你可以在地图中使用高德浏览器路线。"
                map_action = {
                    "type": "client_route",
                    "url": f"/map?destination={destination.id}&use_current=1&agent_run_id={agent_run.id}",
                    "destination_location_id": destination.id,
                    "location_id": destination.id,
                    "campus_id": destination.campus_id,
                }
                tool_status = "error"
                safe_tool_data = {"destination_location_id": destination.id, "route_status": "provider_unavailable"}
                run_store.finish_step(route_step, False, exc.public_message)
                await emit("tool_end", {"run_id": agent_run.id, "step_id": route_step.id, "tool": "calculate_walking_route", "success": False, "summary": exc.public_message})
            else:
                from app.api.map import _distance_meters

                off_campus = _distance_meters(
                    location_context.latitude,
                    location_context.longitude,
                    float(destination.latitude),
                    float(destination.longitude),
                ) > 5_000
                route.update(
                    {
                        "destination_location_id": destination.id,
                        "destination_name": destination.name,
                        "accuracy_status": "accurate" if location_context.accuracy <= 30 else "approximate",
                        "off_campus": off_campus,
                    }
                )
                minutes = max(1, round(int(route.get("duration_seconds") or 0) / 60))
                distance = int(route.get("distance_meters") or 0)
                campus_name = self.db.scalar(select(Campus.name).where(Campus.id == destination.campus_id)) or "目标校区"
                prefix = f"你现在似乎不在{campus_name}附近；我先按高德公共路线规划到目的地。" if off_campus else "路线已经算好。"
                answer = f"{prefix} 从你当前位置到{destination.name}约 {distance} 米，步行约 {minutes} 分钟。"
                map_action = {
                    "type": "route",
                    "url": f"/map?destination={destination.id}&use_current=1",
                    "destination_location_id": destination.id,
                    "location_id": destination.id,
                    "campus_id": destination.campus_id,
                }
                safe_tool_data = {
                    "destination_location_id": destination.id,
                    "destination_name": destination.name,
                    "distance_meters": distance,
                    "duration_seconds": int(route.get("duration_seconds") or 0),
                    "accuracy_status": route["accuracy_status"],
                    "off_campus": off_campus,
                }
                run_store.finish_step(route_step, True, f"{distance} 米，约 {minutes} 分钟")
                await emit("tool_end", {"run_id": agent_run.id, "step_id": route_step.id, "tool": "calculate_walking_route", "success": True, "summary": f"{distance} 米，约 {minutes} 分钟"})
        if location_context is None:
            wait_step = run_store.start_step(
                agent_run,
                step_type="request_input",
                public_label="等待你授权当前位置或选择手动起点",
                tool_name="request_location",
                input_summary={"destination_location_id": destination.id},
            )
            wait_step.status = "waiting"
            run_store.transition(
                agent_run,
                "waiting_for_location",
                required_input=[{
                    "type": "location",
                    "label": "使用当前位置",
                    "destination_location_id": destination.id,
                }],
                summary=f"已确认目的地 {destination.name}，等待位置后继续同一次执行。",
            )
        elif safe_tool_data.get("coordinate_status") == "unverified":
            run_store.transition(
                agent_run,
                "waiting_for_user_input",
                required_input=[{
                    "type": "destination_calibration",
                    "label": "该目的地精确入口仍待管理员核验",
                    "destination_location_id": destination.id,
                }],
                summary="目的地缺少可审计的精确坐标，未生成猜测路线。",
            )
        elif safe_tool_data.get("route_status") == "provider_unavailable":
            run_store.transition(
                agent_run,
                "waiting_for_user_input",
                required_input=[{
                    "type": "client_navigation",
                    "label": "在浏览器高德地图中继续真实路线规划",
                    "destination_location_id": destination.id,
                }],
                summary="后端路线服务不可用，等待浏览器高德地图完成真实路线。",
            )
        else:
            run_store.transition(agent_run, "verifying")
            verify_step = run_store.start_step(agent_run, step_type="verify", public_label="核对路线提供方与定位精度")
            run_store.finish_step(verify_step, route is not None, "真实路线已核验" if route else "路线提供方未返回可用路线")
            await emit("verify", {
                "run_id": agent_run.id, "step_id": verify_step.id,
                "success": route is not None,
                "checks": {"destination_verified": True, "route_available": route is not None},
            })
            run_store.transition(
                agent_run,
                "completed" if route else "failed",
                summary="真实步行路线已生成。" if route else "路线提供方未返回可核验路线，未冒充成功。",
            )
        tool_result = ToolResult(tool="walking_route", status=tool_status, title="当前位置步行路线", data=safe_tool_data)
        assistant = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            intent="campus_navigation",
            tool_results=[tool_result.model_dump(mode="json")],
            sources=[],
        )
        self.db.add(assistant)
        self.db.flush()
        self.db.add(ToolExecution(
            conversation_id=conversation.id,
            message_id=assistant.id,
            tool_name="calculate_walking_route",
            success=bool(route),
            summary=answer,
            verification={
                "agent_run_id": agent_run.id,
                "destination_location_id": destination.id,
                "coordinate_accuracy": destination.coordinate_accuracy,
                "location_accuracy_status": safe_tool_data.get("accuracy_status", "not_provided"),
                "final_status": agent_run.status,
            },
            error_code="" if route else str(safe_tool_data.get("coordinate_status") or safe_tool_data.get("route_status") or "location_required"),
        ))
        self.db.commit()
        self.db.refresh(assistant)
        self.db.refresh(agent_run, attribute_names=["steps"])
        actions: list[AgentAction] = []
        if map_action.get("type") == "request_location":
            actions.append(AgentAction(id="share-location", type="location", label="使用当前位置"))
        elif map_action.get("url"):
            actions.append(AgentAction(
                id="open-map", type="navigation",
                label="开始导航" if map_action.get("type") in {"route", "client_route"} else "在地图中查看",
                url=str(map_action["url"]),
            ))
        response = AgentChatResponse(
            conversation_id=conversation.id,
            message_id=assistant.id,
            intent="campus_navigation",
            plan=["resolve_destination", "request_location" if location_context is None else "calculate_walking_route"],
            tools_called=["search_campus_locations", "calculate_walking_route"] if location_context else ["search_campus_locations"],
            tool_success={"search_campus_locations": True, "calculate_walking_route": bool(route)},
            answer=answer,
            tool_results=[tool_result],
            locations=[{"id": destination.id, "name": destination.name, "campus_id": destination.campus_id}],
            route=route,
            map_action=map_action,
            requires_confirmation=requires_confirmation,
            degraded=False,
            error_id=None,
            data_status=destination.data_status,
            current_time=self.memory.observe(user, conversation).current_time,
            agent_run_id=agent_run.id,
            agent_status=agent_run.status,
            agent_steps=[public_step(step) for step in agent_run.steps],
            actions=actions,
        )
        await emit("final", response.model_dump(mode="json"))
        return response
