"""Auth endpoint tests."""

from tests.conftest import auth_headers


def test_register_returns_token_and_user(client):
    res = client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "supersecret789"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "carol@example.com"
    assert "password" not in body["user"]


def test_register_duplicate_email_409(client, user_a):
    res = client.post(
        "/api/v1/auth/register",
        json={"email": user_a["email"], "password": "anotherpass123"},
    )
    assert res.status_code == 409


def test_register_weak_password_422(client):
    res = client.post(
        "/api/v1/auth/register",
        json={"email": "dave@example.com", "password": "short"},
    )
    assert res.status_code == 422


def test_register_invalid_email_422(client):
    res = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "supersecret123"},
    )
    assert res.status_code == 422


def test_login_ok(client, user_a):
    res = client.post(
        "/api/v1/auth/login",
        json={"email": user_a["email"], "password": user_a["password"]},
    )
    assert res.status_code == 200
    assert res.json()["access_token"]


def test_login_wrong_password_401(client, user_a):
    res = client.post(
        "/api/v1/auth/login",
        json={"email": user_a["email"], "password": "wrong-password"},
    )
    assert res.status_code == 401


def test_login_unknown_email_401(client):
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "whatever123"},
    )
    assert res.status_code == 401


def test_me_with_token(client, user_a):
    res = client.get("/api/v1/auth/me", headers=auth_headers(user_a["token"]))
    assert res.status_code == 200
    assert res.json()["email"] == user_a["email"]


def test_me_without_token_401(client):
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401


def test_me_with_garbage_token_401(client):
    res = client.get("/api/v1/auth/me", headers=auth_headers("garbage.token.value"))
    assert res.status_code == 401
