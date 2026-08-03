"""Persistent, user-isolated task lifecycle service."""

from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path
from typing import Any, Iterable
import uuid

from core.database import Database
from core.models import TaskItem
from core.time_service import now_china, parse_datetime_value
from services.notification_service import NotificationDraft


class TaskService:
    def __init__(self, db_path: str | Path | None = None):
        self.database = Database(db_path)

    @staticmethod
    def _row_to_task(row: dict[str, Any]) -> TaskItem:
        payload = dict(row)
        try:
            payload["materials"] = json.loads(payload.pop("materials_json", "[]"))
        except json.JSONDecodeError:
            payload["materials"] = []
        payload["needs_confirmation"] = bool(payload.get("needs_confirmation"))
        return TaskItem(**payload)

    def create_task(
        self,
        user_id: str,
        title: str,
        deadline: str | None = None,
        location: str = "",
        materials: Iterable[str] = (),
        submission_method: str = "",
        source_text: str = "",
        source_url: str = "",
        needs_confirmation: bool = False,
        confirmed: bool = False,
    ) -> TaskItem:
        if not user_id.strip():
            raise ValueError("user_id 不能为空")
        if not title.strip():
            raise ValueError("任务标题不能为空")
        if not confirmed:
            raise ValueError("创建任务前必须由用户确认")
        if needs_confirmation and not confirmed:
            raise ValueError("推断日期存在风险，必须确认")
        timestamp = now_china().isoformat()
        task = TaskItem(
            id=str(uuid.uuid4()),
            user_id=user_id,
            title=title.strip(),
            deadline=deadline,
            location=location.strip(),
            materials=list(materials),
            submission_method=submission_method.strip(),
            source_text=source_text,
            source_url=source_url,
            status="pending",
            needs_confirmation=needs_confirmation,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.database.execute(
            """
            INSERT INTO tasks(
                id,user_id,title,deadline,location,materials_json,submission_method,
                source_text,source_url,status,needs_confirmation,created_at,updated_at,completed_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                task.id,
                task.user_id,
                task.title,
                task.deadline,
                task.location,
                json.dumps(task.materials, ensure_ascii=False),
                task.submission_method,
                task.source_text,
                task.source_url,
                task.status,
                int(task.needs_confirmation),
                task.created_at,
                task.updated_at,
                task.completed_at,
            ),
        )
        return task

    def create_from_drafts(
        self,
        user_id: str,
        drafts: Iterable[NotificationDraft],
        confirmed: bool = False,
    ) -> list[TaskItem]:
        if not confirmed:
            raise ValueError("保存通知任务前必须确认")
        return [
            self.create_task(
                user_id=user_id,
                title=draft.title,
                deadline=draft.deadline,
                location=draft.location,
                materials=draft.materials,
                submission_method=draft.submission_method,
                source_text=draft.source_text,
                source_url=draft.source_url,
                needs_confirmation=draft.needs_confirmation,
                confirmed=True,
            )
            for draft in drafts
        ]

    def get_task(self, task_id: str, user_id: str) -> TaskItem | None:
        row = self.database.query_one(
            "SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
        )
        return self._row_to_task(row) if row else None

    def list_tasks(
        self,
        user_id: str,
        status: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> list[TaskItem]:
        clauses = ["user_id = ?"]
        parameters: list[Any] = [user_id]
        if status:
            clauses.append("status = ?")
            parameters.append(status)
        if start:
            clauses.append("deadline >= ?")
            parameters.append(start)
        if end:
            clauses.append("deadline <= ?")
            parameters.append(end)
        rows = self.database.query(
            "SELECT * FROM tasks WHERE "
            + " AND ".join(clauses)
            + " ORDER BY CASE WHEN deadline IS NULL THEN 1 ELSE 0 END, deadline, created_at",
            tuple(parameters),
        )
        return [self._row_to_task(row) for row in rows]

    def list_week_tasks(self, user_id: str, reference_time=None, incomplete_only: bool = True) -> list[TaskItem]:
        reference = now_china(reference_time)
        monday = (reference - timedelta(days=reference.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        sunday_end = monday + timedelta(days=7) - timedelta(microseconds=1)
        return self.list_tasks(
            user_id,
            status="pending" if incomplete_only else None,
            start=monday.isoformat(),
            end=sunday_end.isoformat(),
        )

    def complete_task(self, task_id: str, user_id: str) -> TaskItem:
        task = self.get_task(task_id, user_id)
        if not task:
            raise ValueError("任务不存在或不属于当前用户")
        timestamp = now_china().isoformat()
        self.database.execute(
            "UPDATE tasks SET status='completed', completed_at=?, updated_at=? "
            "WHERE id=? AND user_id=?",
            (timestamp, timestamp, task_id, user_id),
        )
        return self.get_task(task_id, user_id)

    def reopen_task(self, task_id: str, user_id: str) -> TaskItem:
        if not self.get_task(task_id, user_id):
            raise ValueError("任务不存在或不属于当前用户")
        timestamp = now_china().isoformat()
        self.database.execute(
            "UPDATE tasks SET status='pending', completed_at=NULL, updated_at=? "
            "WHERE id=? AND user_id=?",
            (timestamp, task_id, user_id),
        )
        return self.get_task(task_id, user_id)

    def overdue_tasks(self, user_id: str, reference_time=None) -> list[TaskItem]:
        reference = now_china(reference_time)
        return [
            task
            for task in self.list_tasks(user_id, status="pending")
            if task.deadline
            and (parse_datetime_value(task.deadline) or reference) < reference
        ]
