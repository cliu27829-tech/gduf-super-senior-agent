from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import or_, select

from app.core.dependencies import CurrentUser, DbSession
from app.models.entities import Conversation, Message, Note
from app.schemas.notes import NoteCreate, NotePreview, NotePreviewRequest, NoteRead, NoteUpdate


router = APIRouter(prefix="/notes", tags=["notes"])


def _owned(db: DbSession, note_id: str, user_id: str) -> Note:
    row = db.scalar(select(Note).where(Note.id == note_id, Note.user_id == user_id))
    if not row:
        raise HTTPException(status_code=404, detail="便签不存在")
    return row


def _validate_source(db: DbSession, user_id: str, source_message_id: str | None) -> None:
    if not source_message_id:
        return
    owned = db.scalar(
        select(Message.id).join(Conversation).where(Message.id == source_message_id, Conversation.user_id == user_id)
    )
    if not owned:
        raise HTTPException(status_code=404, detail="来源消息不存在")


@router.post("/preview", response_model=NotePreview)
def preview_note(payload: NotePreviewRequest, user: CurrentUser, db: DbSession) -> NotePreview:
    _validate_source(db, user.id, payload.source_message_id)
    content = re.sub(r"^(?:请)?(?:把)?(?:刚才的)?", "", payload.text.strip())
    content = re.sub(r"(?:记一下|记下来|保存为便签|保存到便签)[。！!]?$", "", content).strip() or payload.text.strip()
    first_line = next((line.strip() for line in content.splitlines() if line.strip()), "新便签")
    return NotePreview(
        title=first_line[:60],
        content=content,
        tags=[],
        source_message_id=payload.source_message_id,
    )


@router.get("", response_model=list[NoteRead])
def list_notes(
    user: CurrentUser,
    db: DbSession,
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[Note]:
    query = select(Note).where(Note.user_id == user.id)
    if q.strip():
        pattern = f"%{q.strip()}%"
        query = query.where(or_(Note.title.ilike(pattern), Note.content.ilike(pattern)))
    return list(db.scalars(query.order_by(Note.pinned.desc(), Note.updated_at.desc()).limit(limit)))


@router.post("", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def create_note(payload: NoteCreate, user: CurrentUser, db: DbSession) -> Note:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="保存便签前必须明确确认")
    _validate_source(db, user.id, payload.source_message_id)
    row = Note(user_id=user.id, **payload.model_dump(exclude={"confirmed"}))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{note_id}", response_model=NoteRead)
def update_note(note_id: str, payload: NoteUpdate, user: CurrentUser, db: DbSession) -> Note:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="修改便签前必须明确确认")
    row = _owned(db, note_id, user.id)
    for key, value in payload.model_dump(exclude_unset=True, exclude={"confirmed"}).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: str, user: CurrentUser, db: DbSession, confirmed: bool = Query(False)) -> Response:
    if not confirmed:
        raise HTTPException(status_code=422, detail="删除便签前必须明确确认")
    db.delete(_owned(db, note_id, user.id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
