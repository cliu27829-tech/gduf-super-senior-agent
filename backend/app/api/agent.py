from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.core.dependencies import CurrentUser, DbSession
from app.core.llm_client import LLMClient, LLMClientError, get_llm_client
from app.agents.run_store import AgentRunStore, public_run
from app.models.entities import AgentRun, Campus, Conversation, Message
from app.schemas.agent import AgentChatRequest, AgentChatResponse, AgentStatusResponse
from app.services.agent_service import AgentService
from app.services.ownership import get_owned_conversation


router = APIRouter(prefix="/agent", tags=["agent"])
LLMDependency = Annotated[LLMClient, Depends(get_llm_client)]


@router.get("/status", response_model=AgentStatusResponse)
def agent_status(db: DbSession, llm: LLMDependency) -> AgentStatusResponse:
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="数据库暂时不可用") from exc
    return AgentStatusResponse(
        backend="ok",
        llm_configured=llm.configured,
        model=llm.model,
        database="ok",
    )


@router.post("/chat", response_model=AgentChatResponse)
async def chat(payload: AgentChatRequest, user: CurrentUser, db: DbSession, llm: LLMDependency) -> AgentChatResponse:
    campus_id = payload.campus_id
    if payload.campus:
        campus = db.scalar(
            select(Campus).where(
                Campus.is_active.is_(True),
                (Campus.slug == payload.campus) | (Campus.name == payload.campus),
            )
        )
        if not campus:
            raise HTTPException(status_code=422, detail="校区不存在")
        campus_id = campus.id
    elif campus_id and not db.scalar(select(Campus.id).where(Campus.id == campus_id, Campus.is_active.is_(True))):
        raise HTTPException(status_code=422, detail="校区不存在")
    try:
        return await AgentService(db, llm).chat(
            user,
            payload.message,
            payload.conversation_id,
            campus_id,
            location_context=payload.location_context,
            resume_navigation=payload.resume_navigation,
            agent_run_id=payload.agent_run_id,
        )
    except LLMClientError as exc:
        db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"{exc.public_message} 错误编号：{exc.error_id}",
            headers={"X-Error-ID": exc.error_id},
        ) from exc


def _resolve_campus(payload: AgentChatRequest, db: DbSession) -> str | None:
    campus_id = payload.campus_id
    if payload.campus:
        campus = db.scalar(select(Campus).where(
            Campus.is_active.is_(True), (Campus.slug == payload.campus) | (Campus.name == payload.campus)
        ))
        if not campus:
            raise HTTPException(status_code=422, detail="校区不存在")
        campus_id = campus.id
    elif campus_id and not db.scalar(select(Campus.id).where(Campus.id == campus_id, Campus.is_active.is_(True))):
        raise HTTPException(status_code=422, detail="校区不存在")
    return campus_id


@router.post("/chat/stream")
async def chat_stream(
    payload: AgentChatRequest,
    user: CurrentUser,
    db: DbSession,
    llm: LLMDependency,
) -> StreamingResponse:
    campus_id = _resolve_campus(payload, db)

    async def event_stream():
        queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

        async def emit(event: str, data: dict[str, Any]) -> None:
            await queue.put((event, data))

        async def work() -> None:
            try:
                await AgentService(db, llm).chat_stream(
                    user,
                    payload.message,
                    payload.conversation_id,
                    campus_id,
                    emit,
                    location_context=payload.location_context,
                    resume_navigation=payload.resume_navigation,
                    agent_run_id=payload.agent_run_id,
                )
            except LLMClientError as exc:
                db.rollback()
                await emit("error", {"message": exc.public_message, "error_id": exc.error_id, "status": exc.status_code})
            except Exception:
                db.rollback()
                await emit("error", {"message": "对话处理失败，请稍后重试", "status": 500})
            finally:
                await queue.put(None)

        worker = asyncio.create_task(work())
        try:
            while (item := await queue.get()) is not None:
                event, data = item
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
        finally:
            if not worker.done():
                worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations")
def conversations(user: CurrentUser, db: DbSession) -> list[dict]:
    rows = list(db.scalars(select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc())))
    return [{"id": row.id, "title": row.title, "campus_id": row.campus_id, "created_at": row.created_at, "updated_at": row.updated_at} for row in rows]


@router.get("/runs")
def agent_runs(user: CurrentUser, db: DbSession, limit: int = 20) -> list[dict]:
    rows = list(db.scalars(
        select(AgentRun)
        .where(AgentRun.user_id == user.id)
        .order_by(AgentRun.updated_at.desc())
        .limit(min(max(limit, 1), 100))
    ))
    return [public_run(row, include_steps=False) for row in rows]


@router.get("/runs/{run_id}")
def agent_run_detail(run_id: str, user: CurrentUser, db: DbSession) -> dict:
    row = db.scalar(
        select(AgentRun)
        .options(selectinload(AgentRun.steps))
        .where(AgentRun.id == run_id, AgentRun.user_id == user.id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Agent 执行不存在")
    return public_run(row)


@router.post("/runs/{run_id}/confirm")
def confirm_agent_action(run_id: str, payload: dict, user: CurrentUser, db: DbSession) -> dict:
    row = db.scalar(
        select(AgentRun)
        .options(selectinload(AgentRun.steps))
        .where(AgentRun.id == run_id, AgentRun.user_id == user.id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Agent 执行不存在")
    if row.status not in {"waiting_for_confirmation", "waiting_for_user_input"}:
        raise HTTPException(status_code=409, detail="该 Agent 执行当前不等待用户动作")
    action_id = str(payload.get("action_id") or "")[:100]
    if not action_id:
        raise HTTPException(status_code=422, detail="缺少 action_id")
    required_input = row.required_input if isinstance(row.required_input, list) else []
    if row.status == "waiting_for_confirmation":
        allowed_actions = {
            str(item.get("action_id"))
            for item in required_input
            if isinstance(item, dict) and item.get("action_id")
        }
        if action_id not in allowed_actions:
            raise HTTPException(status_code=409, detail="该操作不在本次 Agent 执行的待确认列表中")
    if row.status == "waiting_for_user_input":
        waiting_for_client_route = any(
            isinstance(item, dict) and item.get("type") == "client_navigation"
            for item in required_input
        )
        if not waiting_for_client_route or action_id != "client-route-completed":
            raise HTTPException(status_code=409, detail="该 Agent 执行尚未满足完成条件")
    store = AgentRunStore(db)
    step = store.start_step(
        row,
        step_type="user_action",
        tool_name=action_id,
        public_label="用户已确认并完成写入操作",
    )
    store.finish_step(step, True, action_id)
    store.transition(row, "completed", required_input=[], summary="用户已确认，目标闭环完成。")
    db.commit()
    db.refresh(row, attribute_names=["steps"])
    return public_run(row)


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
def create_conversation(user: CurrentUser, db: DbSession) -> dict:
    row = Conversation(user_id=user.id, campus_id=user.campus_id, title="新对话")
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "title": row.title, "campus_id": row.campus_id, "created_at": row.created_at, "updated_at": row.updated_at}


@router.get("/conversations/{conversation_id}")
def conversation_detail(conversation_id: str, user: CurrentUser, db: DbSession) -> dict:
    row = get_owned_conversation(db, conversation_id, user.id)
    return {
        "id": row.id,
        "title": row.title,
        "messages": [
            {
                "id": item.id,
                "role": item.role,
                "content": item.content,
                "intent": item.intent,
                "tool_results": item.tool_results,
                "sources": item.sources,
                "created_at": item.created_at,
            }
            for item in sorted(row.messages, key=lambda value: value.created_at)
        ],
    }


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, user: CurrentUser, db: DbSession) -> Response:
    row = get_owned_conversation(db, conversation_id, user.id)
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
