"""Campus location, canteen, freshness, feedback, and admin operations."""

from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime
import io
import json
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, urlencode
import uuid

from core.database import Database
from core.models import (
    CAMPUSES,
    CanteenInfo,
    CampusLocation,
    FreshnessResult,
    SourceReference,
)
from core.time_service import is_stale, now_china, parse_datetime_value


CAMPUS_ALIASES = {
    "校本部": "广州校本部",
    "本部": "广州校本部",
    "广州": "广州校本部",
    "广州校区": "广州校本部",
    "广州校本部": "广州校本部",
    "肇庆": "肇庆校区",
    "肇庆校区": "肇庆校区",
    "清远": "清远校区",
    "清远校区": "清远校区",
}

DEFAULT_FRESHNESS_THRESHOLDS = {
    "daily_menu": 1,
    "operating_status": 7,
    "food_stall": 30,
    "opening_hours": 90,
    "fixed_location": 180,
}


def normalize_campus(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    normalized = CAMPUS_ALIASES.get(str(value).strip())
    if not normalized:
        raise ValueError(f"不支持的校区：{value}")
    return normalized


class LocationService:
    def __init__(
        self,
        db_path: str | Path | None = None,
        data_root: str | Path = "data/campuses",
        auto_seed: bool = True,
        freshness_thresholds: dict[str, int] | None = None,
    ):
        self.database = Database(db_path)
        self.data_root = Path(data_root)
        self.freshness_thresholds = {
            **DEFAULT_FRESHNESS_THRESHOLDS,
            **(freshness_thresholds or {}),
        }
        if auto_seed:
            self.seed_from_files()

    @staticmethod
    def _loads(value: str | None, default: Any) -> Any:
        if not value:
            return default
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return default

    def _row_to_location(self, row: dict[str, Any]) -> CampusLocation:
        payload = dict(row)
        payload["aliases"] = self._loads(payload.pop("aliases_json", "[]"), [])
        payload["services"] = self._loads(payload.pop("services_json", "[]"), [])
        payload["payment_methods"] = self._loads(payload.pop("payment_methods_json", "[]"), [])
        payload["source_references"] = self._loads(
            payload.pop("source_references_json", "[]"), []
        )
        payload["is_active"] = bool(payload.get("is_active"))
        return CampusLocation.from_dict(payload)

    def _row_to_stall(self, row: dict[str, Any]) -> CanteenInfo:
        payload = dict(row)
        payload["common_items"] = self._loads(payload.pop("common_items_json", "[]"), [])
        payload["meal_periods"] = self._loads(payload.pop("meal_periods_json", "[]"), [])
        payload["payment_methods"] = self._loads(payload.pop("payment_methods_json", "[]"), [])
        payload["source_references"] = self._loads(
            payload.pop("source_references_json", "[]"), []
        )
        if payload.get("is_operating") is not None:
            payload["is_operating"] = bool(payload["is_operating"])
        payload["is_active"] = bool(payload.get("is_active"))
        return CanteenInfo.from_dict(payload)

    @staticmethod
    def _source_payload(values: Iterable[SourceReference]) -> str:
        return json.dumps([asdict(item) for item in values], ensure_ascii=False)

    def save_location(
        self,
        location: CampusLocation,
        changed_by: str = "system",
        record_version: bool = True,
    ) -> CampusLocation:
        current = self.database.query_one(
            "SELECT * FROM campus_locations WHERE id = ?", (location.id,)
        )
        timestamp = now_china().isoformat()
        if current and record_version:
            previous = self._row_to_location(current).to_dict()
            self.database.execute(
                "INSERT INTO location_versions(location_id, payload_json, changed_at, changed_by) "
                "VALUES(?, ?, ?, ?)",
                (location.id, json.dumps(previous, ensure_ascii=False), timestamp, changed_by),
            )
        location.created_at = location.created_at or (
            current.get("created_at") if current else timestamp
        )
        location.updated_at = timestamp
        values = (
            location.id,
            location.name,
            json.dumps(location.aliases, ensure_ascii=False),
            location.campus,
            location.category,
            location.sub_category,
            location.description,
            location.building,
            location.floor,
            location.area,
            location.latitude,
            location.longitude,
            location.map_x,
            location.map_y,
            location.address,
            location.opening_hours,
            location.phone,
            json.dumps(location.services, ensure_ascii=False),
            json.dumps(location.payment_methods, ensure_ascii=False),
            location.navigation_url,
            self._source_payload(location.source_references),
            location.verification_method,
            location.verified_at,
            location.valid_from,
            location.valid_until,
            location.freshness_status,
            location.confidence,
            int(location.is_active),
            location.data_status,
            location.created_at,
            location.updated_at,
        )
        placeholders = ",".join("?" for _ in values)
        self.database.execute(
            f"""
            INSERT INTO campus_locations(
                id,name,aliases_json,campus,category,sub_category,description,
                building,floor,area,latitude,longitude,map_x,map_y,address,
                opening_hours,phone,services_json,payment_methods_json,
                navigation_url,source_references_json,verification_method,
                verified_at,valid_from,valid_until,freshness_status,confidence,
                is_active,data_status,created_at,updated_at
            ) VALUES({placeholders})
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, aliases_json=excluded.aliases_json,
                campus=excluded.campus, category=excluded.category,
                sub_category=excluded.sub_category, description=excluded.description,
                building=excluded.building, floor=excluded.floor, area=excluded.area,
                latitude=excluded.latitude, longitude=excluded.longitude,
                map_x=excluded.map_x, map_y=excluded.map_y, address=excluded.address,
                opening_hours=excluded.opening_hours, phone=excluded.phone,
                services_json=excluded.services_json,
                payment_methods_json=excluded.payment_methods_json,
                navigation_url=excluded.navigation_url,
                source_references_json=excluded.source_references_json,
                verification_method=excluded.verification_method,
                verified_at=excluded.verified_at, valid_from=excluded.valid_from,
                valid_until=excluded.valid_until,
                freshness_status=excluded.freshness_status,
                confidence=excluded.confidence, is_active=excluded.is_active,
                data_status=excluded.data_status, updated_at=excluded.updated_at
            """,
            values,
        )
        return location

    def save_food_stall(self, stall: CanteenInfo) -> CanteenInfo:
        if not self.get_location(stall.canteen_id, include_inactive=True):
            raise ValueError(f"饭堂不存在：{stall.canteen_id}")
        timestamp = now_china().isoformat()
        existing = self.database.query_one("SELECT created_at FROM food_stalls WHERE id = ?", (stall.id,))
        stall.created_at = stall.created_at or (existing.get("created_at") if existing else timestamp)
        stall.updated_at = timestamp
        values = (
            stall.id,
            stall.canteen_id,
            stall.name,
            stall.campus,
            stall.floor,
            stall.food_type,
            json.dumps(stall.common_items, ensure_ascii=False),
            stall.price_range,
            json.dumps(stall.meal_periods, ensure_ascii=False),
            stall.opening_hours,
            json.dumps(stall.payment_methods, ensure_ascii=False),
            None if stall.is_operating is None else int(stall.is_operating),
            stall.verified_at,
            self._source_payload(stall.source_references),
            stall.confidence,
            stall.data_status,
            int(stall.is_active),
            stall.created_at,
            stall.updated_at,
        )
        placeholders = ",".join("?" for _ in values)
        self.database.execute(
            f"""
            INSERT INTO food_stalls(
                id,canteen_id,name,campus,floor,food_type,common_items_json,
                price_range,meal_periods_json,opening_hours,payment_methods_json,
                is_operating,verified_at,source_references_json,confidence,
                data_status,is_active,created_at,updated_at
            ) VALUES({placeholders})
            ON CONFLICT(id) DO UPDATE SET
                canteen_id=excluded.canteen_id,name=excluded.name,campus=excluded.campus,
                floor=excluded.floor,food_type=excluded.food_type,
                common_items_json=excluded.common_items_json,
                price_range=excluded.price_range,meal_periods_json=excluded.meal_periods_json,
                opening_hours=excluded.opening_hours,
                payment_methods_json=excluded.payment_methods_json,
                is_operating=excluded.is_operating,verified_at=excluded.verified_at,
                source_references_json=excluded.source_references_json,
                confidence=excluded.confidence,data_status=excluded.data_status,
                is_active=excluded.is_active,updated_at=excluded.updated_at
            """,
            values,
        )
        return stall

    def seed_from_files(self) -> int:
        if not self.data_root.exists():
            return 0
        inserted = 0
        for location_file in self.data_root.glob("*/locations.json"):
            try:
                payload = json.loads(location_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for item in payload:
                if self.get_location(str(item.get("id", "")), include_inactive=True):
                    continue
                self.save_location(CampusLocation.from_dict(item), changed_by="seed")
                inserted += 1
        for canteen_file in self.data_root.glob("*/canteens.json"):
            try:
                payload = json.loads(canteen_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for item in payload:
                if self.database.query_one("SELECT id FROM food_stalls WHERE id = ?", (item.get("id"),)):
                    continue
                self.save_food_stall(CanteenInfo.from_dict(item))
        return inserted

    def get_location(self, location_id: str, include_inactive: bool = False) -> CampusLocation | None:
        sql = "SELECT * FROM campus_locations WHERE id = ?"
        parameters: tuple[Any, ...] = (location_id,)
        if not include_inactive:
            sql += " AND is_active = 1"
        row = self.database.query_one(sql, parameters)
        if not row:
            return None
        location = self._row_to_location(row)
        freshness = self.calculate_freshness(location)
        location.freshness_status = freshness.status
        return location

    def search_locations(
        self,
        query: str = "",
        campus: str | None = None,
        category: str | None = None,
        include_inactive: bool = False,
    ) -> list[CampusLocation]:
        campus = normalize_campus(campus)
        clauses = []
        parameters: list[Any] = []
        if not include_inactive:
            clauses.append("is_active = 1")
        if campus:
            clauses.append("campus = ?")
            parameters.append(campus)
        if category:
            clauses.append("category = ?")
            parameters.append(category)
        sql = "SELECT * FROM campus_locations"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        rows = self.database.query(sql, tuple(parameters))
        needle = (query or "").strip().casefold()
        ranked: list[tuple[int, CampusLocation]] = []
        for row in rows:
            location = self._row_to_location(row)
            freshness = self.calculate_freshness(location)
            location.freshness_status = freshness.status
            if not needle:
                ranked.append((0, location))
                continue
            name = location.name.casefold()
            aliases = [item.casefold() for item in location.aliases]
            haystack = " ".join(
                [name, *aliases, location.description.casefold(), location.address.casefold()]
            )
            if needle == name or needle in aliases:
                score = 100
            elif needle in name:
                score = 80
            elif any(needle in alias for alias in aliases):
                score = 70
            elif needle in haystack:
                score = 30
            else:
                continue
            ranked.append((score, location))
        ranked.sort(key=lambda item: (-item[0], item[1].campus, item[1].name))
        return [item[1] for item in ranked]

    def find_locations_by_category(self, category: str, campus: str | None = None) -> list[CampusLocation]:
        return self.search_locations(campus=campus, category=category)

    def list_canteens(self, campus: str | None = None) -> list[CampusLocation]:
        return self.find_locations_by_category("canteen", campus)

    def list_food_stalls(
        self,
        canteen_id: str | None = None,
        campus: str | None = None,
        query: str = "",
        include_inactive: bool = False,
        verified_only: bool = False,
    ) -> list[CanteenInfo]:
        campus = normalize_campus(campus)
        clauses = []
        parameters: list[Any] = []
        if not include_inactive:
            clauses.append("is_active = 1")
        if canteen_id:
            clauses.append("canteen_id = ?")
            parameters.append(canteen_id)
        if campus:
            clauses.append("campus = ?")
            parameters.append(campus)
        if verified_only:
            clauses.append("verified_at IS NOT NULL")
            clauses.append("data_status NOT IN ('demo_fixture', 'unverified_seed')")
        sql = "SELECT * FROM food_stalls"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        rows = self.database.query(sql, tuple(parameters))
        needle = query.strip().casefold()
        results = []
        for row in rows:
            stall = self._row_to_stall(row)
            haystack = " ".join(
                [stall.name, stall.food_type, *stall.common_items, *stall.payment_methods]
            ).casefold()
            if needle and needle not in haystack:
                continue
            results.append(stall)
        return sorted(results, key=lambda item: (item.campus, item.canteen_id, item.floor, item.name))

    def get_canteen_details(self, canteen_id: str) -> dict[str, Any] | None:
        canteen = self.get_location(canteen_id)
        if not canteen or canteen.category != "canteen":
            return None
        stalls = self.list_food_stalls(canteen_id=canteen_id)
        return {
            "canteen": canteen.to_dict(),
            "food_stalls": [item.to_dict() for item in stalls],
            "today_menu": [],
            "today_menu_available": False,
            "today_menu_message": (
                "目前没有可靠的当日菜单数据，以下是最近一次核验的档口信息。"
                if stalls
                else "目前没有可靠的当日菜单或已核验档口数据。"
            ),
        }

    def calculate_freshness(
        self,
        location: CampusLocation | CanteenInfo,
        reference_time: datetime | None = None,
        data_kind: str | None = None,
    ) -> FreshnessResult:
        if data_kind is None:
            data_kind = "food_stall" if isinstance(location, CanteenInfo) else "fixed_location"
        threshold = int(self.freshness_thresholds.get(data_kind, 180))
        verified = parse_datetime_value(location.verified_at)
        valid_until = parse_datetime_value(getattr(location, "valid_until", None))
        reference = now_china(reference_time)
        if valid_until and valid_until < reference:
            return FreshnessResult("expired", (reference - valid_until).days, threshold, "有效期已结束。")
        if verified is None:
            return FreshnessResult("needs_verification", None, threshold, "没有人工核验日期。")
        age_days = max((reference - verified).days, 0)
        if is_stale(verified, threshold, reference):
            return FreshnessResult(
                "stale",
                age_days,
                threshold,
                f"距上次核验 {age_days} 天，超过 {threshold} 天阈值。",
            )
        return FreshnessResult("current", age_days, threshold, "仍在配置的新鲜度窗口内。")

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        earth_radius_m = 6_371_000
        d_lat = radians(lat2 - lat1)
        d_lon = radians(lon2 - lon1)
        a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
        return 2 * earth_radius_m * asin(sqrt(a))

    def find_nearby_locations(
        self,
        campus: str,
        latitude: float | None = None,
        longitude: float | None = None,
        map_x: float | None = None,
        map_y: float | None = None,
        category: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        locations = self.search_locations(campus=campus, category=category)
        ranked: list[dict[str, Any]] = []
        for location in locations:
            distance = None
            unit = None
            precision = None
            if None not in (latitude, longitude, location.latitude, location.longitude):
                distance = self._haversine(
                    float(latitude), float(longitude), float(location.latitude), float(location.longitude)
                )
                unit = "m"
                precision = "gps"
            elif None not in (map_x, map_y, location.map_x, location.map_y):
                distance = sqrt((float(map_x) - float(location.map_x)) ** 2 + (float(map_y) - float(location.map_y)) ** 2)
                unit = "schematic_unit"
                precision = "schematic"
            if distance is None:
                continue
            ranked.append(
                {
                    "location": location.to_dict(),
                    "distance": round(distance, 2),
                    "unit": unit,
                    "precision": precision,
                }
            )
        ranked.sort(key=lambda item: item["distance"])
        return ranked[:limit]

    def build_navigation_link(self, location: CampusLocation | str) -> str:
        if isinstance(location, str):
            found = self.get_location(location)
            if not found:
                raise ValueError(f"地点不存在：{location}")
            location = found
        if location.navigation_url:
            return location.navigation_url
        if location.latitude is not None and location.longitude is not None:
            parameters = {
                "to": f"{location.longitude},{location.latitude},{location.name}",
                "mode": "walk",
                "callnative": "0",
            }
            return "https://uri.amap.com/navigation?" + urlencode(parameters, safe=",")
        query = " ".join(filter(None, [location.campus, location.address, location.name]))
        return "https://www.amap.com/search?query=" + quote(query, safe="")

    def submit_location_feedback(
        self,
        campus: str,
        feedback: str,
        user_id: str,
        location_id: str | None = None,
    ) -> str:
        normalized_campus = normalize_campus(campus)
        if not feedback.strip():
            raise ValueError("纠错内容不能为空")
        feedback_id = str(uuid.uuid4())
        self.database.execute(
            "INSERT INTO user_location_feedback(id,location_id,campus,user_id,feedback,status,created_at) "
            "VALUES(?,?,?,?,?,'pending',?)",
            (
                feedback_id,
                location_id,
                normalized_campus,
                user_id,
                feedback.strip(),
                now_china().isoformat(),
            ),
        )
        return feedback_id

    def list_feedback(self, status: str = "pending") -> list[dict[str, Any]]:
        return self.database.query(
            "SELECT * FROM user_location_feedback WHERE status = ? ORDER BY created_at DESC",
            (status,),
        )

    def deactivate_location(self, location_id: str, changed_by: str = "admin") -> None:
        location = self.get_location(location_id, include_inactive=True)
        if not location:
            raise ValueError(f"地点不存在：{location_id}")
        location.is_active = False
        self.save_location(location, changed_by=changed_by)

    def deactivate_food_stall(self, stall_id: str) -> None:
        self.database.execute(
            "UPDATE food_stalls SET is_active = 0, updated_at = ? WHERE id = ?",
            (now_china().isoformat(), stall_id),
        )

    def save_campus_map(
        self,
        campus: str,
        original_name: str,
        content: bytes,
        uploaded_by: str = "admin",
        upload_dir: str | Path = "data/uploads/maps",
    ) -> dict[str, Any]:
        normalized_campus = normalize_campus(campus)
        suffix = Path(original_name).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            raise ValueError("校园底图仅支持 PNG、JPG、JPEG 或 WebP")
        if not content:
            raise ValueError("上传的地图为空")
        if len(content) > 10 * 1024 * 1024:
            raise ValueError("校园底图不得超过 10 MB")
        map_id = str(uuid.uuid4())
        destination_dir = Path(upload_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{map_id}{suffix}"
        destination.write_bytes(content)
        timestamp = now_china().isoformat()
        self.database.execute(
            "UPDATE campus_maps SET is_active = 0 WHERE campus = ?",
            (normalized_campus,),
        )
        self.database.execute(
            "INSERT INTO campus_maps(id,campus,original_name,file_path,uploaded_at,uploaded_by,is_active) "
            "VALUES(?,?,?,?,?,?,1)",
            (
                map_id,
                normalized_campus,
                Path(original_name).name,
                str(destination),
                timestamp,
                uploaded_by,
            ),
        )
        return {
            "id": map_id,
            "campus": normalized_campus,
            "original_name": Path(original_name).name,
            "file_path": str(destination),
            "uploaded_at": timestamp,
            "uploaded_by": uploaded_by,
            "is_active": True,
        }

    def list_campus_maps(self, campus: str, active_only: bool = True) -> list[dict[str, Any]]:
        normalized = normalize_campus(campus)
        sql = "SELECT * FROM campus_maps WHERE campus = ?"
        if active_only:
            sql += " AND is_active = 1"
        sql += " ORDER BY uploaded_at DESC"
        return self.database.query(sql, (normalized,))

    def verify_location(self, location_id: str, changed_by: str = "admin") -> CampusLocation:
        location = self.get_location(location_id, include_inactive=True)
        if not location:
            raise ValueError(f"地点不存在：{location_id}")
        location.verified_at = now_china().isoformat()
        location.verification_method = "admin_verified"
        location.data_status = "verified"
        location.confidence = max(location.confidence, 0.85)
        location.freshness_status = "current"
        return self.save_location(location, changed_by=changed_by)

    def list_stale_locations(self, campus: str | None = None) -> list[dict[str, Any]]:
        results = []
        for location in self.search_locations(campus=campus, include_inactive=True):
            freshness = self.calculate_freshness(location)
            if freshness.status != "current":
                results.append({"location": location.to_dict(), "freshness": asdict(freshness)})
        return results

    def rollback_location(self, location_id: str, changed_by: str = "admin") -> CampusLocation:
        version = self.database.query_one(
            "SELECT * FROM location_versions WHERE location_id = ? ORDER BY id DESC LIMIT 1",
            (location_id,),
        )
        if not version:
            raise ValueError("没有可回滚的历史版本")
        restored = CampusLocation.from_dict(json.loads(version["payload_json"]))
        self.save_location(restored, changed_by=f"rollback:{changed_by}", record_version=False)
        self.database.execute("DELETE FROM location_versions WHERE id = ?", (version["id"],))
        return restored

    def import_data(self, filename: str, content: bytes, changed_by: str = "admin") -> dict[str, int]:
        suffix = Path(filename).suffix.lower()
        decoded = content.decode("utf-8-sig")
        if suffix == ".csv":
            items = list(csv.DictReader(io.StringIO(decoded)))
            for item in items:
                for list_field in ("aliases", "services", "payment_methods"):
                    if isinstance(item.get(list_field), str):
                        item[list_field] = [value.strip() for value in item[list_field].split("|") if value.strip()]
        elif suffix in (".json", ".geojson"):
            payload = json.loads(decoded)
            if isinstance(payload, dict) and payload.get("type") == "FeatureCollection":
                items = []
                for feature in payload.get("features", []):
                    item = dict(feature.get("properties") or {})
                    coordinates = (feature.get("geometry") or {}).get("coordinates") or []
                    if len(coordinates) >= 2:
                        item["longitude"], item["latitude"] = coordinates[:2]
                    items.append(item)
            elif isinstance(payload, dict):
                items = payload.get("locations") or [payload]
            else:
                items = payload
        else:
            raise ValueError("仅支持 CSV、JSON 或 GeoJSON")
        inserted = 0
        updated = 0
        for item in items:
            item.setdefault("id", str(uuid.uuid4()))
            item["campus"] = normalize_campus(item.get("campus"))
            item.setdefault("category", "other")
            item.setdefault("aliases", [])
            existing = self.get_location(str(item["id"]), include_inactive=True)
            self.save_location(CampusLocation.from_dict(item), changed_by=changed_by)
            updated += int(existing is not None)
            inserted += int(existing is None)
        return {"inserted": inserted, "updated": updated}


# Module-level convenience functions for tool adapters and simple scripts.
def search_locations(*args: Any, **kwargs: Any) -> list[CampusLocation]:
    return LocationService().search_locations(*args, **kwargs)


def get_location(location_id: str) -> CampusLocation | None:
    return LocationService().get_location(location_id)


def list_canteens(campus: str | None = None) -> list[CampusLocation]:
    return LocationService().list_canteens(campus)


def get_canteen_details(canteen_id: str) -> dict[str, Any] | None:
    return LocationService().get_canteen_details(canteen_id)


def list_food_stalls(*args: Any, **kwargs: Any) -> list[CanteenInfo]:
    return LocationService().list_food_stalls(*args, **kwargs)


def find_nearby_locations(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    return LocationService().find_nearby_locations(*args, **kwargs)


def find_locations_by_category(category: str, campus: str | None = None) -> list[CampusLocation]:
    return LocationService().find_locations_by_category(category, campus)


def build_navigation_link(location: CampusLocation | str) -> str:
    return LocationService().build_navigation_link(location)


def calculate_freshness(location: CampusLocation | CanteenInfo) -> FreshnessResult:
    return LocationService().calculate_freshness(location)


def submit_location_feedback(*args: Any, **kwargs: Any) -> str:
    return LocationService().submit_location_feedback(*args, **kwargs)
