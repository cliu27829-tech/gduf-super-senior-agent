from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.core.dependencies import CurrentUser, DbSession
from app.models.entities import Campus, CampusProcess, Canteen, FeedbackSubmission, FoodStall, Location
from app.schemas.campus import CanteenRead, CampusRead, FeedbackCreate, LocationRead, ProcessRead, StallRead


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
    query = select(Location).options(selectinload(Location.sources)).where(Location.is_active.is_(True))
    if campus_id:
        query = query.where(Location.campus_id == campus_id)
    if category:
        query = query.where(Location.category == category)
    if q.strip():
        needle = f"%{q.strip()}%"
        query = query.where(or_(Location.name.ilike(needle), Location.description.ilike(needle), Location.address.ilike(needle)))
    return list(db.scalars(query.order_by(Location.name)).unique())


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
    query = select(Location).where(Location.campus_id == campus_id, Location.is_active.is_(True))
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
    item = db.scalar(select(Location).options(selectinload(Location.sources)).where(Location.id == location_id, Location.is_active.is_(True)))
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
def list_canteens(db: DbSession, campus_id: str | None = None, q: str = "") -> list[Canteen]:
    query = select(Canteen).options(selectinload(Canteen.stalls), selectinload(Canteen.source)).where(Canteen.is_active.is_(True))
    if campus_id:
        query = query.where(Canteen.campus_id == campus_id)
    if q.strip():
        query = query.where(Canteen.name.ilike(f"%{q.strip()}%"))
    return list(db.scalars(query.order_by(Canteen.name)).unique())


@router.get("/canteens/{canteen_id}", response_model=CanteenRead)
def get_canteen(canteen_id: str, db: DbSession) -> Canteen:
    item = db.scalar(select(Canteen).options(selectinload(Canteen.stalls), selectinload(Canteen.source)).where(Canteen.id == canteen_id, Canteen.is_active.is_(True)))
    if not item:
        raise HTTPException(status_code=404, detail="饭堂不存在")
    return item


@router.get("/canteens/{canteen_id}/stalls", response_model=list[StallRead])
def list_stalls(canteen_id: str, db: DbSession) -> list[FoodStall]:
    return list(db.scalars(select(FoodStall).where(FoodStall.canteen_id == canteen_id, FoodStall.is_active.is_(True)).order_by(FoodStall.floor, FoodStall.name)))


@router.get("/food-search")
def food_search(db: DbSession, q: str = Query(min_length=1, max_length=100), campus_id: str | None = None) -> dict:
    query = (
        select(FoodStall)
        .options(selectinload(FoodStall.canteen))
        .join(Canteen)
        .where(
            FoodStall.is_active.is_(True),
            FoodStall.verified_at.is_not(None),
            FoodStall.verification_status == "verified",
            or_(FoodStall.name.ilike(f"%{q}%"), FoodStall.food_type.ilike(f"%{q}%")),
        )
    )
    if campus_id:
        query = query.where(Canteen.campus_id == campus_id)
    rows = list(db.scalars(query))
    return {
        "items": [
            {
                "id": item.id,
                "canteen": item.canteen.name,
                "name": item.name,
                "food_type": item.food_type,
                "common_items": item.common_items,
                "verified_at": item.verified_at,
            }
            for item in rows
        ],
        "today_menu_available": False,
        "message": "没有可靠的今日菜单；结果仅包含已核验的常见餐品。" if rows else "没有匹配的已核验餐品，系统不会根据占位数据补写。",
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

