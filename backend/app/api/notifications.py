from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from hashlib import sha256

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pypdf import PdfReader

from app.core.config import get_settings
from app.core.dependencies import CurrentUser, DbSession
from app.models.entities import Reminder, Task, TaskReminder, UploadedDocument
from app.schemas.agent import NotificationConfirmRequest, NotificationParseResponse
from app.schemas.tasks import TaskRead
from app.services.notification_service import NotificationService
from app.services.time_service import now_china


router = APIRouter(prefix="/notifications", tags=["notifications"])


def _extract_upload(filename: str, content_type: str, payload: bytes) -> str:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix == "txt" and content_type in {"text/plain", "application/octet-stream"}:
        try:
            return payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=422, detail="TXT 文件必须使用 UTF-8 编码") from exc
    if suffix == "pdf" and content_type in {"application/pdf", "application/octet-stream"}:
        try:
            return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(payload)).pages).strip()
        except Exception as exc:
            raise HTTPException(status_code=422, detail="PDF 文本提取失败，请改为粘贴文本") from exc
    if suffix in {"png", "jpg", "jpeg", "webp"}:
        raise HTTPException(status_code=415, detail="图片 OCR 尚未启用，请粘贴文字或上传 TXT/PDF")
    raise HTTPException(status_code=415, detail="仅支持 TXT 和 PDF 文件")


@router.post("/parse", response_model=NotificationParseResponse)
async def parse_notification(
    user: CurrentUser,
    db: DbSession,
    text: str = Form(default=""),
    source_url: str = Form(default=""),
    file: UploadFile | None = File(default=None),
) -> NotificationParseResponse:
    combined = text.strip()
    if file:
        payload = await file.read(get_settings().max_upload_bytes + 1)
        if len(payload) > get_settings().max_upload_bytes:
            raise HTTPException(status_code=413, detail="文件不得超过 5 MB")
        extracted = _extract_upload(file.filename or "", file.content_type or "application/octet-stream", payload)
        combined = "\n".join(filter(None, [combined, extracted]))
    if not combined:
        raise HTTPException(status_code=422, detail="请粘贴通知或上传 TXT/PDF")
    result = await NotificationService().extract(combined, source_url)
    if file:
        db.add(UploadedDocument(
            user_id=user.id,
            original_filename=(file.filename or "upload")[:255],
            content_type=(file.content_type or "application/octet-stream")[:120],
            size_bytes=len(payload),
            content_hash=sha256(payload).hexdigest(),
            extraction_status=result.extraction_mode,
        ))
        db.commit()
    return result


@router.post("/confirm", response_model=list[TaskRead], status_code=status.HTTP_201_CREATED)
def confirm_notification(payload: NotificationConfirmRequest, user: CurrentUser, db: DbSession) -> list[Task]:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="保存任务前必须明确确认")
    if any(item.is_expired for item in payload.action_items) and not payload.allow_expired:
        raise HTTPException(status_code=422, detail="通知已经过期，默认不保存；如仍需补交，请手动确认保存过期任务")
    tasks: list[Task] = []
    for item in payload.action_items:
        task = Task(
            user_id=user.id,
            title=item.title,
            deadline=item.deadline,
            location=item.location,
            description="\n".join([item.action, *item.notes]).strip(),
            materials=item.materials,
            submission_target=item.submission_target,
            submission_method=item.submission_method,
            file_naming=item.file_naming,
            conditions=item.conditions,
            evidence_requirements=item.evidence_requirements,
            is_expired=item.is_expired,
            source_title=item.source_title,
            source_text=item.source_text,
            source_url=item.source_url,
            needs_confirmation=item.needs_confirmation,
        )
        db.add(task)
        db.flush()
        db.add_all([TaskReminder(task_id=task.id, minutes_before=1440), TaskReminder(task_id=task.id, minutes_before=180)])
        if task.deadline:
            for minutes in (1440, 180):
                remind_at = task.deadline - timedelta(minutes=minutes)
                if now_china(remind_at) > now_china():
                    db.add(Reminder(
                        user_id=user.id,
                        task_id=task.id,
                        title=f"任务提醒：{task.title}",
                        body=task.description,
                        remind_at=now_china(remind_at),
                        timezone="Asia/Shanghai",
                        channels=["in_app"],
                    ))
        tasks.append(task)
    db.commit()
    for task in tasks:
        db.refresh(task)
    return tasks
