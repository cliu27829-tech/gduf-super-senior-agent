from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.entities import Campus, Canteen, FoodStall, Location, Source, User


CAMPUS_DEFINITIONS = (
    ("guangzhou", "广州校本部"),
    ("zhaoqing", "肇庆校区"),
    ("qingyuan", "清远校区"),
)


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def seed_database(db: Session) -> None:
    settings = get_settings()
    campus_by_name: dict[str, Campus] = {}
    for slug, name in CAMPUS_DEFINITIONS:
        campus = db.scalar(select(Campus).where(Campus.slug == slug))
        if not campus:
            campus = Campus(slug=slug, name=name, data_notice="历史与待核验数据并存，请查看每条记录的来源和核验状态。")
            db.add(campus)
            db.flush()
        campus_by_name[name] = campus

    location_by_id: dict[str, Location] = {}
    campus_root = Path(settings.data_root) / "campuses"
    for slug, _ in CAMPUS_DEFINITIONS:
        path = campus_root / slug / "locations.json"
        if not path.exists():
            continue
        for item in json.loads(path.read_text(encoding="utf-8")):
            existing = db.get(Location, item["id"])
            if existing:
                location_by_id[existing.id] = existing
                continue
            source_models: list[Source] = []
            for source_data in item.get("source_references", []):
                source = db.scalar(select(Source).where(Source.url == source_data.get("url", ""), Source.title == source_data.get("title", "")))
                if not source:
                    source = Source(
                        title=source_data.get("title", "待补充"),
                        url=source_data.get("url", ""),
                        publisher=source_data.get("publisher", ""),
                        source_type=source_data.get("source_status", "unverified"),
                        published_at=_date(source_data.get("published_at")),
                        fetched_at=None,
                        verified_at=None,
                        confidence=float(item.get("confidence", 0)),
                        is_official=bool(source_data.get("is_official", False)),
                    )
                    db.add(source)
                    db.flush()
                source_models.append(source)
            location = Location(
                id=item["id"],
                campus_id=campus_by_name[item["campus"]].id,
                name=item["name"],
                aliases=item.get("aliases", []),
                category=item.get("category", "other"),
                sub_category=item.get("sub_category", ""),
                description=item.get("description", ""),
                address=item.get("address", ""),
                area=item.get("area", ""),
                floor=item.get("floor", ""),
                latitude=item.get("latitude"),
                longitude=item.get("longitude"),
                map_x=item.get("map_x"),
                map_y=item.get("map_y"),
                opening_hours=item.get("opening_hours", ""),
                services=item.get("services", []),
                payment_methods=item.get("payment_methods", []),
                verification_status=item.get("freshness_status", "needs_verification"),
                verification_method=item.get("verification_method", "unverified_seed"),
                verified_at=_date(item.get("verified_at")),
                confidence=float(item.get("confidence", 0)),
                freshness_status=item.get("freshness_status", "needs_verification"),
                data_status=item.get("data_status", "demo_fixture"),
                is_active=bool(item.get("is_active", True)),
                sources=source_models,
            )
            db.add(location)
            db.flush()
            location_by_id[location.id] = location
            if location.category == "canteen":
                source_id = source_models[0].id if source_models else None
                canteen = Canteen(
                    id=f"canteen-{location.id}",
                    campus_id=location.campus_id,
                    location_id=location.id,
                    source_id=source_id,
                    name=location.name,
                    floors=[location.floor] if location.floor else [],
                    opening_hours=location.opening_hours,
                    payment_methods=location.payment_methods,
                    verification_status=location.verification_status,
                    verified_at=location.verified_at,
                    confidence=location.confidence,
                    is_active=location.is_active,
                )
                db.add(canteen)
                db.flush()

    for slug, name in CAMPUS_DEFINITIONS:
        path = campus_root / slug / "canteens.json"
        if not path.exists():
            continue
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            items = []
        for item in items:
            if db.get(FoodStall, item.get("id")):
                continue
            canteen = db.scalar(select(Canteen).where(Canteen.location_id == item.get("canteen_id")))
            if not canteen:
                continue
            db.add(
                FoodStall(
                    id=item["id"], canteen_id=canteen.id, name=item["name"], floor=item.get("floor", ""),
                    food_type=item.get("food_type", ""), common_items=item.get("common_items", []),
                    price_range=item.get("price_range", ""), meal_periods=item.get("meal_periods", []),
                    opening_hours=item.get("opening_hours", ""), payment_methods=item.get("payment_methods", []),
                    is_operating=item.get("is_operating"), verification_status="needs_verification",
                    verified_at=_date(item.get("verified_at")), confidence=float(item.get("confidence", 0)),
                    is_active=bool(item.get("is_active", True)),
                )
            )

    if settings.admin_bootstrap_email and settings.admin_bootstrap_password:
        email = settings.admin_bootstrap_email.strip().lower()
        if not db.scalar(select(User).where(User.email == email)):
            default_campus = next(iter(campus_by_name.values()))
            db.add(
                User(
                    email=email,
                    username="admin",
                    nickname="系统管理员",
                    password_hash=hash_password(settings.admin_bootstrap_password),
                    role="admin",
                    campus_id=default_campus.id,
                )
            )
    db.commit()

