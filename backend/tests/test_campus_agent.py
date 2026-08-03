from fastapi.testclient import TestClient

from app.core.llm_client import (
    LLMAuthenticationError,
    LLMNotConfiguredError,
    LLMTimeoutError,
    get_llm_client,
)
from app.main import app


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
    assert body["degraded"] is False
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

    distance = client.post("/api/agent/chat", json={"message": "哪个饭堂离北教比较近？", "campus_id": campus_id})
    assert distance.status_code == 200
    assert distance.json()["intent"] == "canteen_search"
    assert "非测绘示意坐标" in distance.json()["answer"]
    assert distance.json()["tool_results"][0]["data"][0]["name"] == "北苑饭堂"


def test_conversations_are_private_between_users(client: TestClient, register_user):
    register_user("conversation-owner")
    conversation_id = client.post("/api/agent/chat", json={"message": "你好"}).json()["conversation_id"]
    register_user("conversation-other")
    assert client.get(f"/api/agent/conversations/{conversation_id}").status_code == 404
    assert client.post("/api/agent/chat", json={"message": "继续", "conversation_id": conversation_id}).status_code == 404


def test_agent_llm_planner_and_answer_use_mocked_model(client: TestClient, register_user, mock_llm):
    register_user("mock-agent")
    response = client.post("/api/agent/chat", json={"message": "高数跟不上怎么办"})
    assert response.status_code == 200
    assert response.json()["degraded"] is False
    assert "Mock LLM" in response.json()["answer"]
    assert len(mock_llm.calls) == 2


def test_agent_model_timeout_returns_explicit_error(client: TestClient, register_user, mock_llm):
    register_user("failed-agent")

    class TimeoutLLM:
        configured = True
        model = "mock-deepseek-v4-flash"

        async def chat_completion(self, *_args, **_kwargs):
            raise LLMTimeoutError()

    app.dependency_overrides[get_llm_client] = TimeoutLLM
    response = client.post("/api/agent/chat", json={"message": "你好，你能做什么？"})
    assert response.status_code == 504
    assert "响应超时" in response.json()["detail"]
    assert "错误编号" in response.json()["detail"]
    app.dependency_overrides[get_llm_client] = lambda: mock_llm


def test_agent_status_and_unconfigured_model_are_explicit(client: TestClient, register_user, mock_llm):
    class UnconfiguredLLM:
        configured = False
        model = "deepseek-v4-flash"

        async def chat_completion(self, *_args, **_kwargs):
            raise LLMNotConfiguredError()

    app.dependency_overrides[get_llm_client] = UnconfiguredLLM
    status = client.get("/api/agent/status")
    assert status.status_code == 200
    assert status.json() == {
        "backend": "ok",
        "llm_configured": False,
        "model": "deepseek-v4-flash",
        "database": "ok",
    }
    register_user("unconfigured-agent")
    response = client.post("/api/agent/chat", json={"message": "你好"})
    assert response.status_code == 503
    assert "尚未配置大模型密钥" in response.json()["detail"]
    app.dependency_overrides[get_llm_client] = lambda: mock_llm


def test_agent_authentication_failure_does_not_leak_key(client: TestClient, register_user, mock_llm):
    sentinel_key = "sensitive-test-key-that-must-not-leak"

    class AuthenticationFailureLLM:
        configured = True
        model = "deepseek-v4-flash"

        async def chat_completion(self, *_args, **_kwargs):
            raise LLMAuthenticationError()

    app.dependency_overrides[get_llm_client] = AuthenticationFailureLLM
    register_user("auth-failure-agent")
    response = client.post("/api/agent/chat", json={"message": "你好"})
    assert response.status_code == 502
    assert "认证失败" in response.json()["detail"]
    assert sentinel_key not in response.text
    app.dependency_overrides[get_llm_client] = lambda: mock_llm


def test_agent_rejects_blank_message(client: TestClient, register_user):
    register_user("blank-agent")
    response = client.post("/api/agent/chat", json={"message": "   "})
    assert response.status_code == 422


def test_agent_sends_recent_history_for_multi_turn_memory(client: TestClient, register_user, mock_llm):
    register_user("history-agent")
    first = client.post("/api/agent/chat", json={"message": "我叫小明，请记住。"})
    assert first.status_code == 200
    second = client.post(
        "/api/agent/chat",
        json={"message": "我刚才说我叫什么？", "conversation_id": first.json()["conversation_id"]},
    )
    assert second.status_code == 200
    assert "小明" in second.json()["answer"]
    answer_call = mock_llm.calls[-1]
    assert any(item["role"] == "user" and "我叫小明" in item["content"] for item in answer_call)
    assert any(item["role"] == "assistant" for item in answer_call)


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
