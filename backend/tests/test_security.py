import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings


def test_auth_responses_never_expose_secrets(client: TestClient, register_user):
    response = register_user("safe-response")
    serialized = str(response["user"]).lower()
    assert "password" not in serialized
    assert "token" not in serialized
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert "password" not in me.text.lower()


def test_production_rejects_weak_secrets_and_insecure_cookies():
    with pytest.raises(ValidationError):
        Settings(environment="production")
    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            jwt_secret="a" * 48,
            refresh_token_secret="b" * 48,
            cookie_secure=False,
        )


def test_admin_import_rejects_oversized_upload(client: TestClient, login_admin):
    login_admin()
    payload = b"x" * (5 * 1024 * 1024 + 1)
    response = client.post(
        "/api/admin/data/import",
        files={"file": ("too-large.json", payload, "application/json")},
    )
    assert response.status_code == 413


def test_account_deletion_revokes_access(client: TestClient, register_user):
    register_user("delete-me")
    assert client.delete("/api/auth/account").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_admin_account_cannot_bypass_audit_retention(client: TestClient, login_admin):
    login_admin()
    response = client.delete("/api/auth/account")
    assert response.status_code == 409
    assert "审计记录" in response.json()["detail"]
    assert client.get("/api/auth/me").status_code == 200


def test_security_headers_and_request_id(client: TestClient):
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["x-request-id"]
