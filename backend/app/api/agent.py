from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.dependencies import CurrentUser, DbSession
from app.models.entities import Campus, Conversation, Message
from app.schemas.agent import AgentChatRequest, AgentChatResponse
from app.services.agent_service import AgentService


router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/chat", response_model=AgentChatResponse)
def chat(payload: AgentChatRequest, user: CurrentUser, db: DbSession) -> AgentChatResponse:
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
    return AgentService(db).chat(user, payload.message, payload.conversation_id, campus_id)


@router.get("/conversations")
def conversations(user: CurrentUser, db: DbSession) -> list[dict]:
    rows = list(db.scalars(select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc())))
    return [{"id": row.id, "title": row.title, "campus_id": row.campus_id, "created_at": row.created_at, "updated_at": row.updated_at} for row in rows]


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
