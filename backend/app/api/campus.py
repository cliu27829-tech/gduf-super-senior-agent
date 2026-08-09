from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
import re

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.core.dependencies import CurrentUser, DbSession
from app.models.entities import Campus, CampusProcess, Canteen, FeedbackSubmission, FoodStall, KnowledgeDocument, Location, Task
from app.schemas.campus import (
    CanteenRead, CampusRead, FeedbackCreate, KnowledgeRead, LocationRead, ProcessRead, ProcessTaskCreate, StallRead,
)
from app.schemas.tasks import TaskRead


router = APIRouter(tags=["campus"])


@router.get("/campuses", response_model=list[CampusRead])
def list_campuses(db: DbSession) -> list[Campus]:
    return list(db.scalars(select(Campus).where(Campus.is_active.is_(True)).order_by(Campus.name)))


@router.get("/locations", response_model=list[LocationRead])
def list_locations(
    db: DbSession,
    campus_id: str | None = None,
    category: str | None = None,
    q: str = "",
) -> list[Location]:
    query = select(Location).options(selectinload(Location.sources)).where(
        Location.is_active.is_(True), Location.data_status != "demo_fixture"
    )
    if campus_id:
        query = query.where(Location.campus_id == campus_id)
    if category:
        query = query.where(Location.category == category)
    rows = list(db.scalars(query.order_by(Location.name)).unique())
    if q.strip():
        needle = q.strip().lower()
        rows = [
            item for item in rows
            if needle in " ".join([item.name, *item.aliases, item.description, item.address, item.area, *item.services]).lower()
        ]
    return rows


@router.get("/locations/search", response_model=list[LocationRead])
def search_locations(
    db: DbSession,
    q: str = Query(min_length=1, max_length=120),
    campus_id: str | None = None,
    category: str | None = None,
) -> list[Location]:
    return list_locations(db=db, campus_id=campus_id, category=category, q=q)


def _distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    value = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return 2 * radius * asin(sqrt(value))


@router.get("/locations/nearby")
def nearby_locations(
    db: DbSession,
    campus_id: str,
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    map_x: float | None = Query(default=None, ge=0, le=1),
    map_y: float | None = Query(default=None, ge=0, le=1),
    category: str | None = None,
    limit: int = Query(default=8, ge=1, le=50),
) -> list[dict]:
    query = select(Location).where(
        Location.campus_id == campus_id,
        Location.is_active.is_(True),
        Location.data_status != "demo_fixture",
    )
    if category:
        query = query.where(Location.category == category)
    ranked: list[dict] = []
    for item in db.scalars(query):
        if None not in (latitude, longitude, item.latitude, item.longitude):
            distance = _distance(float(latitude), float(longitude), float(item.latitude), float(item.longitude))
            precision, unit = "gps", "m"
        elif None not in (map_x, map_y, item.map_x, item.map_y):
            distance = sqrt((float(map_x) - float(item.map_x)) ** 2 + (float(map_y) - float(item.map_y)) ** 2)
            precision, unit = "schematic", "schematic_unit"
        else:
            continue
        ranked.append({"location": LocationRead.model_validate(item).model_dump(mode="json"), "distance": round(distance, 3), "precision": precision, "unit": unit})
    return sorted(ranked, key=lambda value: value["distance"])[:limit]


@router.get("/locations/{location_id}", response_model=LocationRead)
def get_location(location_id: str, db: DbSession) -> Location:
    item = db.scalar(select(Location).options(selectinload(Location.sources)).where(
        Location.id == location_id, Location.is_active.is_(True), Location.data_status != "demo_fixture"
    ))
    if not item:
        raise HTTPException(status_code=404, detail="地点不存在")
    return item


@router.post("/location-feedback", status_code=status.HTTP_201_CREATED)
def submit_feedback(payload: FeedbackCreate, user: CurrentUser, db: DbSession) -> dict:
    if not db.get(Campus, payload.campus_id):
        raise HTTPException(status_code=422, detail="校区不存在")
    if payload.location_id and not db.get(Location, payload.location_id):
        raise HTTPException(status_code=422, detail="地点不存在")
    feedback = FeedbackSubmission(user_id=user.id, **payload.model_dump())
    db.add(feedback)
    db.commit()
    return {"id": feedback.id, "status": feedback.status, "message": "纠错已提交，等待管理员审核"}


@router.get("/canteens", response_model=list[CanteenRead])
def list_canteens(db: DbSession, campus_id: str | None = None, q: str = "") -> list[CanteenRead]:
    query = select(Canteen).options(
        selectinload(Canteen.stalls), selectinload(Canteen.source), selectinload(Canteen.location)
    ).where(
        Canteen.is_active.is_(True), Canteen.data_status != "demo_fixture"
    )
    if campus_id:
        query = query.where(Canteen.campus_id == campus_id)
    if q.strip():
        query = query.where(Canteen.name.ilike(f"%{q.strip()}%"))
    rows = list(db.scalars(query.order_by(Canteen.name)).unique())
    return [
        CanteenRead.model_validate(row).model_copy(
            update={"stalls": [StallRead.model_validate(stall) for stall in row.stalls if stall.is_active and stall.data_status != "demo_fixture"]}
        )
        for row in rows
    ]


@router.get("/canteens/{canteen_id}", response_model=CanteenRead)
def get_canteen(canteen_id: str, db: DbSession) -> CanteenRead:
    item = db.scalar(select(Canteen).options(
        selectinload(Canteen.stalls), selectinload(Canteen.source), selectinload(Canteen.location)
    ).where(
        Canteen.id == canteen_id, Canteen.is_active.is_(True), Canteen.data_status != "demo_fixture"
    ))
    if not item:
        raise HTTPException(status_code=404, detail="饭堂不存在")
    return CanteenRead.model_validate(item).model_copy(
        update={"stalls": [StallRead.model_validate(stall) for stall in item.stalls if stall.is_active and stall.data_status != "demo_fixture"]}
    )


@router.get("/canteens/{canteen_id}/stalls", response_model=list[StallRead])
def list_stalls(canteen_id: str, db: DbSession) -> list[FoodStall]:
    return list(db.scalars(select(FoodStall).where(
        FoodStall.canteen_id == canteen_id,
        FoodStall.is_active.is_(True),
        FoodStall.data_status != "demo_fixture",
    ).order_by(FoodStall.floor, FoodStall.name)))


@router.get("/food-search")
def food_search(db: DbSession, q: str = Query(min_length=1, max_length=100), campus_id: str | None = None) -> dict:
    query = (
        select(FoodStall)
        .options(selectinload(FoodStall.canteen))
        .join(Canteen)
        .where(
            FoodStall.is_active.is_(True),
            FoodStall.data_status != "demo_fixture",
            Canteen.is_active.is_(True),
            Canteen.data_status != "demo_fixture",
        )
    )
    if campus_id:
        query = query.where(Canteen.campus_id == campus_id)
    candidates = list(db.scalars(query))
    needle = q.strip().lower()
    rows = [
        item for item in candidates
        if needle in " ".join([item.name, item.food_type, *item.common_items, *item.meal_periods]).lower()
    ]
    return {
        "items": [
            {
                "id": item.id,
                "canteen": item.canteen.name,
                "name": item.name,
                "food_type": item.food_type,
                "common_items": item.common_items,
                "verified_at": item.verified_at,
                "data_status": item.data_status,
            }
            for item in rows
        ],
        "today_menu_available": False,
        "message": "目前没有可靠的当日菜单数据，以下是最近一次核验的档口或常见餐品信息，不保证今日全部供应。" if rows else "目前没有可靠的当日菜单数据，也没有匹配的可公开档口或常见餐品记录；系统不会编造今日供应。",
    }


@router.get("/processes", response_model=list[ProcessRead])
def list_processes(db: DbSession, campus_id: str | None = None, q: str = "") -> list[CampusProcess]:
    query = select(CampusProcess).options(selectinload(CampusProcess.source)).where(CampusProcess.is_active.is_(True))
    if campus_id:
        query = query.where(or_(CampusProcess.campus_id == campus_id, CampusProcess.campus_id.is_(None)))
    if q.strip():
        query = query.where(CampusProcess.title.ilike(f"%{q.strip()}%"))
    return list(db.scalars(query.order_by(CampusProcess.title)))


@router.get("/processes/{process_id}", response_model=ProcessRead)
def get_process(process_id: str, db: DbSession) -> CampusProcess:
    item = db.scalar(select(CampusProcess).options(selectinload(CampusProcess.source)).where(CampusProcess.id == process_id, CampusProcess.is_active.is_(True)))
    if not item:
        raise HTTPException(status_code=404, detail="办事流程不存在")
    return item


@router.post("/processes/{process_id}/create-tasks", response_model=list[TaskRead], status_code=status.HTTP_201_CREATED)
def create_process_tasks(
    process_id: str,
    payload: ProcessTaskCreate,
    user: CurrentUser,
    db: DbSession,
) -> list[Task]:
    if not payload.confirmed:
        raise HTTPException(status_code=422, detail="保存办事步骤前必须明确确认")
    item = db.scalar(
        select(CampusProcess).options(selectinload(CampusProcess.source)).where(
            CampusProcess.id == process_id, CampusProcess.is_active.is_(True)
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="办事流程不存在")
    if item.campus_id and user.campus_id and item.campus_id != user.campus_id:
        raise HTTPException(status_code=422, detail="该流程不属于当前用户校区")
    tasks: list[Task] = []
    source_url = item.online_url or (item.source.url if item.source else "")
    if payload.include_overview:
        tasks.append(Task(
            user_id=user.id,
            title=item.title,
            description=item.notes,
            location=item.location,
            task_type="campus_process",
            materials=item.materials,
            source_text=f"适用人群：{item.audience}\n联系方式：{item.contact}\n开放时间：{item.opening_hours}".strip(),
            source_url=source_url,
        ))
    for index, step in enumerate(item.steps, start=1):
        text = str(step.get("text") or step.get("title") or "").strip()
        if not text:
            continue
        tasks.append(Task(
            user_id=user.id,
            title=f"{item.title} · 第 {index} 步",
            description=text,
            location=item.location,
            task_type="campus_process_step",
            source_text=item.title,
            source_url=source_url,
        ))
    if not tasks:
        raise HTTPException(status_code=422, detail="该流程没有可保存的步骤")
    db.add_all(tasks)
    db.commit()
    for task in tasks:
        db.refresh(task)
    return tasks


def _knowledge_score(query: str, item: KnowledgeDocument) -> float:
    normalized = re.sub(r"\s+", "", query.lower())
    if not normalized:
        return 0
    text = f"{item.title}\n{item.content}".lower()
    terms = set(re.findall(r"[a-z0-9]{2,}|[\u4e00-\u9fff]{2,8}", query.lower()))
    if len(normalized) >= 2:
        terms.update(normalized[index:index + 2] for index in range(len(normalized) - 1))
    score = sum((5 if term in item.title.lower() else 1) * text.count(term) for term in terms if term)
    if normalized in text:
        score += 12
    if item.is_official:
        score *= 1.25
    return float(score)


@router.get("/knowledge", response_model=list[KnowledgeRead])
def search_knowledge(
    db: DbSession,
    q: str = Query(min_length=2, max_length=200),
    campus_id: str | None = None,
    limit: int = Query(default=8, ge=1, le=30),
) -> list[KnowledgeDocument]:
    query = select(KnowledgeDocument).options(selectinload(KnowledgeDocument.source)).where(
        KnowledgeDocument.is_active.is_(True), KnowledgeDocument.data_status != "demo_fixture"
    )
    if campus_id:
        query = query.where(or_(KnowledgeDocument.campus_id == campus_id, KnowledgeDocument.campus_id.is_(None)))
    ranked = [(_knowledge_score(q, row), row) for row in db.scalars(query)]
    return [row for score, row in sorted(ranked, key=lambda pair: (-pair[0], pair[1].title)) if score >= 2][:limit]
