from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agents.tool_registry import TOOL_NAMES, ToolRegistry
from app.agents.tools import AgentToolbox
from app.core.config import Settings
from app.core.database import SessionLocal
from app.models.entities import ToolExecution, UploadedDocument, User
from app.services.map_service import MapService


def test_every_required_agent_tool_is_registered(client: TestClient, register_user):
    account = register_user("registry")
    with SessionLocal() as db:
        user = db.get(User, account["user"]["id"])
        registry = ToolRegistry()
        registry.register_toolbox(AgentToolbox(db, user, user.campus_id))
        assert registry.complete()
        assert set(registry.names) == set(TOOL_NAMES)


def test_preferred_address_and_location_persist(client: TestClient, register_user, mock_llm):
    account = register_user("preferences")
    campus_id = account["user"]["campus_id"]
    location_id = client.get("/api/locations", params={"campus_id": campus_id}).json()[0]["id"]
    response = client.patch("/api/auth/me", json={
        "preferred_name": "小林", "address_style": "师弟", "preferred_location_id": location_id,
    })
    assert response.status_code == 200, response.text
    assert response.json()["preferred_name"] == "小林"
    assert response.json()["address_style"] == "师弟"
    assert response.json()["preferred_location_id"] == location_id
    chat = client.post("/api/agent/chat", json={"message": "你好"})
    assert chat.status_code == 200
    assert "用户偏好称呼：小林师弟" in mock_llm.calls[-1][0]["content"]


def test_process_steps_require_confirmation_and_persist_as_tasks(client: TestClient, register_user):
    account = register_user("process-task")
    rows = client.get("/api/processes", params={"campus_id": account["user"]["campus_id"]}).json()
    assert rows
    process_id = rows[0]["id"]
    assert client.post(f"/api/processes/{process_id}/create-tasks", json={"confirmed": False}).status_code == 422
    response = client.post(f"/api/processes/{process_id}/create-tasks", json={"confirmed": True})
    assert response.status_code == 201, response.text
    created = response.json()
    assert len(created) >= 2
    stored_ids = {row["id"] for row in client.get("/api/tasks").json()}
    assert {row["id"] for row in created}.issubset(stored_ids)


def test_knowledge_admin_crud_and_low_match_suppression(client: TestClient, login_admin, campus_id: str):
    login_admin()
    payload = {
        "campus_id": campus_id,
        "title": "测试专用校园服务资料",
        "content": "校园网络测试资料仅用于自动测试。",
        "publisher": "测试发布方",
        "is_official": False,
        "data_status": "needs_verification",
    }
    created = client.post("/api/admin/knowledge", json=payload)
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]
    found = client.get("/api/knowledge", params={"q": "校园网络测试资料", "campus_id": campus_id})
    assert any(row["id"] == document_id for row in found.json())
    assert client.get("/api/knowledge", params={"q": "完全无关的火星词汇", "campus_id": campus_id}).json() == []
    assert client.delete(f"/api/admin/knowledge/{document_id}").status_code == 204


def test_tool_execution_pipeline_is_remembered(client: TestClient, register_user):
    register_user("tool-memory")
    conversation_id = client.post("/api/agent/chat", json={"message": "我的任务有哪些？"}).json()["conversation_id"]
    with SessionLocal() as db:
        rows = list(db.scalars(select(ToolExecution).where(ToolExecution.conversation_id == conversation_id)))
        assert rows
        assert rows[0].tool_name == "list_tasks"
        assert rows[0].verification["pipeline"] == [
            "observe", "reason", "plan", "execute", "observe_tool", "replan", "verify", "respond",
        ]
        assert rows[0].verification["intent"] == "task_management"
        assert rows[0].verification["plan"][0]["tool"] == "list_tasks"
        assert rows[0].verification["tools_called"] == ["list_tasks"]
        assert rows[0].verification["tool_success"] == {"list_tasks": True}


def test_upload_records_only_metadata_not_document_text(client: TestClient, register_user):
    account = register_user("upload-meta")
    text = "测试通知\n截止时间：2099年10月1日"
    response = client.post("/api/notifications/parse", files={"file": ("notice.txt", text, "text/plain")})
    assert response.status_code == 200
    with SessionLocal() as db:
        row = db.scalar(select(UploadedDocument).where(UploadedDocument.user_id == account["user"]["id"]))
        assert row is not None
        assert row.original_filename == "notice.txt"
        assert len(row.content_hash) == 64
        assert not hasattr(row, "content")


def test_map_status_is_honest_without_keys(client: TestClient):
    response = client.get("/api/map/status")
    assert response.status_code == 200
    assert response.json()["provider"] == "amap"
    assert response.json()["webservice_configured"] is False
    assert response.json()["security_proxy_configured"] is False


def test_amap_route_parser_uses_mocked_provider(monkeypatch):
    service = MapService(Settings(amap_webservice_key="mock-map-key", environment="test"))

    async def fake_request(_self, _path: str, _params: dict):
        return {"status": "1", "route": {"paths": [{
            "distance": "800", "duration": "600",
            "steps": [{"instruction": "向北步行", "road": "测试路", "distance": "800", "duration": "600", "polyline": "113.1,23.1;113.2,23.2"}],
        }]}}

    monkeypatch.setattr(MapService, "_request", fake_request)
    result = asyncio.run(service.walking_route(113.1, 23.1, 113.2, 23.2))
    assert result["distance_meters"] == 800
    assert result["duration_seconds"] == 600
    assert result["polyline"] == [[113.1, 23.1], [113.2, 23.2]]


def test_admin_exact_coordinate_requires_traceable_evidence(client: TestClient, login_admin, campus_id: str):
    login_admin()
    missing = client.post("/api/admin/locations", json={
        "id": "test-coordinate-evidence",
        "campus_id": campus_id,
        "name": "测试坐标点",
        "category": "other",
        "latitude": 23.2,
        "longitude": 113.38,
        "coordinate_accuracy": "exact",
        "coordinate_source": "AMap POI",
    })
    assert missing.status_code == 422
    created = client.post("/api/admin/locations", json={
        "id": "test-coordinate-evidence",
        "campus_id": campus_id,
        "name": "测试坐标点",
        "category": "other",
        "latitude": 23.2,
        "longitude": 113.38,
        "coordinate_accuracy": "exact",
        "coordinate_source": "AMap POI",
        "amap_poi_id": "TEST-POI",
        "evidence": "高德 POI 名称和卫星图复核",
        "verification_note": "自动测试",
    })
    assert created.status_code == 201, created.text
    assert created.json()["coordinate_accuracy"] == "exact"
    assert created.json()["coordinate_source"] == "AMap POI"


def test_agent_core_intents_expose_plan_and_tool_outcomes(client: TestClient, register_user, monkeypatch):
    account = register_user("agent-core-matrix")
    campus_id = account["user"]["campus_id"]

    class FakeMap:
        async def walking_route(self, *_args):
            return {"provider": "amap", "distance_meters": 360, "duration_seconds": 300, "steps": [], "polyline": [[113.381176, 23.202708], [113.383625, 23.202675]]}

    monkeypatch.setattr(MapService, "configured", classmethod(lambda cls: FakeMap()))
    cases = [
        ("大一高数跟不上怎么办？", "learning_guidance", [], []),
        ("快递站在哪里？", "campus_location_search", ["search_campus_locations"], ["search_campus_locations"]),
        ("饭堂有什么吃？", "food_search", ["search_food"], ["search_food"]),
        ("这是通知：请提交课程报告", "notification_to_tasks", ["extract_tasks_from_notification", "validate_extracted_tasks"], ["extract_tasks_from_notification", "validate_extracted_tasks"]),
        ("我的任务有哪些？", "task_management", ["list_tasks"], ["list_tasks"]),
        ("校园网故障怎么报修？", "campus_process", ["search_campus_processes"], ["search_campus_processes"]),
        (
            "从北教去北苑饭堂怎么走？",
            "campus_navigation",
            ["search_campus_locations", "list_canteens", "calculate_walking_route"],
            ["search_campus_locations", "list_canteens", "calculate_walking_route"],
        ),
    ]
    for message, intent, plan, tools in cases:
        response = client.post("/api/agent/chat", json={"message": message, "campus_id": campus_id})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["intent"] == intent
        assert body["plan"] == plan
        assert body["tools_called"] == tools
        assert all(body["tool_success"].get(tool) is True for tool in tools)
