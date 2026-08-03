from fastapi.testclient import TestClient


def test_health_ready_and_openapi(client: TestClient):
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/ready").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "/api/auth/register" in schema["paths"]
    assert "/api/admin/dashboard" in schema["paths"]


def test_register_me_refresh_logout(client: TestClient, register_user):
    account = register_user("auth")
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == account["email"]
    assert client.post("/api/auth/refresh").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_duplicate_registration_and_uniform_login_error(client: TestClient, register_user):
    account = register_user("duplicate")
    client.cookies.clear()
    response = client.post(
        "/api/auth/register",
        json={key: value for key, value in account.items() if key != "user"},
    )
    assert response.status_code == 409
    wrong = client.post("/api/auth/login", json={"email": account["email"], "password": "wrong"})
    missing = client.post("/api/auth/login", json={"email": "missing@example.com", "password": "wrong"})
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json()["detail"] == missing.json()["detail"]


def test_profile_and_change_password(client: TestClient, register_user):
    account = register_user("profile")
    response = client.patch("/api/auth/me", json={"nickname": "新昵称", "grade": "2027级"})
    assert response.status_code == 200
    assert response.json()["nickname"] == "新昵称"
    changed = client.post(
        "/api/auth/change-password",
        json={"current_password": account["password"], "new_password": "NewPassword456"},
    )
    assert changed.status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": account["email"], "password": "NewPassword456"}).status_code == 200


def test_weak_password_is_rejected(client: TestClient, campus_id: str):
    response = client.post(
        "/api/auth/register",
        json={"username": "weakpass", "email": "weak@example.com", "password": "abcdefgh", "campus_id": campus_id},
    )
    assert response.status_code == 422

