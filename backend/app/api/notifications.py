from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pypdf import PdfReader

from app.core.config import get_settings
from app.core.dependencies import CurrentUser, DbSession
from app.models.entities import Task, TaskReminder
from app.schemas.agent import NotificationConfirmRequest, NotificationParseResponse
from app.schemas.tasks import TaskRead
from app.services.notification_service import NotificationService


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
    text: str = Form(default=""),
    source_url: str = Form(default=""),
    file: UploadFile | None = File(default=None),
) -> NotificationParseResponse:
    del user
    combined = text.strip()
    if file:
        payload = await file.read(get_settings().max_upload_bytes + 1)
        if len(payload) > get_settings().max_upload_bytes:
            raise HTTPException(status_code=413, detail="文件不得超过 5 MB")
        extracted = _extract_upload(file.filename or "", file.content_type or "application/octet-stream", payload)
        combined = "\n".join(filter(None, [combined, extracted]))
    if not combined:
        raise HTTPException(status_code=422, detail="请粘贴通知或上传 TXT/PDF")
    drafts, mode, warning = NotificationService().extract(combined, source_url)
    return NotificationParseResponse(drafts=drafts, extraction_mode=mode, warning=warning)


@router.post("/confirm", response_model=list[TaskRead], status_code=status.HTTP_201_CREATED)
def confirm_notification(payload: NotificationConfirmRequest, user: CurrentUser, db: DbSession) -> list[Task]:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="保存任务前必须明确确认")
    tasks: list[Task] = []
    for draft in payload.drafts:
        task = Task(
            user_id=user.id,
            title=draft.title,
            deadline=draft.deadline,
            location=draft.location,
            description=draft.notes,
            materials=draft.materials,
            submission_target=draft.submission_target,
            submission_method=draft.submission_method,
            file_naming=draft.file_naming,
            source_text=draft.source_text,
            source_url=draft.source_url,
            needs_confirmation=draft.needs_confirmation,
        )
        db.add(task)
        db.flush()
        db.add_all([TaskReminder(task_id=task.id, minutes_before=1440), TaskReminder(task_id=task.id, minutes_before=180)])
        tasks.append(task)
    db.commit()
    for task in tasks:
        db.refresh(task)
    return tasks
