from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from app.core.dependencies import CurrentUser, DbSession
from app.models.entities import Location, Note, Reminder, Task, utcnow
from app.schemas.reminders import ReminderCreate, ReminderPreview, ReminderPreviewRequest, ReminderRead, ReminderUpdate
from app.services.time_service import now_china, parse_relative_datetime
from app.services.ownership import get_owned_reminder


router = APIRouter(prefix="/reminders", tags=["reminders"])


def _owned(db: DbSession, reminder_id: str, user_id: str) -> Reminder:
    return get_owned_reminder(db, reminder_id, user_id)


def _read(db: DbSession, row: Reminder) -> ReminderRead:
    location_id = None
    location_name = ""
    if row.task_id:
        task = db.scalar(select(Task).where(Task.id == row.task_id, Task.user_id == row.user_id))
        if task:
            location_id = task.location_id
            location_name = task.location
            if location_id:
                location = db.get(Location, location_id)
                location_name = location.name if location else location_name
    return ReminderRead.model_validate(row).model_copy(
        update={"location_id": location_id, "location_name": location_name}
    )


def _validate_links(db: DbSession, user_id: str, task_id: str | None, note_id: str | None) -> None:
    if task_id and not db.scalar(select(Task.id).where(Task.id == task_id, Task.user_id == user_id)):
        raise HTTPException(status_code=404, detail="关联任务不存在")
    if note_id and not db.scalar(select(Note.id).where(Note.id == note_id, Note.user_id == user_id)):
        raise HTTPException(status_code=404, detail="关联便签不存在")


@router.post("/preview", response_model=ReminderPreview)
def preview_reminder(payload: ReminderPreviewRequest, user: CurrentUser, db: DbSession) -> ReminderPreview:
    _validate_links(db, user.id, payload.task_id, payload.note_id)
    inference = parse_relative_datetime(payload.text)
    content = re.sub(r"^(?:请|帮我)?", "", payload.text.strip())
    content = re.sub(r"(?:今天|明天|明日|后天|大后天|下周[一二三四五六日天])[^，,。；;]*提醒我", "", content)
    content = re.sub(r"提醒我", "", content).strip(" ，,。；;") or payload.text.strip()
    title = payload.title.strip() or content[:60]
    return ReminderPreview(
        title=title,
        body=content,
        remind_at=inference.value,
        explanation=inference.explanation,
        requires_confirmation=True,
    )


@router.get("", response_model=list[ReminderRead])
def list_reminders(
    user: CurrentUser,
    db: DbSession,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ReminderRead]:
    query = select(Reminder).where(Reminder.user_id == user.id)
    if status_filter:
        query = query.where(Reminder.status == status_filter)
    return [_read(db, row) for row in db.scalars(query.order_by(Reminder.remind_at).limit(limit))]


@router.post("", response_model=ReminderRead, status_code=status.HTTP_201_CREATED)
def create_reminder(payload: ReminderCreate, user: CurrentUser, db: DbSession) -> ReminderRead:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="创建提醒前必须明确确认")
    _validate_links(db, user.id, payload.task_id, payload.note_id)
    remind_at = now_china(payload.remind_at)
    if remind_at <= now_china():
        raise HTTPException(status_code=422, detail="提醒时间必须晚于当前时间")
    row = Reminder(
        user_id=user.id,
        task_id=payload.task_id,
        note_id=payload.note_id,
        title=payload.title,
        body=payload.body,
        remind_at=remind_at,
        timezone=payload.timezone,
        repeat_rule=payload.repeat_rule,
        channels=payload.channels,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _read(db, row)


@router.post("/check", response_model=list[ReminderRead])
def check_due_reminders(user: CurrentUser, db: DbSession) -> list[ReminderRead]:
    rows = list(db.scalars(select(Reminder).where(
        Reminder.user_id == user.id,
        Reminder.status == "scheduled",
        Reminder.remind_at <= now_china(),
    ).order_by(Reminder.remind_at).limit(20)))
    if rows:
        stamp = utcnow()
        for row in rows:
            row.status = "triggered"
            row.triggered_at = stamp
        db.commit()
        for row in rows:
            db.refresh(row)
    return [_read(db, row) for row in rows]


@router.get("/{reminder_id}", response_model=ReminderRead)
def get_reminder(reminder_id: str, user: CurrentUser, db: DbSession) -> ReminderRead:
    return _read(db, _owned(db, reminder_id, user.id))


@router.patch("/{reminder_id}", response_model=ReminderRead)
def update_reminder(reminder_id: str, payload: ReminderUpdate, user: CurrentUser, db: DbSession) -> ReminderRead:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="修改提醒前必须明确确认")
    row = _owned(db, reminder_id, user.id)
    changes = payload.model_dump(exclude_unset=True, exclude={"confirmed"})
    if changes.get("remind_at"):
        changes["remind_at"] = now_china(changes["remind_at"])
    for key, value in changes.items():
        setattr(row, key, value)
    if row.status == "dismissed":
        row.dismissed_at = utcnow()
    db.commit()
    db.refresh(row)
    return _read(db, row)


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_reminder(reminder_id: str, user: CurrentUser, db: DbSession, confirmed: bool = Query(False)) -> Response:
    if not confirmed:
        raise HTTPException(status_code=422, detail="取消提醒前必须明确确认")
    row = _owned(db, reminder_id, user.id)
    row.status = "cancelled"
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
