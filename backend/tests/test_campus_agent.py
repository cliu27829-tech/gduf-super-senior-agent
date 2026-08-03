from fastapi.testclient import TestClient

from app.services.agent_service import AgentService


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
    assert "不保证今日" in search.json()["message"] or "不会编造" in search.json()["message"]


def test_public_campus_queries_exclude_demo_fixtures(client: TestClient):
    for campus in client.get("/api/campuses").json():
        locations = client.get("/api/locations", params={"campus_id": campus["id"]}).json()
        canteens = client.get("/api/canteens", params={"campus_id": campus["id"]}).json()
        assert all(item["data_status"] != "demo_fixture" for item in locations)
        assert all(item["data_status"] != "demo_fixture" for item in canteens)
        assert all(stall["data_status"] != "demo_fixture" for item in canteens for stall in item["stalls"])


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


def test_agent_routes_location_food_and_campus_card_process_to_tools(client: TestClient, register_user):
    account = register_user("agent-tools")
    campus_id = account["user"]["campus_id"]

    location = client.post("/api/agent/chat", json={"message": "快递站在哪里？", "campus_id": campus_id})
    assert location.status_code == 200
    assert location.json()["intent"] == "campus_location_search"
    assert location.json()["tool_results"][0]["tool"] == "location_search"
    assert all(item["data_status"] != "demo_fixture" for item in location.json()["tool_results"][0]["data"])

    food = client.post("/api/agent/chat", json={"message": "饭堂以前有什么面或肠粉？", "campus_id": campus_id})
    assert food.status_code == 200
    assert food.json()["intent"] == "food_search"
    assert "当日菜单" in food.json()["answer"]

    process = client.post("/api/agent/chat", json={"message": "校园卡丢了怎么挂失补办？", "campus_id": campus_id})
    assert process.status_code == 200
    assert process.json()["intent"] == "campus_process"
    assert process.json()["tool_results"][0]["tool"] == "process_search"
    assert process.json()["tool_results"][0]["data"]


def test_conversations_are_private_between_users(client: TestClient, register_user):
    register_user("conversation-owner")
    conversation_id = client.post("/api/agent/chat", json={"message": "你好"}).json()["conversation_id"]
    register_user("conversation-other")
    assert client.get(f"/api/agent/conversations/{conversation_id}").status_code == 404
    assert client.post("/api/agent/chat", json={"message": "继续", "conversation_id": conversation_id}).status_code == 404


def test_agent_llm_planner_and_answer_use_mocked_model(monkeypatch, client: TestClient, register_user):
    register_user("mock-agent")
    settings = type("S", (), {
        "deepseek_api_key": "mock-key",
        "deepseek_base_url": "https://mock.invalid",
        "deepseek_model": "mock-model",
    })()
    monkeypatch.setattr("app.services.agent_service.get_settings", lambda: settings)

    def fake_model(self, system_prompt: str, user_message: str) -> dict:
        del self, user_message
        if "意图规划器" in system_prompt:
            return {"intent": "learning_guidance", "confidence": 0.97, "query": "高数", "tool_plan": []}
        return {"answer": "这是由测试中的模拟模型生成的学习计划。"}

    monkeypatch.setattr(AgentService, "_model_json", fake_model)
    response = client.post("/api/agent/chat", json={"message": "高数跟不上怎么办"})
    assert response.status_code == 200
    assert response.json()["degraded"] is False
    assert "模拟模型" in response.json()["answer"]


def test_agent_model_failure_returns_degraded_error_id(monkeypatch, client: TestClient, register_user):
    register_user("failed-agent")
    settings = type("S", (), {
        "deepseek_api_key": "mock-key",
        "deepseek_base_url": "https://mock.invalid",
        "deepseek_model": "mock-model",
    })()
    monkeypatch.setattr("app.services.agent_service.get_settings", lambda: settings)
    monkeypatch.setattr(AgentService, "_model_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("mock timeout")))
    response = client.post("/api/agent/chat", json={"message": "你好，你能做什么？"})
    assert response.status_code == 200
    assert response.json()["degraded"] is True
    assert len(response.json()["error_id"]) == 12


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
