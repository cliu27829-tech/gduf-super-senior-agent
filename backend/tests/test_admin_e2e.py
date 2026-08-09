from uuid import uuid4

from fastapi.testclient import TestClient


def test_normal_user_cannot_access_admin(client: TestClient, register_user):
    register_user("ordinary")
    assert client.get("/api/admin/dashboard").status_code == 403
    assert client.get("/api/admin/users").status_code == 403


def test_admin_dashboard_and_verified_evidence_rule(client: TestClient, login_admin, campus_id: str):
    login_admin()
    dashboard = client.get("/api/admin/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["users"] >= 1

    payload = {
        "campus_id": campus_id,
        "name": f"核验测试地点-{uuid4().hex[:6]}",
        "category": "service",
        "verification_status": "verified",
        "confidence": 0.95,
    }
    rejected = client.post("/api/admin/locations", json=payload)
    assert rejected.status_code == 422
    accepted = client.post(
        "/api/admin/locations",
        json={**payload, "evidence": "管理员依据校方现场核验记录 2026-08-03"},
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["verification_status"] == "verified"

    logs = client.get("/api/admin/logs")
    assert logs.status_code == 200
    assert any(item["entity_id"] == accepted.json()["id"] for item in logs.json()["audit"])


def test_feedback_admin_review_flow(client: TestClient, register_user, login_admin, campus_id: str):
    register_user("feedback-flow")
    created = client.post(
        "/api/location-feedback",
        json={"campus_id": campus_id, "content": "现场标识与系统地址不一致"},
    ).json()
    login_admin()
    pending = client.get("/api/admin/feedback", params={"review_status": "pending"})
    assert any(item["id"] == created["id"] for item in pending.json())
    reviewed = client.post(
        f"/api/admin/feedback/{created['id']}/approve",
        json={"note": "已转交数据维护人员复核"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "approved"


def test_task_persists_across_logout_and_login(client: TestClient, register_user):
    user = register_user("persist")
    task = client.post(
        "/api/tasks",
        json={"title": "跨会话保留的任务", "confirmed": True},
    ).json()
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/tasks").status_code == 401
    login = client.post(
        "/api/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )
    assert login.status_code == 200
    assert any(item["id"] == task["id"] for item in client.get("/api/tasks").json())


def test_admin_import_export_json(client: TestClient, login_admin, campus_id: str):
    login_admin()
    content = (
        '{"locations":[{"campus_id":"%s","name":"导入测试地点",'
        '"category":"service","verification_status":"needs_verification"}]}' % campus_id
    ).encode("utf-8")
    imported = client.post(
        "/api/admin/data/import",
        files={"file": ("locations.json", content, "application/json")},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["created"] == 1
    exported = client.get("/api/admin/data/export")
    assert exported.status_code == 200
    assert "导入测试地点" in exported.text


def test_admin_map_and_source_crud(client: TestClient, login_admin, campus_id: str):
    login_admin()
    source_payload = {
        "title": "校方公开信息测试",
        "url": "https://example.edu/source",
        "publisher": "广东金融学院",
        "source_type": "official",
        "confidence": 0.9,
        "is_official": True,
    }
    source = client.post("/api/admin/sources", json=source_payload)
    assert source.status_code == 201, source.text
    source_id = source.json()["id"]
    updated_source = client.patch(
        f"/api/admin/sources/{source_id}",
        json={**source_payload, "title": "更新后的校方公开信息"},
    )
    assert updated_source.status_code == 200
    assert updated_source.json()["title"] == "更新后的校方公开信息"

    map_payload = {
        "campus_id": campus_id,
        "image_url": "https://example.edu/campus-map.png",
        "version": "test-v1",
        "license_note": "仅用于自动测试",
        "is_active": True,
    }
    campus_map = client.post("/api/admin/maps", json=map_payload)
    assert campus_map.status_code == 201, campus_map.text
    map_id = campus_map.json()["id"]
    assert client.patch(
        f"/api/admin/maps/{map_id}",
        json={**map_payload, "version": "test-v2"},
    ).json()["version"] == "test-v2"
    assert client.delete(f"/api/admin/maps/{map_id}").status_code == 204
    assert client.delete(f"/api/admin/sources/{source_id}").status_code == 204
