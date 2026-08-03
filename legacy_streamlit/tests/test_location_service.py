from datetime import datetime
import json

from core.models import CampusLocation
from core.time_service import CHINA_TZ
from services.location_service import LocationService


def location(location_id: str, name: str, campus: str, category: str = "other", **changes):
    payload = {
        "id": location_id,
        "name": name,
        "aliases": changes.pop("aliases", []),
        "campus": campus,
        "category": category,
        "map_x": 0.5,
        "map_y": 0.5,
        "data_status": "verified",
        "verified_at": "2026-08-01T10:00:00+08:00",
        "confidence": 0.9,
    }
    payload.update(changes)
    return CampusLocation.from_dict(payload)


def test_campus_isolation_alias_search_and_no_fabricated_today_menu(tmp_path):
    service = LocationService(tmp_path / "locations.db", tmp_path / "none", auto_seed=False)
    service.save_location(location("gz-canteen", "广州饭堂", "广州校本部", "canteen", aliases=["广饭"]))
    service.save_location(location("zq-canteen", "肇庆饭堂", "肇庆校区", "canteen"))

    results = service.search_locations("广饭", campus="广州校本部")
    assert [item.id for item in results] == ["gz-canteen"]
    assert [item.id for item in service.list_canteens("肇庆校区")] == ["zq-canteen"]
    assert all(item.campus == "广州校本部" for item in service.search_locations(campus="广州校本部"))
    assert [item.id for item in service.find_locations_by_category("canteen", "广州校本部")] == ["gz-canteen"]

    service.deactivate_location("gz-canteen")
    assert service.search_locations(campus="广州校本部") == []
    reactivated = service.get_location("gz-canteen", include_inactive=True)
    reactivated.is_active = True
    service.save_location(reactivated)

    details = service.get_canteen_details("gz-canteen")
    assert details["today_menu_available"] is False
    assert details["today_menu"] == []
    assert "没有可靠" in details["today_menu_message"]


def test_freshness_navigation_versioning_and_rollback(tmp_path):
    service = LocationService(tmp_path / "locations.db", tmp_path / "none", auto_seed=False)
    item = location("library", "图书馆", "清远校区", address="校内")
    service.save_location(item)
    freshness = service.calculate_freshness(
        item,
        datetime(2026, 8, 2, 12, tzinfo=CHINA_TZ),
    )
    assert freshness.status == "current"
    assert service.build_navigation_link(item).startswith("https://www.amap.com/search")

    item.description = "新描述"
    service.save_location(item, changed_by="test")
    assert service.get_location("library").description == "新描述"
    restored = service.rollback_location("library", changed_by="test")
    assert restored.description == ""
    assert service.get_location("library").description == ""


def test_import_json_is_campus_scoped_and_versioned(tmp_path):
    service = LocationService(tmp_path / "locations.db", tmp_path / "none", auto_seed=False)
    payload = {
        "locations": [
            {
                "id": "zq-gate",
                "name": "校门",
                "aliases": ["大门"],
                "campus": "肇庆",
                "category": "campus_gate",
                "data_status": "needs_verification",
            }
        ]
    }
    result = service.import_data("locations.json", json.dumps(payload, ensure_ascii=False).encode())
    assert result == {"inserted": 1, "updated": 0}
    assert service.get_location("zq-gate").campus == "肇庆校区"
    assert service.search_locations(campus="广州校本部") == []


def test_nearby_schematic_distance_and_campus_map_upload(tmp_path):
    service = LocationService(tmp_path / "locations.db", tmp_path / "none", auto_seed=False)
    service.save_location(location("origin", "起点", "广州校本部", map_x=0.1, map_y=0.1))
    service.save_location(location("near", "近点", "广州校本部", map_x=0.2, map_y=0.1))
    nearby = service.find_nearby_locations("广州校本部", map_x=0.1, map_y=0.1)
    assert nearby[0]["location"]["id"] == "origin"
    assert nearby[1]["location"]["id"] == "near"
    assert nearby[1]["precision"] == "schematic"

    record = service.save_campus_map(
        "广州校本部",
        "campus.png",
        b"not-a-real-image-but-storage-is-tested",
        upload_dir=tmp_path / "maps",
    )
    assert service.list_campus_maps("广州校本部")[0]["id"] == record["id"]
