from __future__ import annotations

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
        "ADMIN_BOOTSTRAP_EMAIL": "admin-test@example.com",
        "ADMIN_BOOTSTRAP_PASSWORD": "test-admin-password-123",
    }
)

from fastapi.testclient import TestClient  # noqa: E402

from app.core.rate_limit import auth_limiter  # noqa: E402
from app.core.database import engine  # noqa: E402
from app.main import app  # noqa: E402


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
