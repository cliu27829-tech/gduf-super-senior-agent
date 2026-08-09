from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import SessionLocal
from app.agents.tools import AgentToolbox
from app.models.entities import AgentRun, CampusPathEdge, CampusPathNode, Canteen, Location, User, utcnow
from app.services.map_service import MapService


class _RouteService:
    async def walking_route(self, *_coordinates: float) -> dict:
        return {
            "provider": "amap-test-fixture",
            "distance_meters": 420,
            "duration_seconds": 360,
            "steps": [{"instruction": "沿测试道路步行", "distance_meters": 420}],
            "polyline": [[113.084, 23.715], [113.085, 23.716]],
        }


def _destination(campus_id: str) -> Location:
    stamp = utcnow()
    return Location(
        id=f"run-route-{uuid4().hex[:12]}",
        campus_id=campus_id,
        name=f"Run测试楼{uuid4().hex[:5]}",
        aliases=[],
        category="teaching_building",
        latitude=23.716,
        longitude=113.085,
        coordinate_accuracy="exact",
        coordinate_verified_at=stamp,
        coordinate_verified_by="automated-fixture",
        verification_status="verified",
        verified_at=stamp,
        data_status="verified",
        is_active=True,
    )


def test_agent_run_persists_observable_steps(client: TestClient, register_user):
    register_user("agent-run")
    response = client.post("/api/agent/chat", json={"message": "清远校区图书馆在哪里？", "campus": "qingyuan"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["agent_run_id"]
    assert body["agent_status"] == "completed"
    assert any(step["step_type"] == "tool" for step in body["agent_steps"])
    assert any(step["step_type"] == "verify" for step in body["agent_steps"])
    detail = client.get(f"/api/agent/runs/{body['agent_run_id']}")
    assert detail.status_code == 200
    assert detail.json()["conversation_id"] == body["conversation_id"]


def test_agent_run_is_owner_scoped(client: TestClient, register_user):
    register_user("run-owner")
    run_id = client.post("/api/agent/chat", json={"message": "你好"}).json()["agent_run_id"]
    register_user("run-other")
    assert client.get(f"/api/agent/runs/{run_id}").status_code == 404
    assert all(row["id"] != run_id for row in client.get("/api/agent/runs").json())


def test_navigation_resumes_same_run_and_never_persists_gps(
    client: TestClient, register_user, monkeypatch
):
    account = register_user("run-resume")
    with SessionLocal() as db:
        destination = _destination(account["user"]["campus_id"])
        db.add(destination)
        db.commit()
        destination_name = destination.name
    monkeypatch.setattr(MapService, "configured", classmethod(lambda cls: _RouteService()))

    first = client.post("/api/agent/chat", json={"message": f"{destination_name}怎么走？"})
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["agent_status"] == "waiting_for_location"
    run_id = first_body["agent_run_id"]

    resumed = client.post("/api/agent/chat", json={
        "message": f"{destination_name}怎么走？",
        "conversation_id": first_body["conversation_id"],
        "agent_run_id": run_id,
        "resume_navigation": True,
        "location_context": {
            "latitude": 23.715,
            "longitude": 113.084,
            "accuracy": 180,
            "captured_at": "2026-08-09T12:00:00+08:00",
        },
    })
    assert resumed.status_code == 200, resumed.text
    body = resumed.json()
    assert body["agent_run_id"] == run_id
    assert body["agent_status"] == "completed"
    assert body["route"]["distance_meters"] == 420
    assert body["route"]["accuracy_status"] == "approximate"
    with SessionLocal() as db:
        run = db.scalar(select(AgentRun).where(AgentRun.id == run_id))
        persisted = json.dumps({"context": run.context_data, "required_input": run.required_input}, ensure_ascii=False)
    assert "23.715" not in persisted
    assert "113.084" not in persisted
    assert "captured_at" not in persisted


def test_stream_exposes_public_tool_events_not_reasoning(client: TestClient, register_user):
    register_user("run-stream")
    response = client.post("/api/agent/chat/stream", json={"message": "清远校区有多少个学院？"})
    assert response.status_code == 200
    assert "event: plan" in response.text
    assert "event: tool_start" in response.text
    assert "event: tool_end" in response.text
    assert "event: verify" in response.text
    assert "reasoning_content" not in response.text


def test_action_confirmation_closes_owned_run(client: TestClient, register_user):
    register_user("run-action")
    response = client.post("/api/agent/chat", json={"message": "明天下午3点提醒我复习高数"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["agent_status"] == "waiting_for_confirmation"
    action = next(item for item in body["actions"] if item["type"] == "reminder")
    rejected = client.post(
        f"/api/agent/runs/{body['agent_run_id']}/confirm",
        json={"action_id": "not-this-run"},
    )
    assert rejected.status_code == 409
    saved = client.post(f"/api{action['api_path']}", json=action["payload"])
    assert saved.status_code == 201, saved.text
    confirmed = client.post(f"/api/agent/runs/{body['agent_run_id']}/confirm", json={"action_id": action["id"]})
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "completed"


def test_notification_agent_uses_extracted_result_for_validation_and_action(client: TestClient, register_user):
    register_user("run-notice")
    response = client.post("/api/agent/chat", json={
        "message": "请解析通知并生成任务：请各班同学于2099年9月3日下午5点前提交课程报告，文件命名为学号+姓名，发送给班长。"
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["intent"] == "notification_to_tasks"
    assert body["agent_status"] == "waiting_for_confirmation"
    assert body["tool_success"]["extract_tasks_from_notification"] is True
    assert body["tool_success"]["validate_extracted_tasks"] is True
    validation = next(item for item in body["tool_results"] if item["tool"] == "validate_extracted_tasks")
    assert validation["data"]["valid"] is True
    action = next(item for item in body["actions"] if item["type"] == "task")
    saved = client.post(f"/api{action['api_path']}", json=action["payload"])
    assert saved.status_code == 201, saved.text
    assert len(saved.json()) == 1
    assert len(client.get("/api/reminders?status=scheduled").json()) == 2


def test_qingyuan_dorm_and_path_seed_is_deduplicated(client: TestClient):
    del client
    with SessionLocal() as db:
        dorms = list(db.scalars(select(Location).where(
            Location.category == "dormitory", Location.is_active.is_(True), Location.id.like("qy-%")
        )))
        assert {row.id for row in dorms} == {
            *{f"qy-south-dorm-{index}" for index in range(1, 6)},
            *{f"qy-north-dorm-{index}" for index in range(1, 9)},
        }
        assert len({alias for row in dorms for alias in row.aliases}) == sum(len(row.aliases) for row in dorms)
        assert db.scalar(select(CampusPathNode).where(CampusPathNode.id == "qy-node-library")) is not None
        edge = db.scalar(select(CampusPathEdge).where(CampusPathEdge.id == "qy-edge-library-ming"))
        assert edge is not None
        assert edge.verified is False
        qingyuan_campus_id = db.get(Location, "qy-library").campus_id
        qingyuan_canteens = list(db.scalars(select(Canteen).where(
            Canteen.is_active.is_(True), Canteen.campus_id == qingyuan_campus_id
        )))
        assert {row.location_id for row in qingyuan_canteens} == {"qy-north-canteen", "qy-south-canteen"}


def test_multi_stop_route_is_composed_from_verified_segments(
    client: TestClient, register_user, monkeypatch
):
    account = register_user("multi-route")
    monkeypatch.setattr(MapService, "configured", classmethod(lambda cls: _RouteService()))
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.id == account["user"]["id"]))
        rows = [_destination(account["user"]["campus_id"]) for _ in range(3)]
        db.add_all(rows)
        db.commit()
        result = asyncio.run(AgentToolbox(db, user, user.campus_id).calculate_walking_route(
            origin_location_id=rows[0].id,
            waypoint_location_ids=[rows[1].id],
            destination_location_id=rows[2].id,
        ))
    assert result.success is True
    assert result.data["distance_meters"] == 840
    assert result.data["duration_seconds"] == 720
    assert len(result.data["segments"]) == 2
    assert result.verification["multi_stop"] is True
