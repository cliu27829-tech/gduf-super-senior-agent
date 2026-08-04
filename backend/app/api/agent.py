from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.core.dependencies import CurrentUser, DbSession
from app.core.llm_client import LLMClient, LLMClientError, get_llm_client
from app.models.entities import Campus, Conversation, Message
from app.schemas.agent import AgentChatRequest, AgentChatResponse, AgentStatusResponse
from app.services.agent_service import AgentService


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
        return await AgentService(db, llm).chat(user, payload.message, payload.conversation_id, campus_id)
    except LLMClientError as exc:
        db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"{exc.public_message} 错误编号：{exc.error_id}",
            headers={"X-Error-ID": exc.error_id},
        ) from exc


@router.get("/conversations")
def conversations(user: CurrentUser, db: DbSession) -> list[dict]:
    rows = list(db.scalars(select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc())))
    return [{"id": row.id, "title": row.title, "campus_id": row.campus_id, "created_at": row.created_at, "updated_at": row.updated_at} for row in rows]


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
def create_conversation(user: CurrentUser, db: DbSession) -> dict:
    row = Conversation(user_id=user.id, campus_id=user.campus_id, title="新对话")
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "title": row.title, "campus_id": row.campus_id, "created_at": row.created_at, "updated_at": row.updated_at}


@router.get("/conversations/{conversation_id}")
def conversation_detail(conversation_id: str, user: CurrentUser, db: DbSession) -> dict:
    row = db.scalar(select(Conversation).options(selectinload(Conversation.messages)).where(Conversation.id == conversation_id, Conversation.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="对话不存在")
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
    row = db.scalar(select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="对话不存在")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
