from fastapi.testclient import TestClient


def _task(title: str) -> dict:
    return {
        "title": title,
        "deadline": "2099-09-03T17:00:00+08:00",
        "task_type": "assignment",
        "confirmed": True,
    }


def test_seed_contains_three_distinct_campuses(client: TestClient):
    campuses = client.get("/api/campuses").json()
    assert len(campuses) == 3
    assert len({item["id"] for item in campuses}) == 3
    assert {item["slug"] for item in campuses} == {"guangzhou", "zhaoqing", "qingyuan"}


def test_location_filters_do_not_mix_campuses(client: TestClient):
    campuses = client.get("/api/campuses").json()
    for campus in campuses:
        rows = client.get("/api/locations", params={"campus_id": campus["id"]}).json()
        assert rows
        assert {row["campus_id"] for row in rows} == {campus["id"]}


def test_canteens_explicitly_disclaim_realtime_menu(client: TestClient, campus_id: str):
    rows = client.get("/api/canteens", params={"campus_id": campus_id}).json()
    assert rows
    assert all(item["today_menu_available"] is False for item in rows)
    assert all("今日" in item["today_menu_message"] for item in rows)
    search = client.get("/api/food-search", params={"q": "米饭", "campus_id": campus_id})
    assert search.status_code == 200
    assert search.json()["today_menu_available"] is False


def test_agent_uses_persistent_task_tool_and_conversation(client: TestClient, register_user):
    register_user("agent")
    client.post("/api/tasks", json=_task("Agent 可见任务"))
    first = client.post("/api/agent/chat", json={"message": "我的任务还有哪些？"})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["intent"] == "task_management"
    assert body["degraded"] is True
    assert body["tool_results"][0]["tool"] == "task_list"
    assert any(row["title"] == "Agent 可见任务" for row in body["tool_results"][0]["data"])

    conversation_id = body["conversation_id"]
    second = client.post(
        "/api/agent/chat",
        json={"message": "你好", "conversation_id": conversation_id},
    )
    assert second.status_code == 200
    detail = client.get(f"/api/agent/conversations/{conversation_id}")
    assert detail.status_code == 200
    assert len(detail.json()["messages"]) == 4


def test_notification_agent_requires_confirmation(client: TestClient, register_user):
    register_user("notification-agent")
    response = client.post(
        "/api/agent/chat",
        json={"message": "班群通知：9月3日17:00前提交课程报告，请生成任务"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "notification_to_tasks"
    assert payload["requires_confirmation"] is True
    assert payload["tool_results"][0]["tool"] == "notification_parser"


def test_location_feedback_is_authenticated_and_persisted(client: TestClient, register_user, campus_id: str):
    client.cookies.clear()
    assert client.post(
        "/api/location-feedback",
        json={"campus_id": campus_id, "content": "这个地点信息需要更新"},
    ).status_code == 401
    register_user("feedback")
    response = client.post(
        "/api/location-feedback",
        json={"campus_id": campus_id, "content": "这个地点信息需要更新"},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
