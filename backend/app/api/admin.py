from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from io import StringIO
import json

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.dependencies import AdminUser, DbSession
from app.models.entities import (
    AdminAuditLog,
    Campus,
    CampusMap,
    CampusProcess,
    Canteen,
    DataRefreshLog,
    FeedbackSubmission,
    FoodStall,
    Location,
    Source,
    SystemLog,
    User,
    VerificationRecord,
    new_id,
    utcnow,
)
from app.schemas.admin import (
    AdminDashboard,
    AdminUserUpdate,
    CampusMapRead,
    CampusMapWrite,
    CampusWrite,
    CanteenWrite,
    FeedbackReview,
    ProcessWrite,
    SourceWrite,
    StallWrite,
)
from app.schemas.auth import UserRead
from app.schemas.campus import CampusRead, CanteenRead, LocationCreate, LocationRead, LocationUpdate, ProcessRead, SourceRead, StallRead


router = APIRouter(prefix="/admin", tags=["admin"])


def audit(db: DbSession, admin_id: str, action: str, entity_type: str = "", entity_id: str = "", summary: str = "") -> None:
    db.add(AdminAuditLog(admin_id=admin_id, action=action, entity_type=entity_type, entity_id=entity_id, summary=summary[:2000]))


def verify_record(db: DbSession, admin_id: str, entity_type: str, entity_id: str, status_value: str, evidence: str, note: str) -> None:
    if status_value == "verified" and not evidence.strip():
        raise HTTPException(status_code=422, detail="标记为已核验时必须填写核验证据")
    if evidence.strip() or note.strip():
        db.add(VerificationRecord(entity_type=entity_type, entity_id=entity_id, status=status_value, evidence=evidence.strip(), note=note.strip(), verified_by=admin_id))


@router.get("/dashboard", response_model=AdminDashboard)
def dashboard(admin: AdminUser, db: DbSession) -> AdminDashboard:
    del admin
    stale_cutoff = datetime.now(UTC) - timedelta(days=180)
    return AdminDashboard(
        users=db.scalar(select(func.count()).select_from(User)) or 0,
        active_users=db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) or 0,
        locations=db.scalar(select(func.count()).select_from(Location).where(Location.is_active.is_(True))) or 0,
        canteens=db.scalar(select(func.count()).select_from(Canteen).where(Canteen.is_active.is_(True))) or 0,
        pending_feedback=db.scalar(select(func.count()).select_from(FeedbackSubmission).where(FeedbackSubmission.status == "pending")) or 0,
        stale_records=db.scalar(select(func.count()).select_from(Location).where((Location.verified_at.is_(None)) | (Location.verified_at < stale_cutoff))) or 0,
        recent_errors=db.scalar(select(func.count()).select_from(SystemLog).where(SystemLog.level == "error", SystemLog.created_at >= datetime.now(UTC) - timedelta(days=7))) or 0,
    )


@router.get("/users", response_model=list[UserRead])
def users(admin: AdminUser, db: DbSession) -> list[User]:
    del admin
    return list(db.scalars(select(User).order_by(User.created_at.desc())))


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(user_id: str, payload: AdminUserUpdate, admin: AdminUser, db: DbSession) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    changes = payload.model_dump(exclude_unset=True)
    if user.id == admin.id and changes.get("is_active") is False:
        raise HTTPException(status_code=400, detail="不能停用当前管理员账户")
    for key, value in changes.items():
        setattr(user, key, value)
    audit(db, admin.id, "user.update", "user", user.id, f"fields={sorted(changes)}")
    db.commit()
    db.refresh(user)
    return user


@router.get("/campuses", response_model=list[CampusRead])
def admin_campuses(admin: AdminUser, db: DbSession) -> list[Campus]:
    del admin
    return list(db.scalars(select(Campus).order_by(Campus.name)))


@router.post("/campuses", status_code=status.HTTP_201_CREATED, response_model=CampusRead)
def create_campus(payload: CampusWrite, admin: AdminUser, db: DbSession) -> Campus:
    campus = Campus(**payload.model_dump())
    db.add(campus)
    db.flush()
    audit(db, admin.id, "campus.create", "campus", campus.id, campus.name)
    db.commit()
    db.refresh(campus)
    return campus


@router.patch("/campuses/{campus_id}", response_model=CampusRead)
def update_campus(campus_id: str, payload: CampusWrite, admin: AdminUser, db: DbSession) -> Campus:
    campus = db.get(Campus, campus_id)
    if not campus:
        raise HTTPException(status_code=404, detail="校区不存在")
    for key, value in payload.model_dump().items():
        setattr(campus, key, value)
    audit(db, admin.id, "campus.update", "campus", campus.id, campus.name)
    db.commit()
    db.refresh(campus)
    return campus


@router.delete("/campuses/{campus_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_campus(campus_id: str, admin: AdminUser, db: DbSession) -> Response:
    campus = db.get(Campus, campus_id)
    if not campus:
        raise HTTPException(status_code=404, detail="校区不存在")
    campus.is_active = False
    audit(db, admin.id, "campus.deactivate", "campus", campus.id, campus.name)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/locations", response_model=list[LocationRead])
def locations(admin: AdminUser, db: DbSession) -> list[Location]:
    del admin
    return list(db.scalars(select(Location).options(selectinload(Location.sources)).order_by(Location.updated_at.desc())).unique())


@router.post("/locations", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
def create_location(payload: LocationCreate, admin: AdminUser, db: DbSession) -> Location:
    data = payload.model_dump(exclude={"source_ids", "evidence", "verification_note", "id"})
    location = Location(id=payload.id or new_id(), **data)
    if payload.source_ids:
        location.sources = list(db.scalars(select(Source).where(Source.id.in_(payload.source_ids))))
    verify_record(db, admin.id, "location", location.id, location.verification_status, payload.evidence, payload.verification_note)
    db.add(location)
    audit(db, admin.id, "location.create", "location", location.id, location.name)
    db.commit()
    db.refresh(location)
    return location


@router.patch("/locations/{location_id}", response_model=LocationRead)
def update_location(location_id: str, payload: LocationUpdate, admin: AdminUser, db: DbSession) -> Location:
    location = db.scalar(select(Location).options(selectinload(Location.sources)).where(Location.id == location_id))
    if not location:
        raise HTTPException(status_code=404, detail="地点不存在")
    changes = payload.model_dump(exclude_unset=True, exclude={"source_ids", "evidence", "verification_note"})
    for key, value in changes.items():
        setattr(location, key, value)
    if payload.source_ids is not None:
        location.sources = list(db.scalars(select(Source).where(Source.id.in_(payload.source_ids))))
    if location.verification_status == "verified":
        location.verified_at = location.verified_at or utcnow()
        location.verified_by = admin.id
    verify_record(db, admin.id, "location", location.id, location.verification_status, payload.evidence, payload.verification_note)
    audit(db, admin.id, "location.update", "location", location.id, f"fields={sorted(changes)}")
    db.commit()
    db.refresh(location)
    return location


@router.delete("/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_location(location_id: str, admin: AdminUser, db: DbSession) -> Response:
    location = db.get(Location, location_id)
    if not location:
        raise HTTPException(status_code=404, detail="地点不存在")
    location.is_active = False
    location.verification_status = "inactive"
    audit(db, admin.id, "location.deactivate", "location", location.id, location.name)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/canteens", response_model=list[CanteenRead])
def canteens(admin: AdminUser, db: DbSession) -> list[Canteen]:
    del admin
    return list(db.scalars(select(Canteen).options(selectinload(Canteen.stalls), selectinload(Canteen.source))).unique())


@router.post("/canteens", response_model=CanteenRead, status_code=status.HTTP_201_CREATED)
def create_canteen(payload: CanteenWrite, admin: AdminUser, db: DbSession) -> Canteen:
    data = payload.model_dump(exclude={"id", "evidence", "verification_note"})
    item = Canteen(id=payload.id or new_id(), **data)
    verify_record(db, admin.id, "canteen", item.id, item.verification_status, payload.evidence, payload.verification_note)
    db.add(item)
    audit(db, admin.id, "canteen.create", "canteen", item.id, item.name)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/canteens/{canteen_id}", response_model=CanteenRead)
def update_canteen(canteen_id: str, payload: CanteenWrite, admin: AdminUser, db: DbSession) -> Canteen:
    item = db.get(Canteen, canteen_id)
    if not item:
        raise HTTPException(status_code=404, detail="饭堂不存在")
    for key, value in payload.model_dump(exclude={"id", "evidence", "verification_note"}).items():
        setattr(item, key, value)
    verify_record(db, admin.id, "canteen", item.id, item.verification_status, payload.evidence, payload.verification_note)
    audit(db, admin.id, "canteen.update", "canteen", item.id, item.name)
    db.commit()
    return item


@router.delete("/canteens/{canteen_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_canteen(canteen_id: str, admin: AdminUser, db: DbSession) -> Response:
    item = db.get(Canteen, canteen_id)
    if not item:
        raise HTTPException(status_code=404, detail="饭堂不存在")
    item.is_active = False
    audit(db, admin.id, "canteen.deactivate", "canteen", item.id, item.name)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/stalls", response_model=list[StallRead])
def stalls(admin: AdminUser, db: DbSession) -> list[FoodStall]:
    del admin
    return list(db.scalars(select(FoodStall).order_by(FoodStall.canteen_id, FoodStall.floor, FoodStall.name)))


@router.post("/stalls", response_model=StallRead, status_code=status.HTTP_201_CREATED)
def create_stall(payload: StallWrite, admin: AdminUser, db: DbSession) -> FoodStall:
    data = payload.model_dump(exclude={"id", "evidence", "verification_note"})
    item = FoodStall(id=payload.id or new_id(), **data)
    verify_record(db, admin.id, "stall", item.id, item.verification_status, payload.evidence, payload.verification_note)
    db.add(item)
    audit(db, admin.id, "stall.create", "stall", item.id, item.name)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/stalls/{stall_id}", response_model=StallRead)
def update_stall(stall_id: str, payload: StallWrite, admin: AdminUser, db: DbSession) -> FoodStall:
    item = db.get(FoodStall, stall_id)
    if not item:
        raise HTTPException(status_code=404, detail="档口不存在")
    for key, value in payload.model_dump(exclude={"id", "evidence", "verification_note"}).items():
        setattr(item, key, value)
    verify_record(db, admin.id, "stall", item.id, item.verification_status, payload.evidence, payload.verification_note)
    audit(db, admin.id, "stall.update", "stall", item.id, item.name)
    db.commit()
    return item


@router.delete("/stalls/{stall_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_stall(stall_id: str, admin: AdminUser, db: DbSession) -> Response:
    item = db.get(FoodStall, stall_id)
    if not item:
        raise HTTPException(status_code=404, detail="档口不存在")
    item.is_active = False
    audit(db, admin.id, "stall.deactivate", "stall", item.id, item.name)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/processes", response_model=list[ProcessRead])
def processes(admin: AdminUser, db: DbSession) -> list[CampusProcess]:
    del admin
    return list(db.scalars(select(CampusProcess).options(selectinload(CampusProcess.source)).order_by(CampusProcess.title)))


@router.post("/processes", response_model=ProcessRead, status_code=status.HTTP_201_CREATED)
def create_process(payload: ProcessWrite, admin: AdminUser, db: DbSession) -> CampusProcess:
    data = payload.model_dump(exclude={"id", "evidence", "verification_note"})
    item = CampusProcess(id=payload.id or new_id(), **data)
    verify_record(db, admin.id, "process", item.id, item.verification_status, payload.evidence, payload.verification_note)
    db.add(item)
    audit(db, admin.id, "process.create", "process", item.id, item.title)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/processes/{process_id}", response_model=ProcessRead)
def update_process(process_id: str, payload: ProcessWrite, admin: AdminUser, db: DbSession) -> CampusProcess:
    item = db.get(CampusProcess, process_id)
    if not item:
        raise HTTPException(status_code=404, detail="办事流程不存在")
    for key, value in payload.model_dump(exclude={"id", "evidence", "verification_note"}).items():
        setattr(item, key, value)
    verify_record(db, admin.id, "process", item.id, item.verification_status, payload.evidence, payload.verification_note)
    audit(db, admin.id, "process.update", "process", item.id, item.title)
    db.commit()
    return item


@router.delete("/processes/{process_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_process(process_id: str, admin: AdminUser, db: DbSession) -> Response:
    item = db.get(CampusProcess, process_id)
    if not item:
        raise HTTPException(status_code=404, detail="办事流程不存在")
    item.is_active = False
    audit(db, admin.id, "process.deactivate", "process", item.id, item.title)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/feedback", response_model=None)
def feedback(admin: AdminUser, db: DbSession, review_status: str = "pending") -> list[FeedbackSubmission]:
    del admin
    return list(db.scalars(select(FeedbackSubmission).where(FeedbackSubmission.status == review_status).order_by(FeedbackSubmission.created_at.desc())))


def _review_feedback(feedback_id: str, decision: str, payload: FeedbackReview, admin: AdminUser, db: DbSession) -> FeedbackSubmission:
    item = db.get(FeedbackSubmission, feedback_id)
    if not item:
        raise HTTPException(status_code=404, detail="纠错不存在")
    item.status = decision
    item.reviewed_by = admin.id
    item.reviewed_at = utcnow()
    item.review_note = payload.note
    audit(db, admin.id, f"feedback.{decision}", "feedback", item.id, payload.note)
    db.commit()
    return item


@router.post("/feedback/{feedback_id}/approve", response_model=None)
def approve_feedback(feedback_id: str, payload: FeedbackReview, admin: AdminUser, db: DbSession) -> FeedbackSubmission:
    return _review_feedback(feedback_id, "approved", payload, admin, db)


@router.post("/feedback/{feedback_id}/reject", response_model=None)
def reject_feedback(feedback_id: str, payload: FeedbackReview, admin: AdminUser, db: DbSession) -> FeedbackSubmission:
    return _review_feedback(feedback_id, "rejected", payload, admin, db)


@router.get("/sources", response_model=list[SourceRead])
def sources(admin: AdminUser, db: DbSession) -> list[Source]:
    del admin
    return list(db.scalars(select(Source).order_by(Source.updated_at.desc())))


@router.post("/sources", status_code=status.HTTP_201_CREATED, response_model=SourceRead)
def create_source(payload: SourceWrite, admin: AdminUser, db: DbSession) -> Source:
    item = Source(**payload.model_dump())
    db.add(item)
    db.flush()
    audit(db, admin.id, "source.create", "source", item.id, item.title)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/sources/{source_id}", response_model=SourceRead)
def update_source(source_id: str, payload: SourceWrite, admin: AdminUser, db: DbSession) -> Source:
    item = db.get(Source, source_id)
    if not item:
        raise HTTPException(status_code=404, detail="资料来源不存在")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    audit(db, admin.id, "source.update", "source", item.id, item.title)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: str, admin: AdminUser, db: DbSession) -> Response:
    item = db.get(Source, source_id)
    if not item:
        raise HTTPException(status_code=404, detail="资料来源不存在")
    audit(db, admin.id, "source.delete", "source", item.id, item.title)
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/maps", response_model=list[CampusMapRead])
def maps(admin: AdminUser, db: DbSession) -> list[CampusMap]:
    del admin
    return list(db.scalars(select(CampusMap).order_by(CampusMap.updated_at.desc())))


@router.post("/maps", status_code=status.HTTP_201_CREATED, response_model=CampusMapRead)
def create_map(payload: CampusMapWrite, admin: AdminUser, db: DbSession) -> CampusMap:
    item = CampusMap(**payload.model_dump())
    db.add(item)
    db.flush()
    audit(db, admin.id, "map.create", "campus_map", item.id, payload.image_url)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/maps/{map_id}", response_model=CampusMapRead)
def update_map(map_id: str, payload: CampusMapWrite, admin: AdminUser, db: DbSession) -> CampusMap:
    item = db.get(CampusMap, map_id)
    if not item:
        raise HTTPException(status_code=404, detail="校园地图不存在")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    audit(db, admin.id, "map.update", "campus_map", item.id, item.image_url)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/maps/{map_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_map(map_id: str, admin: AdminUser, db: DbSession) -> Response:
    item = db.get(CampusMap, map_id)
    if not item:
        raise HTTPException(status_code=404, detail="校园地图不存在")
    audit(db, admin.id, "map.delete", "campus_map", item.id, item.image_url)
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/stale")
def stale_data(admin: AdminUser, db: DbSession) -> list[dict]:
    del admin
    cutoff = datetime.now(UTC) - timedelta(days=180)
    rows = list(db.scalars(select(Location).where((Location.verified_at.is_(None)) | (Location.verified_at < cutoff))))
    return [{"id": row.id, "name": row.name, "verification_status": row.verification_status, "verified_at": row.verified_at, "updated_at": row.updated_at} for row in rows]


@router.get("/logs")
def logs(admin: AdminUser, db: DbSession) -> dict:
    del admin
    def fields(row, names: tuple[str, ...]) -> dict:
        return {name: getattr(row, name) for name in names}

    return {
        "audit": [
            fields(row, ("id", "admin_id", "action", "entity_type", "entity_id", "summary", "created_at"))
            for row in db.scalars(select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc()).limit(100))
        ],
        "system": [
            fields(row, ("id", "level", "event", "message", "request_id", "created_at"))
            for row in db.scalars(select(SystemLog).order_by(SystemLog.created_at.desc()).limit(100))
        ],
        "refresh": [
            fields(row, ("id", "source_id", "status", "changed", "message", "fetched_at"))
            for row in db.scalars(select(DataRefreshLog).order_by(DataRefreshLog.fetched_at.desc()).limit(100))
        ],
    }


@router.post("/data/import")
async def import_data(admin: AdminUser, db: DbSession, file: UploadFile = File()) -> dict:
    payload = await file.read(get_settings().max_upload_bytes + 1)
    if len(payload) > get_settings().max_upload_bytes:
        raise HTTPException(status_code=413, detail="导入文件不得超过 5 MB")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="导入文件必须为 UTF-8") from exc
    suffix = (file.filename or "").lower().rsplit(".", 1)[-1]
    try:
        if suffix == "csv":
            rows = list(csv.DictReader(StringIO(text)))
            for row in rows:
                for key in ("aliases", "services", "payment_methods", "source_ids"):
                    row[key] = [value.strip() for value in row.get(key, "").split("|") if value.strip()]
                for key in ("latitude", "longitude", "map_x", "map_y", "confidence"):
                    row[key] = float(row[key]) if row.get(key) else None
        elif suffix in {"json", "geojson"}:
            raw = json.loads(text)
            if raw.get("type") == "FeatureCollection":
                rows = []
                for feature in raw.get("features", []):
                    row = dict(feature.get("properties", {}))
                    coordinates = feature.get("geometry", {}).get("coordinates", [])
                    if len(coordinates) >= 2:
                        row["longitude"], row["latitude"] = coordinates[:2]
                    rows.append(row)
            else:
                rows = raw.get("locations", raw if isinstance(raw, list) else [raw])
        else:
            raise HTTPException(status_code=415, detail="仅支持 CSV、JSON 和 GeoJSON")
        created = 0
        for row in rows:
            model = LocationCreate.model_validate(row)
            data = model.model_dump(exclude={"id", "source_ids", "evidence", "verification_note"})
            item = Location(id=model.id or new_id(), **data)
            item.sources = list(db.scalars(select(Source).where(Source.id.in_(model.source_ids)))) if model.source_ids else []
            db.add(item)
            created += 1
        audit(db, admin.id, "data.import", "location", "", f"file={file.filename}; created={created}")
        db.commit()
        return {"created": created, "filename": file.filename}
    except HTTPException:
        raise
    except (ValueError, json.JSONDecodeError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=f"导入数据格式错误：{exc}") from exc


@router.get("/data/export")
def export_data(admin: AdminUser, db: DbSession) -> Response:
    del admin
    locations = list(db.scalars(select(Location).options(selectinload(Location.sources))).unique())
    payload = [LocationRead.model_validate(item).model_dump(mode="json") for item in locations]
    return Response(json.dumps({"locations": payload}, ensure_ascii=False, indent=2), media_type="application/json; charset=utf-8", headers={"Content-Disposition": "attachment; filename=gduf-locations.json"})
