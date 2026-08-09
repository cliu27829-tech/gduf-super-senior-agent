from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models.entities import (
    Campus, CampusCollege, CampusFact, CampusPathEdge, CampusPathNode, CampusProcess, Canteen, FoodStall,
    KnowledgeDocument, Location, Source, User,
)


CAMPUS_DEFINITIONS = (
    ("guangzhou", "广州校本部", "广州市天河区龙洞迎福路527号"),
    ("zhaoqing", "肇庆校区", "广东省肇庆市星湖石牌"),
    ("qingyuan", "清远校区", "广东省清远市清城区东城街道环城东路北1号"),
)

DATA_STATUS_MAP = {
    "historical_seed": "historical",
    "unverified_seed": "needs_verification",
    "admin_entry": "needs_verification",
}
PROTECTED_STATUSES = {"admin_verified", "user_verified"}


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def _data_status(value: str | None) -> str:
    return DATA_STATUS_MAP.get(value or "needs_verification", value or "needs_verification")


def _source(db: Session, data: dict, confidence: float = 0.0) -> Source:
    url = str(data.get("url") or "")
    title = str(data.get("title") or "来源待补充")
    source = db.scalar(select(Source).where(Source.url == url, Source.title == title))
    if not source:
        source = Source(title=title, url=url)
        db.add(source)
        db.flush()
    source.publisher = str(data.get("publisher") or "")
    source.source_type = str(data.get("source_type") or data.get("source_status") or "unverified")
    source.published_at = _date(data.get("published_at"))
    source.fetched_at = _date(data.get("fetched_at"))
    source.verified_at = _date(data.get("verified_at"))
    source.confidence = float(data.get("confidence", confidence))
    source.is_official = bool(data.get("is_official", False))
    return source


def _verification_status(data_status: str) -> str:
    return "verified" if data_status in {"official", "amap_verified", "admin_verified", "user_verified"} else "needs_verification"


def seed_database(db: Session) -> None:
    settings = get_settings()
    campus_by_name: dict[str, Campus] = {}
    for slug, name, address in CAMPUS_DEFINITIONS:
        campus = db.scalar(select(Campus).where(Campus.slug == slug))
        if not campus:
            campus = Campus(slug=slug, name=name)
            db.add(campus)
            db.flush()
        campus.address = address
        campus.data_notice = "仅展示有来源的公开记录；历史资料和待核验信息会明确标记，演示数据默认隐藏。"
        campus_by_name[name] = campus

    campus_root = Path(settings.data_root) / "campuses"
    for slug, _, _ in CAMPUS_DEFINITIONS:
        path = campus_root / slug / "locations.json"
        if not path.exists():
            continue
        for item in json.loads(path.read_text(encoding="utf-8")):
            status = _data_status(item.get("data_status"))
            location = db.get(Location, item["id"])
            if location and location.data_status in PROTECTED_STATUSES:
                continue
            if not location:
                location = Location(id=item["id"], campus_id=campus_by_name[item["campus"]].id, name=item["name"], category=item.get("category", "other"))
                db.add(location)
            sources = [_source(db, source_data, float(item.get("confidence", 0))) for source_data in item.get("source_references", [])]
            location.campus_id = campus_by_name[item["campus"]].id
            location.name = item["name"]
            location.aliases = item.get("aliases", [])
            location.category = item.get("category", "other")
            location.sub_category = item.get("sub_category", "")
            location.description = item.get("description", "")
            location.address = item.get("address", "")
            location.area = item.get("area", "")
            location.floor = item.get("floor", "")
            location.latitude = item.get("latitude")
            location.longitude = item.get("longitude")
            location.map_x = item.get("map_x")
            location.map_y = item.get("map_y")
            location.opening_hours = item.get("opening_hours", "")
            location.phone = item.get("phone", "")
            location.services = item.get("services", [])
            location.payment_methods = item.get("payment_methods", [])
            location.verification_status = _verification_status(status)
            location.verification_method = item.get("verification_method", "unverified_seed")
            location.verified_at = _date(item.get("verified_at"))
            location.coordinate_source = item.get("coordinate_source", "")
            location.coordinate_accuracy = item.get("coordinate_accuracy", "unknown")
            location.coordinate_verified_at = _date(item.get("coordinate_verified_at"))
            location.coordinate_verified_by = item.get("coordinate_verified_by", "")
            location.coordinate_note = item.get("coordinate_note", "")
            location.amap_poi_id = item.get("amap_poi_id", "")
            location.confidence = float(item.get("confidence", 0))
            location.freshness_status = item.get("freshness_status", "needs_verification")
            location.data_status = status
            location.is_active = bool(item.get("is_active", True))
            location.sources = sources
            db.flush()

            if location.category == "canteen":
                canteen_id = f"canteen-{location.id}"
                canteen = db.get(Canteen, canteen_id)
                if not canteen:
                    canteen = Canteen(id=canteen_id, campus_id=location.campus_id, name=location.name)
                    db.add(canteen)
                if canteen.data_status not in PROTECTED_STATUSES:
                    canteen.campus_id = location.campus_id
                    canteen.location_id = location.id
                    canteen.source_id = sources[0].id if sources else None
                    canteen.name = location.name
                    canteen.floors = [location.floor] if location.floor else []
                    canteen.opening_hours = location.opening_hours
                    canteen.payment_methods = location.payment_methods
                    canteen.verification_status = location.verification_status
                    canteen.data_status = status
                    canteen.verified_at = location.verified_at
                    canteen.confidence = location.confidence
                    canteen.is_active = location.is_active
                db.flush()

    for slug, name, _ in CAMPUS_DEFINITIONS:
        path = campus_root / slug / "canteens.json"
        if not path.exists():
            continue
        try:
            items = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            items = []
        for item in items:
            canteen = db.scalar(select(Canteen).where(Canteen.location_id == item.get("canteen_id")))
            if not canteen:
                continue
            status = _data_status(item.get("data_status"))
            stall = db.get(FoodStall, item["id"])
            if stall and stall.data_status in PROTECTED_STATUSES:
                continue
            if not stall:
                stall = FoodStall(id=item["id"], canteen_id=canteen.id, name=item["name"])
                db.add(stall)
            stall.canteen_id = canteen.id
            stall.name = item["name"]
            stall.floor = item.get("floor", "")
            stall.food_type = item.get("food_type", "")
            stall.common_items = item.get("common_items", [])
            stall.price_range = item.get("price_range", "")
            stall.meal_periods = item.get("meal_periods", [])
            stall.opening_hours = item.get("opening_hours", "")
            stall.payment_methods = item.get("payment_methods", [])
            stall.is_operating = item.get("is_operating")
            stall.verification_status = _verification_status(status)
            stall.data_status = status
            stall.verified_at = _date(item.get("verified_at"))
            stall.confidence = float(item.get("confidence", 0))
            stall.is_active = bool(item.get("is_active", True))

    qingyuan_facts = campus_root / "qingyuan" / "facts.json"
    if qingyuan_facts.exists():
        package = json.loads(qingyuan_facts.read_text(encoding="utf-8"))
        source = package["source"]
        campus = campus_by_name["清远校区"]
        for item in package.get("colleges", []):
            row = db.scalar(select(CampusCollege).where(
                CampusCollege.campus_id == campus.id,
                CampusCollege.name == item["name"],
                CampusCollege.education_mode == item["education_mode"],
            ))
            if not row:
                row = CampusCollege(campus_id=campus.id, name=item["name"], education_mode=item["education_mode"])
                db.add(row)
            row.grades = item.get("grades", [])
            row.source_url = source["url"]
            row.source_title = source["title"]
            row.source_published_at = _date(source["published_at"])
            row.verified = True
            row.note = "学院分类按官方清远校区简介的办学模式口径记录。"
        for item in package.get("facts", []):
            row = db.scalar(select(CampusFact).where(
                CampusFact.campus_id == campus.id,
                CampusFact.subject == item["subject"],
                CampusFact.predicate == item["predicate"],
            ))
            if not row:
                row = CampusFact(campus_id=campus.id, subject=item["subject"], predicate=item["predicate"], object=item["object"])
                db.add(row)
            row.object = item["object"]
            row.aliases = item.get("aliases", [])
            row.source_url = source["url"]
            row.source_title = source["title"]
            row.source_type = "official_page"
            row.published_at = _date(source["published_at"])
            row.verified = True
            row.verification_status = "verified"

    old_demo_stall = db.get(FoodStall, "gz-north-demo-stall")
    if old_demo_stall:
        old_demo_stall.data_status = "demo_fixture"
        old_demo_stall.is_active = False

    # Retire the former aggregate so searches do not return both "南区宿舍楼"
    # and the official 1-5 building records. Existing foreign keys remain valid.
    legacy_south_dorms = db.get(Location, "qy-south-dorms")
    if legacy_south_dorms and legacy_south_dorms.data_status not in PROTECTED_STATUSES:
        legacy_south_dorms.is_active = False
    legacy_west_canteen = db.get(Canteen, "canteen-qy-west-food-street")
    if legacy_west_canteen and legacy_west_canteen.data_status not in PROTECTED_STATUSES:
        legacy_west_canteen.is_active = False
    legacy_placeholder = db.get(Location, "qy-canteen-placeholder")
    if legacy_placeholder and legacy_placeholder.data_status not in PROTECTED_STATUSES:
        legacy_placeholder.is_active = False
    legacy_placeholder_canteen = db.get(Canteen, "canteen-qy-canteen-placeholder")
    if legacy_placeholder_canteen and legacy_placeholder_canteen.data_status not in PROTECTED_STATUSES:
        legacy_placeholder_canteen.is_active = False

    for slug, name, _ in CAMPUS_DEFINITIONS:
        path = campus_root / slug / "paths.json"
        if not path.exists():
            continue
        package = json.loads(path.read_text(encoding="utf-8"))
        campus = campus_by_name[name]
        for item in package.get("nodes", []):
            node = db.get(CampusPathNode, item["id"])
            if not node:
                node = CampusPathNode(id=item["id"], campus_id=campus.id, name=item["name"])
                db.add(node)
            node.campus_id = campus.id
            node.location_id = item.get("location_id")
            node.name = item["name"]
            node.latitude = item.get("latitude")
            node.longitude = item.get("longitude")
            node.map_x = item.get("map_x")
            node.map_y = item.get("map_y")
            node.verified = bool(item.get("verified", False))
            node.source_url = item.get("source_url", "")
        db.flush()
        for item in package.get("edges", []):
            edge = db.get(CampusPathEdge, item["id"])
            if not edge:
                edge = CampusPathEdge(
                    id=item["id"], campus_id=campus.id,
                    from_node_id=item["from_node_id"], to_node_id=item["to_node_id"],
                )
                db.add(edge)
            edge.campus_id = campus.id
            edge.from_node_id = item["from_node_id"]
            edge.to_node_id = item["to_node_id"]
            edge.distance_meters = item.get("distance_meters")
            edge.instruction = item.get("instruction", "")
            edge.bidirectional = bool(item.get("bidirectional", True))
            edge.accessible = bool(item.get("accessible", True))
            edge.verified = bool(item.get("verified", False))
            edge.source_url = item.get("source_url", "")

    for slug, name, _ in CAMPUS_DEFINITIONS:
        path = campus_root / slug / "processes.json"
        if not path.exists():
            continue
        for item in json.loads(path.read_text(encoding="utf-8")):
            source = _source(db, item.get("source", {}), 0.8)
            process = db.get(CampusProcess, item["id"])
            if not process:
                process = CampusProcess(id=item["id"], title=item["title"])
                db.add(process)
            process.campus_id = campus_by_name[name].id
            process.source_id = source.id
            process.title = item["title"]
            process.category = item.get("category", "other")
            process.steps = item.get("steps", [])
            process.materials = item.get("materials", [])
            process.contact = item.get("contact", "")
            process.audience = item.get("audience", "")
            process.location = item.get("location", "")
            process.opening_hours = item.get("opening_hours", "")
            process.online_url = item.get("online_url", "")
            process.notes = item.get("notes", "")
            process.verification_status = item.get("verification_status", "needs_verification")
            process.verified_at = _date(item.get("verified_at"))
            process.confidence = float(item.get("confidence", 0))
            process.data_status = item.get("data_status", "needs_verification")
            process.is_active = bool(item.get("is_active", True))

    knowledge_root = Path(settings.data_root) / "knowledge"
    for path in knowledge_root.glob("*.json") if knowledge_root.exists() else []:
        for item in json.loads(path.read_text(encoding="utf-8")):
            source = _source(db, item.get("source", {}), float(item.get("confidence", 0)))
            document = db.get(KnowledgeDocument, item["id"])
            if not document:
                document = KnowledgeDocument(id=item["id"], title=item["title"], content=item["content"])
                db.add(document)
            campus_name = item.get("campus")
            document.campus_id = campus_by_name[campus_name].id if campus_name else None
            document.source_id = source.id
            document.title = item["title"]
            document.content = item["content"]
            document.publisher = item.get("publisher", source.publisher)
            document.url = item.get("url", source.url)
            document.published_at = _date(item.get("published_at"))
            document.fetched_at = _date(item.get("fetched_at"))
            document.valid_until = _date(item.get("valid_until"))
            document.is_official = bool(item.get("is_official", source.is_official))
            document.data_status = item.get("data_status", "needs_verification")
            document.is_active = bool(item.get("is_active", True))

    if settings.admin_bootstrap_email and settings.admin_bootstrap_password:
        email = settings.admin_bootstrap_email.strip().lower()
        if not db.scalar(select(User).where(User.email == email)):
            default_campus = campus_by_name["广州校本部"]
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
