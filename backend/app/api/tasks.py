from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.core.dependencies import CurrentUser, DbSession
from app.models.entities import Task, TaskReminder, utcnow
from app.schemas.tasks import BulkTaskAction, TaskCreate, TaskRead, TaskUpdate
from app.services.ics_service import generate_ics
from app.services.time_service import now_china


router = APIRouter(prefix="/tasks", tags=["tasks"])


def _owned(db: DbSession, task_id: str, user_id: str) -> Task:
    task = db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/export/ics")
def export_ics(
    user: CurrentUser,
    db: DbSession,
    task_ids: list[str] | None = Query(default=None),
    reminder_hours: list[int] = Query(default=[24, 3]),
) -> Response:
    query = select(Task).where(Task.user_id == user.id)
    if task_ids:
        query = query.where(Task.id.in_(task_ids))
    tasks = list(db.scalars(query))
    minutes = [max(1, min(hour, 24 * 30)) * 60 for hour in reminder_hours]
    payload = generate_ics(tasks, minutes)
    filename = f"gduf-tasks-{uuid4().hex}.ics"
    return Response(
        payload,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("", response_model=list[TaskRead])
def list_tasks(
    user: CurrentUser,
    db: DbSession,
    status_filter: str | None = Query(default=None, alias="status"),
    view: str = "all",
    course: str | None = None,
    task_type: str | None = None,
) -> list[Task]:
    query = select(Task).where(Task.user_id == user.id)
    if status_filter:
        query = query.where(Task.status == status_filter)
    if course:
        query = query.where(Task.course == course)
    if task_type:
        query = query.where(Task.task_type == task_type)
    now = now_china()
    if view == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        query = query.where(Task.deadline >= start, Task.deadline < start + timedelta(days=1))
    elif view == "week":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        query = query.where(Task.deadline >= start, Task.deadline < start + timedelta(days=7))
    elif view == "upcoming":
        query = query.where(Task.deadline >= now, Task.deadline <= now + timedelta(days=7), Task.status == "pending")
    elif view == "overdue":
        query = query.where(Task.deadline < now, Task.status == "pending")
    return list(db.scalars(query.order_by(Task.deadline.is_(None), Task.deadline, Task.created_at)))


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, user: CurrentUser, db: DbSession) -> Task:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="创建任务前必须明确确认")
    data = payload.model_dump(exclude={"confirmed", "reminder_minutes"})
    task = Task(user_id=user.id, **data)
    db.add(task)
    db.flush()
    for minutes in sorted(set(payload.reminder_minutes)):
        if minutes > 0:
            db.add(TaskReminder(task_id=task.id, minutes_before=minutes))
    db.commit()
    db.refresh(task)
    return task


@router.post("/bulk", status_code=status.HTTP_204_NO_CONTENT)
def bulk_action(payload: BulkTaskAction, user: CurrentUser, db: DbSession) -> Response:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="批量操作前必须明确确认")
    tasks = list(db.scalars(select(Task).where(Task.user_id == user.id, Task.id.in_(payload.task_ids))))
    if len(tasks) != len(set(payload.task_ids)):
        raise HTTPException(status_code=404, detail="部分任务不存在")
    for task in tasks:
        if payload.action == "delete":
            db.delete(task)
        elif payload.action == "complete":
            task.status = "completed"
            task.completed_at = utcnow()
        else:
            task.status = "pending"
            task.completed_at = None
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: str, user: CurrentUser, db: DbSession) -> Task:
    return _owned(db, task_id, user.id)


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(task_id: str, payload: TaskUpdate, user: CurrentUser, db: DbSession) -> Task:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="修改任务前必须明确确认")
    task = _owned(db, task_id, user.id)
    for key, value in payload.model_dump(exclude_unset=True, exclude={"confirmed"}).items():
        setattr(task, key, value)
    if task.status == "completed" and not task.completed_at:
        task.completed_at = utcnow()
    elif task.status == "pending":
        task.completed_at = None
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, user: CurrentUser, db: DbSession, confirmed: bool = Query(default=False)) -> Response:
    if not confirmed:
        raise HTTPException(status_code=422, detail="删除任务前必须明确确认")
    db.delete(_owned(db, task_id, user.id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{task_id}/complete", response_model=TaskRead)
def complete_task(task_id: str, user: CurrentUser, db: DbSession, confirmed: bool = Query(default=False)) -> Task:
    if not confirmed:
        raise HTTPException(status_code=422, detail="完成任务前必须明确确认")
    task = _owned(db, task_id, user.id)
    task.status = "completed"
    task.completed_at = utcnow()
    db.commit()
    db.refresh(task)
    return task


@router.post("/{task_id}/reopen", response_model=TaskRead)
def reopen_task(task_id: str, user: CurrentUser, db: DbSession, confirmed: bool = Query(default=False)) -> Task:
    if not confirmed:
        raise HTTPException(status_code=422, detail="重开任务前必须明确确认")
    task = _owned(db, task_id, user.id)
    task.status = "pending"
    task.completed_at = None
    db.commit()
    db.refresh(task)
    return task
