from __future__ import annotations

from collections import Counter
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
import sys


# Make the documented root command work without requiring an editable install:
# python -m backend.app.cli.audit_locations
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models.entities import Campus, Location  # noqa: E402


MAX_CAMPUS_DISTANCE_KM = 5.0


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(value))


def audit() -> tuple[list[dict], Counter]:
    with SessionLocal() as db:
        campuses = {row.id: row for row in db.scalars(select(Campus))}
        locations = list(db.scalars(select(Location).where(Location.is_active.is_(True))))

    anchors = {
        item.campus_id: (float(item.latitude), float(item.longitude))
        for item in locations
        if item.sub_category == "campus_anchor" and item.latitude is not None and item.longitude is not None
    }
    coordinate_counts = Counter(
        (round(float(item.latitude), 6), round(float(item.longitude), 6))
        for item in locations if item.latitude is not None and item.longitude is not None
    )
    results: list[dict] = []
    for item in locations:
        status = "PASS"
        reasons: list[str] = []
        has_lat, has_lon = item.latitude is not None, item.longitude is not None
        if has_lat != has_lon:
            status, reasons = "INVALID", ["latitude/longitude must be provided together"]
        elif not has_lat:
            status, reasons = "NEEDS_REVIEW", ["no trusted coordinate"]
        else:
            point = (float(item.latitude), float(item.longitude))
            if not (-90 <= point[0] <= 90 and -180 <= point[1] <= 180):
                status, reasons = "INVALID", ["coordinate outside geographic bounds"]
            if item.coordinate_accuracy not in {"exact", "approximate", "area_only"}:
                status, reasons = "INVALID", ["coordinate accuracy is missing"]
            if item.coordinate_accuracy == "exact" and (not item.coordinate_source or not item.coordinate_verified_at):
                status, reasons = "INVALID", ["exact coordinate lacks source or verification timestamp"]
            if item.coordinate_accuracy == "area_only" and status == "PASS":
                status, reasons = "NEEDS_REVIEW", ["area-only point cannot be used for routing"]
            center = anchors.get(item.campus_id)
            if center and item.sub_category != "campus_anchor":
                distance = distance_km(center, point)
                if distance > MAX_CAMPUS_DISTANCE_KM:
                    status, reasons = "INVALID", [f"{distance:.2f} km from campus anchor"]
            elif not center and status == "PASS":
                status, reasons = "SUSPICIOUS", ["campus has no verified anchor"]
            key = (round(point[0], 6), round(point[1], 6))
            if coordinate_counts[key] > 1 and status == "PASS":
                status, reasons = "SUSPICIOUS", ["coordinate is duplicated by another location"]
        if (item.map_x is not None or item.map_y is not None) and not has_lat:
            status, reasons = "INVALID", ["schematic coordinate exists without trusted geographic coordinate"]
        results.append({
            "id": item.id,
            "campus": campuses.get(item.campus_id).name if item.campus_id in campuses else item.campus_id,
            "name": item.name,
            "status": status,
            "reason": "; ".join(reasons) or "coordinate has source, precision and verification metadata",
        })
    return results, Counter(item["status"] for item in results)


def main() -> int:
    results, counts = audit()
    for item in results:
        print(f"{item['status']:<12} {item['campus']} / {item['name']} [{item['id']}] - {item['reason']}")
    print("\nSummary: " + ", ".join(f"{name}={counts[name]}" for name in ("PASS", "SUSPICIOUS", "INVALID", "NEEDS_REVIEW")))
    return 1 if counts["INVALID"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
