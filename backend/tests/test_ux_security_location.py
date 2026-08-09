from __future__ import annotations

import json
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.entities import Conversation, Location, Message, User, utcnow
from app.services.map_service import MapService, MapServiceError


def _task(title: str = "隔离任务") -> dict:
    return {
        "title": title,
        "description": "仅当前用户可见",
        "deadline": "2099-09-03T17:00:00+08:00",
        "location": "",
        "course": "测试课程",
        "task_type": "assignment",
        "materials": [],
        "submission_target": "",
        "submission_method": "",
        "file_naming": "",
        "source_text": "测试",
        "confirmed": True,
        "reminder_minutes": [],
    }


def test_password_and_cookie_security_are_provable(client: TestClient, register_user):
    account = register_user("security-proof")
    with SessionLocal() as db:
        row = db.scalar(select(User).where(User.email == account["email"]))
        assert row is not None
        assert row.password_hash.startswith("$argon2id$")
        assert account["password"] not in row.password_hash

    response = client.post("/api/auth/login", json={"email": account["email"], "password": account["password"]})
    assert response.status_code == 200
    assert "token" not in response.text.lower()
    cookies = response.headers.get_list("set-cookie")
    assert any("access_token=" in value and "HttpOnly" in value and "SameSite=lax" in value for value in cookies)
    assert any("refresh_token=" in value and "HttpOnly" in value and "Path=/api/auth" in value for value in cookies)


def test_cross_site_mutation_is_rejected(client: TestClient, register_user):
    register_user("csrf")
    response = client.post(
        "/api/notes",
        json={"title": "不应创建", "content": "恶意跨站请求", "confirmed": True},
        headers={"Origin": "https://attacker.invalid", "Sec-Fetch-Site": "cross-site"},
    )
    assert response.status_code == 403
    assert client.get("/api/notes").json() == []


def test_all_task_actions_and_ics_are_owner_scoped(client: TestClient, register_user):
    owner = register_user("task-owner")
    task_id = client.post("/api/tasks", json=_task()).json()["id"]
    other = register_user("task-other")
    assert owner["user"]["id"] != other["user"]["id"]
    assert client.get(f"/api/tasks/{task_id}").status_code == 404
    assert client.patch(f"/api/tasks/{task_id}", json={"title": "越权", "confirmed": True}).status_code == 404
    assert client.post(f"/api/tasks/{task_id}/complete?confirmed=true").status_code == 404
    assert client.post(f"/api/tasks/{task_id}/reopen?confirmed=true").status_code == 404
    assert client.delete(f"/api/tasks/{task_id}?confirmed=true").status_code == 404
    assert client.get(f"/api/tasks/export/ics?task_ids={task_id}").status_code == 404


def test_conversation_note_reminder_links_are_owner_scoped(client: TestClient, register_user):
    owner = register_user("resource-owner")
    conversation_id = client.post("/api/agent/conversations").json()["id"]
    note_id = client.post(
        "/api/notes", json={"title": "私有便签", "content": "A 的内容", "confirmed": True}
    ).json()["id"]
    task_id = client.post("/api/tasks", json=_task("A 的任务")).json()["id"]
    reminder_id = client.post(
        "/api/reminders",
        json={
            "title": "A 的提醒",
            "body": "私有",
            "remind_at": "2099-09-02T09:00:00+08:00",
            "task_id": task_id,
            "confirmed": True,
        },
    ).json()["id"]

    other = register_user("resource-other")
    assert owner["user"]["id"] != other["user"]["id"]
    assert client.get(f"/api/agent/conversations/{conversation_id}").status_code == 404
    assert client.delete(f"/api/agent/conversations/{conversation_id}").status_code == 404
    assert client.post(
        "/api/agent/chat",
        json={"message": "继续 A 的对话", "conversation_id": conversation_id},
    ).status_code == 404
    assert client.get(f"/api/notes/{note_id}").status_code == 404
    assert client.patch(f"/api/notes/{note_id}", json={"title": "越权", "confirmed": True}).status_code == 404
    assert client.delete(f"/api/notes/{note_id}?confirmed=true").status_code == 404
    assert client.get(f"/api/reminders/{reminder_id}").status_code == 404
    assert client.patch(
        f"/api/reminders/{reminder_id}", json={"title": "越权", "confirmed": True}
    ).status_code == 404
    assert client.delete(f"/api/reminders/{reminder_id}?confirmed=true").status_code == 404
    assert client.post(
        "/api/reminders",
        json={
            "title": "越权关联",
            "remind_at": "2099-09-02T10:00:00+08:00",
            "task_id": task_id,
            "note_id": note_id,
            "confirmed": True,
        },
    ).status_code == 404


def _verified_location(campus_id: str) -> Location:
    stamp = utcnow()
    return Location(
        id=f"test-route-{uuid4().hex[:12]}",
        campus_id=campus_id,
        name="测试核验教学楼",
        aliases=["测试目的地"],
        category="teaching_building",
        latitude=23.716633,
        longitude=113.085429,
        coordinate_accuracy="exact",
        coordinate_verified_at=stamp,
        coordinate_verified_by="automated-fixture",
        verification_status="verified",
        verified_at=stamp,
        data_status="verified",
        is_active=True,
    )


class _RouteService:
    async def walking_route(self, *_coordinates: float) -> dict:
        return {
            "provider": "amap-test-fixture",
            "distance_meters": 680,
            "duration_seconds": 540,
            "steps": [{"instruction": "沿测试道路步行", "distance_meters": 680}],
            "polyline": [[113.084, 23.715], [113.085429, 23.716633]],
        }


def test_route_from_current_validates_accuracy_and_verified_destination(
    client: TestClient, register_user, monkeypatch
):
    account = register_user("route")
    with SessionLocal() as db:
        destination = _verified_location(account["user"]["campus_id"])
        db.add(destination)
        db.commit()
        destination_id = destination.id
    monkeypatch.setattr(MapService, "configured", classmethod(lambda cls: _RouteService()))

    payload = {
        "origin": {"latitude": 23.715, "longitude": 113.084, "accuracy": 18, "captured_at": "2026-08-09T12:00:00+08:00"},
        "destination_location_id": destination_id,
        "mode": "walking",
    }
    response = client.post("/api/map/route-from-current", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["distance_meters"] == 680
    assert body["duration_seconds"] == 540
    assert body["accuracy_status"] == "accurate"
    assert body["off_campus"] is False
    assert "不会保存" in body["privacy"]

    payload["origin"]["accuracy"] = 75
    assert client.post("/api/map/route-from-current", json=payload).json()["accuracy_status"] == "approximate"
    payload["origin"]["accuracy"] = 150
    assert client.post("/api/map/route-from-current", json=payload).status_code == 422

    with SessionLocal() as db:
        unverified = Location(
            id=f"test-unverified-{uuid4().hex[:10]}",
            campus_id=account["user"]["campus_id"],
            name="未核验地点",
            category="other",
            latitude=23.71,
            longitude=113.08,
            coordinate_accuracy="approximate",
            data_status="needs_verification",
            is_active=True,
        )
        db.add(unverified)
        db.commit()
        payload["destination_location_id"] = unverified.id
    payload["origin"]["accuracy"] = 20
    assert client.post("/api/map/route-from-current", json=payload).status_code == 422


def test_route_from_current_marks_off_campus_and_hides_provider_failure(
    client: TestClient, register_user, monkeypatch
):
    account = register_user("off-campus")
    with SessionLocal() as db:
        destination = _verified_location(account["user"]["campus_id"])
        db.add(destination)
        db.commit()
        destination_id = destination.id
    monkeypatch.setattr(MapService, "configured", classmethod(lambda cls: _RouteService()))
    payload = {
        "origin": {"latitude": 22.5431, "longitude": 114.0579, "accuracy": 20},
        "destination_location_id": destination_id,
    }
    assert client.post("/api/map/route-from-current", json=payload).json()["off_campus"] is True

    class FailingRouteService:
        async def walking_route(self, *_coordinates: float) -> dict:
            raise MapServiceError("地图服务暂时不可用", 502)

    monkeypatch.setattr(MapService, "configured", classmethod(lambda cls: FailingRouteService()))
    response = client.post("/api/map/route-from-current", json=payload)
    assert response.status_code == 502
    assert response.json()["detail"] == "地图服务暂时不可用"


def test_chat_navigation_resumes_without_persisting_gps(
    client: TestClient, register_user, monkeypatch
):
    account = register_user("chat-route")
    with SessionLocal() as db:
        destination = _verified_location(account["user"]["campus_id"])
        db.add(destination)
        db.commit()
        destination_name = destination.name
    monkeypatch.setattr(MapService, "configured", classmethod(lambda cls: _RouteService()))

    first = client.post("/api/agent/chat", json={"message": f"{destination_name}怎么走？"})
    assert first.status_code == 200
    assert first.json()["intent"] == "campus_navigation"
    assert first.json()["map_action"]["type"] == "request_location"
    conversation_id = first.json()["conversation_id"]

    resumed = client.post(
        "/api/agent/chat",
        json={
            "message": f"{destination_name}怎么走？",
            "conversation_id": conversation_id,
            "location_context": {
                "latitude": 23.715,
                "longitude": 113.084,
                "accuracy": 18,
                "captured_at": "2026-08-09T12:00:00+08:00",
            },
            "resume_navigation": True,
        },
    )
    assert resumed.status_code == 200
    body = resumed.json()
    assert body["route"]["distance_meters"] == 680
    assert body["map_action"]["type"] == "route"
    assert "680 米" in body["answer"]

    with SessionLocal() as db:
        conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id))
        assert conversation is not None
        rows = list(db.scalars(select(Message).where(Message.conversation_id == conversation_id)))
        persisted = json.dumps(
            [{"content": row.content, "tool_results": row.tool_results} for row in rows], ensure_ascii=False
        )
    assert "23.715" not in persisted
    assert "113.084" not in persisted
    assert "captured_at" not in persisted
