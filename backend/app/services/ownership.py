from __future__ import annotations

from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Conversation, KnowledgeDocument, Note, Reminder, Task


OwnedModel = TypeVar("OwnedModel", Task, Conversation, Note, Reminder, KnowledgeDocument)


def get_owned(db: Session, model: type[OwnedModel], resource_id: str, user_id: str, owner_field: str = "user_id") -> OwnedModel:
    owner_column = getattr(model, owner_field)
    row = db.scalar(select(model).where(model.id == resource_id, owner_column == user_id))
    if not row:
        raise HTTPException(status_code=404, detail="资源不存在")
    return row


def get_owned_task(db: Session, task_id: str, user_id: str) -> Task:
    return get_owned(db, Task, task_id, user_id)


def get_owned_conversation(db: Session, conversation_id: str, user_id: str) -> Conversation:
    return get_owned(db, Conversation, conversation_id, user_id)


def get_owned_note(db: Session, note_id: str, user_id: str) -> Note:
    return get_owned(db, Note, note_id, user_id)


def get_owned_reminder(db: Session, reminder_id: str, user_id: str) -> Reminder:
    return get_owned(db, Reminder, reminder_id, user_id)


def get_owned_document(db: Session, document_id: str, user_id: str) -> KnowledgeDocument:
    return get_owned(db, KnowledgeDocument, document_id, user_id, "owner_user_id")
