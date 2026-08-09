from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import or_, select

from app.core.config import get_settings
from app.core.dependencies import AdminUser, CurrentUser, DbSession
from app.models.entities import AdminAuditLog, Campus, KnowledgeDocument, KnowledgeImportJob, VerificationRecord
from app.schemas.knowledge import (
    ImportResult,
    KnowledgeSearchResult,
    KnowledgeSourceDetail,
    KnowledgeSourceRead,
    ReindexResult,
    ReviewRequest,
    TextImportRequest,
    UrlImportRequest,
)
from app.services.knowledge_service import (
    KnowledgeImportError,
    create_import_job,
    extract_document,
    fetch_article,
    finish_import_job,
    import_document,
    reindex_documents,
    search_knowledge,
)


router = APIRouter(prefix="/knowledge", tags=["knowledge"])
settings = get_settings()


def _validate_campus(db: DbSession, campus_id: str | None) -> None:
    if campus_id and not db.get(Campus, campus_id):
        raise HTTPException(status_code=422, detail="校区不存在")


def _visible_source(db: DbSession, user: CurrentUser, source_id: str) -> KnowledgeDocument:
    access = or_(
        KnowledgeDocument.visibility == "public",
        KnowledgeDocument.owner_user_id == user.id,
    )
    if user.role == "admin":
        access = or_(access, KnowledgeDocument.review_status == "pending")
    item = db.scalar(select(KnowledgeDocument).where(
        KnowledgeDocument.id == source_id,
        KnowledgeDocument.is_active.is_(True),
        access,
    ))
    if not item:
        raise HTTPException(status_code=404, detail="知识来源不存在")
    return item


@router.get("/sources", response_model=list[KnowledgeSourceRead])
def list_sources(user: CurrentUser, db: DbSession) -> list[KnowledgeDocument]:
    access = or_(KnowledgeDocument.visibility == "public", KnowledgeDocument.owner_user_id == user.id)
    if user.role == "admin":
        access = or_(access, KnowledgeDocument.review_status == "pending")
    query = select(KnowledgeDocument).where(KnowledgeDocument.is_active.is_(True), access)
    return list(db.scalars(query.order_by(KnowledgeDocument.created_at.desc()).limit(500)))


@router.get("/sources/{source_id}", response_model=KnowledgeSourceDetail)
def get_source(source_id: str, user: CurrentUser, db: DbSession) -> KnowledgeDocument:
    return _visible_source(db, user, source_id)


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(
    source_id: str,
    user: CurrentUser,
    db: DbSession,
    confirmed: bool = Query(default=False),
) -> Response:
    if not confirmed:
        raise HTTPException(status_code=422, detail="删除知识来源前必须明确确认")
    item = _visible_source(db, user, source_id)
    if item.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="知识来源不存在")
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sources/{source_id}/submit-review", response_model=KnowledgeSourceRead)
def submit_source_for_review(
    source_id: str,
    user: CurrentUser,
    db: DbSession,
    confirmed: bool = Query(default=False),
) -> KnowledgeDocument:
    if not confirmed:
        raise HTTPException(status_code=422, detail="提交共享审核前必须明确确认")
    item = db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == source_id,
            KnowledgeDocument.owner_user_id == user.id,
            KnowledgeDocument.is_active.is_(True),
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="知识来源不存在")
    item.review_status = "pending"
    db.commit()
    db.refresh(item)
    return item


@router.get("/search", response_model=list[KnowledgeSearchResult])
def search(
    user: CurrentUser,
    db: DbSession,
    q: str = Query(min_length=1, max_length=200),
    campus_id: str | None = None,
    limit: int = Query(default=8, ge=1, le=30),
) -> list[dict]:
    return search_knowledge(db, user_id=user.id, query=q, campus_id=campus_id, limit=limit)


@router.post("/import/text", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def import_text(payload: TextImportRequest, user: CurrentUser, db: DbSession) -> ImportResult:
    _validate_campus(db, payload.campus_id)
    job = create_import_job(db, user_id=user.id, source_label="pasted-text", total_files=1)
    try:
        outcome = import_document(
            db,
            user_id=user.id,
            title=payload.title,
            content=payload.content,
            source_type="text",
            campus_id=payload.campus_id,
            publisher=payload.publisher,
        )
    except KnowledgeImportError as exc:
        job.failed_files = 1
        finish_import_job(job, errors=[str(exc)])
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    job.duplicate_files = int(outcome.duplicate)
    job.imported_files = int(not outcome.duplicate)
    finish_import_job(job, errors=[])
    db.commit()
    return ImportResult(
        job_id=job.id,
        imported=job.imported_files,
        duplicates=job.duplicate_files,
        failed=0,
        document_ids=[outcome.document.id] if outcome.document else [],
    )


@router.post("/import/url", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def import_url(payload: UrlImportRequest, user: CurrentUser, db: DbSession) -> ImportResult:
    _validate_campus(db, payload.campus_id)
    safe_url = str(payload.url)
    job = create_import_job(db, user_id=user.id, source_label="article-url", total_files=1)
    try:
        title, content = fetch_article(safe_url, max_bytes=settings.max_upload_bytes)
        outcome = import_document(
            db,
            user_id=user.id,
            title=title,
            content=content,
            source_type="url",
            campus_id=payload.campus_id,
            publisher=payload.publisher,
            url=safe_url,
        )
    except (KnowledgeImportError, httpx.HTTPError) as exc:
        job.failed_files = 1
        finish_import_job(job, errors=[str(exc)])
        db.commit()
        raise HTTPException(status_code=422, detail=f"文章导入失败：{exc}") from exc
    job.duplicate_files = int(outcome.duplicate)
    job.imported_files = int(not outcome.duplicate)
    finish_import_job(job, errors=[])
    db.commit()
    return ImportResult(
        job_id=job.id,
        imported=job.imported_files,
        duplicates=job.duplicate_files,
        failed=0,
        document_ids=[outcome.document.id] if outcome.document else [],
    )


@router.post("/import/files", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def import_files(
    user: CurrentUser,
    db: DbSession,
    files: list[UploadFile] = File(...),
    campus_id: str | None = Form(default=None),
) -> ImportResult:
    _validate_campus(db, campus_id)
    if not files or len(files) > 100:
        raise HTTPException(status_code=422, detail="每次请选择 1 到 100 个文件")
    job = create_import_job(db, user_id=user.id, source_label="file-upload", total_files=len(files))
    errors: list[str] = []
    document_ids: list[str] = []
    for upload in files:
        safe_name = Path(upload.filename or "unnamed").name
        try:
            data = upload.file.read(settings.max_upload_bytes + 1)
            if len(data) > settings.max_upload_bytes:
                raise KnowledgeImportError("文件超过大小限制")
            content = extract_document(safe_name, data)
            outcome = import_document(
                db,
                user_id=user.id,
                title=Path(safe_name).stem,
                content=content,
                source_type="file",
                original_filename=safe_name,
                campus_id=campus_id,
            )
            job.duplicate_files += int(outcome.duplicate)
            job.imported_files += int(not outcome.duplicate)
            if outcome.document:
                document_ids.append(outcome.document.id)
        except KnowledgeImportError as exc:
            job.failed_files += 1
            errors.append(f"{safe_name}: {exc}")
    finish_import_job(job, errors=errors)
    db.commit()
    return ImportResult(
        job_id=job.id,
        imported=job.imported_files,
        duplicates=job.duplicate_files,
        failed=job.failed_files,
        document_ids=document_ids,
        errors=errors,
    )


@router.post("/reindex", response_model=ReindexResult)
def reindex(user: CurrentUser, db: DbSession) -> ReindexResult:
    count = reindex_documents(db, user_id=user.id, include_public=user.role == "admin")
    db.commit()
    return ReindexResult(indexed_documents=count)


@router.get("/jobs")
def list_jobs(user: CurrentUser, db: DbSession) -> list[dict]:
    rows = list(db.scalars(select(KnowledgeImportJob).where(
        KnowledgeImportJob.user_id == user.id
    ).order_by(KnowledgeImportJob.created_at.desc()).limit(50)))
    return [{
        "id": row.id,
        "status": row.status,
        "source_label": row.source_label,
        "total_files": row.total_files,
        "imported_files": row.imported_files,
        "duplicate_files": row.duplicate_files,
        "failed_files": row.failed_files,
        "error_summary": row.error_summary,
        "created_at": row.created_at,
    } for row in rows]


@router.patch("/admin/sources/{source_id}/review", response_model=KnowledgeSourceRead)
def review_source(
    source_id: str,
    payload: ReviewRequest,
    admin: AdminUser,
    db: DbSession,
) -> KnowledgeDocument:
    item = db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == source_id,
            KnowledgeDocument.is_active.is_(True),
            KnowledgeDocument.review_status == "pending",
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="待审核知识来源不存在")
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="管理员审核正式数据前必须二次确认")
    if payload.status == "approved" and not payload.evidence.strip():
        raise HTTPException(status_code=422, detail="审核为共享资料时必须填写核验证据")
    item.review_status = payload.status
    if payload.status == "approved":
        item.visibility = "public"
        item.data_status = "admin_approved"
    elif payload.status == "rejected":
        item.visibility = "private"
        item.data_status = "rejected"
    db.add(VerificationRecord(
        entity_type="knowledge_document",
        entity_id=item.id,
        status=payload.status,
        method=payload.verification_method,
        evidence=payload.evidence.strip(),
        note=f"核验字段：{', '.join(payload.verified_fields)}\n{payload.note.strip()}".strip(),
        verified_by=admin.id,
    ))
    db.add(AdminAuditLog(
        admin_id=admin.id,
        action="knowledge.review",
        entity_type="knowledge_document",
        entity_id=item.id,
        summary=f"review_status={payload.status}; fields={','.join(payload.verified_fields)}"[:2000],
    ))
    db.commit()
    db.refresh(item)
    return item
