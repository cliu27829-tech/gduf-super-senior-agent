from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.contracts import Observation
from app.agents.persona import preferred_address
from app.core.config import get_settings
from app.models.entities import Campus, Conversation, Message, Task, User
from app.services.time_service import now_china
from app.services.ownership import get_owned_conversation


class Memory:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def conversation(self, user: User, conversation_id: str | None, campus_id: str | None, title: str) -> Conversation:
        row = None
        if conversation_id:
            row = get_owned_conversation(self.db, conversation_id, user.id)
        if not row:
            row = Conversation(user_id=user.id, campus_id=campus_id or user.campus_id, title=title[:60])
            self.db.add(row)
            self.db.flush()
        elif campus_id:
            row.campus_id = campus_id
        return row

    def history(self, conversation_id: str) -> list[dict[str, str]]:
        rows = list(self.db.scalars(
            select(Message).where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(self.settings.llm_history_messages)
        ))
        return [
            {"role": row.role, "content": row.content}
            for row in reversed(rows)
            if row.role in {"user", "assistant"}
        ]

    def observe(self, user: User, conversation: Conversation) -> Observation:
        campus_id = conversation.campus_id or user.campus_id
        campus_name = self.db.scalar(select(Campus.name).where(Campus.id == campus_id)) or "未指定"
        tasks = list(self.db.scalars(
            select(Task).where(Task.user_id == user.id, Task.status == "pending")
            .order_by(Task.deadline.is_(None), Task.deadline).limit(20)
        ))
        return Observation(
            user_id=user.id,
            campus_id=campus_id,
            campus_name=campus_name,
            current_time=now_china(),
            history=self.history(conversation.id),
            pending_tasks=[
                {"id": task.id, "title": task.title, "deadline": task.deadline, "status": task.status}
                for task in tasks
            ],
            preferred_address=preferred_address(user),
            preferred_location_id=user.preferred_location_id,
        )
