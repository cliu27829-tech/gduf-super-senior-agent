from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from uuid import uuid4

import pytest


TEST_DB = Path(tempfile.gettempdir()) / f"gduf-web-tests-{uuid4().hex}.db"
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{TEST_DB.as_posix()}",
        "ENVIRONMENT": "test",
        "SEED_DEMO_DATA": "true",
        "AUTO_CREATE_SCHEMA": "true",
        "DEEPSEEK_API_KEY": "",
        "AMAP_SECURITY_CODE": "",
        "AMAP_WEBSERVICE_KEY": "",
        "ADMIN_BOOTSTRAP_EMAIL": "admin-test@example.com",
        "ADMIN_BOOTSTRAP_PASSWORD": "test-admin-password-123",
    }
)

from fastapi.testclient import TestClient  # noqa: E402

from app.core.rate_limit import auth_limiter  # noqa: E402
from app.core.database import engine  # noqa: E402
from app.core.llm_client import get_llm_client  # noqa: E402
from app.main import app  # noqa: E402


class MockLLMClient:
    configured = True
    model = "mock-deepseek-v4-flash"

    def __init__(self):
        self.calls: list[list[dict[str, str]]] = []

    @staticmethod
    def _intent(message: str) -> str:
        patterns = (
            ("knowledge_import", ("导入资料", "上传知识", "保存文章")),
            ("knowledge_search", ("知识库", "查资料", "四六级报名")),
            ("notification_to_tasks", ("通知", "提交课程报告", "生成任务")),
            ("task_management", ("我的任务", "待办", "已完成", "逾期")),
            ("campus_process", ("校园卡", "挂失", "补办", "报修", "校园网", "网络故障", "借书", "还书", "续借")),
            ("campus_navigation", ("怎么走", "导航", "路线")),
            ("food_search", ("有什么吃", "面", "肠粉", "早餐", "菜品")),
            ("canteen_search", ("饭堂", "食堂", "餐厅")),
            ("campus_location_search", ("在哪里", "在哪", "快递", "医务室", "图书馆")),
            ("learning_guidance", ("高数", "学习", "考试周")),
            ("campus_life_guidance", ("社团", "新生", "入学")),
        )
        for intent, terms in patterns:
            if any(term in message for term in terms):
                return intent
        return "general_chat"

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.6,
        *,
        response_format: dict[str, str] | None = None,
    ) -> str:
        del temperature
        self.calls.append(messages)
        user_message = next(item["content"] for item in reversed(messages) if item["role"] == "user")
        if response_format:
            intent = self._intent(user_message)
            tool_plan = [intent] if intent in {
                "campus_location_search", "campus_navigation", "canteen_search", "food_search", "campus_process",
                "knowledge_search", "knowledge_import",
            } else []
            return json.dumps({"intent": intent, "confidence": 0.99, "query": user_message, "tool_plan": tool_plan})

        system = messages[0]["content"]
        if "我刚才说我叫什么" in user_message and any("我叫小明" in item["content"] for item in messages):
            return "你刚才说你叫小明。"
        if "非测绘示意坐标" in system:
            return "按非测绘示意坐标，北苑饭堂与北教学楼的相对位置更近；这不是步行距离或路线。"
        if "当日菜单" in system:
            return "目前没有可靠的当日菜单数据，以下是历史档口资料，不保证今日供应。"
        if "高数" in user_message:
            return "这是 Mock LLM 给出的高数学习建议，仅用于自动测试。"
        return "这是 Mock LLM 生成的测试回答。"


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client
    engine.dispose()
    TEST_DB.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def reset_auth_limiter():
    auth_limiter._events.clear()


@pytest.fixture
def mock_llm() -> MockLLMClient:
    return MockLLMClient()


@pytest.fixture(autouse=True)
def use_mock_llm(mock_llm: MockLLMClient):
    app.dependency_overrides[get_llm_client] = lambda: mock_llm
    yield
    app.dependency_overrides.pop(get_llm_client, None)


@pytest.fixture
def campus_id(client: TestClient) -> str:
    return client.get("/api/campuses").json()[0]["id"]


@pytest.fixture
def register_user(client: TestClient, campus_id: str):
    def _register(label: str = "user") -> dict:
        client.cookies.clear()
        suffix = uuid4().hex[:8]
        payload = {
            "username": f"{label}{suffix}",
            "nickname": f"测试用户{suffix}",
            "email": f"{label}-{suffix}@example.com",
            "password": "TestPass123",
            "campus_id": campus_id,
            "grade": "2026级",
            "major": "测试专业",
        }
        response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 201, response.text
        return {**payload, "user": response.json()["user"]}

    return _register


@pytest.fixture
def login_admin(client: TestClient):
    def _login() -> dict:
        client.cookies.clear()
        response = client.post(
            "/api/auth/login",
            json={"email": "admin-test@example.com", "password": "test-admin-password-123"},
        )
        assert response.status_code == 200, response.text
        return response.json()["user"]

    return _login
