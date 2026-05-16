from __future__ import annotations

import os
import time
import uuid

import httpx
import pytest

BASE_URL = os.environ.get("AISI_BASE_URL", "http://localhost")
TIMEOUT = httpx.Timeout(15.0, connect=5.0)


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT, follow_redirects=True) as c:
        yield c


@pytest.fixture(scope="session")
def auth_headers(client: httpx.Client) -> dict[str, str]:
    email = f"e2e-{uuid.uuid4().hex[:10]}@example.com"
    password = "TestE2E_passw0rd!"
    r = client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": "E2E"},
    )
    if r.status_code != 201:
        r = client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
    assert r.status_code in (200, 201), r.text
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_traefik_reachable(client: httpx.Client) -> None:
    r = client.get("/api/healthz")
    assert r.status_code == 200, r.text


def test_login_with_wrong_password_rejected(client: httpx.Client) -> None:
    email = f"badpw-{uuid.uuid4().hex[:8]}@example.com"
    pw = "GoodPassword123!"
    reg = client.post(
        "/api/auth/register",
        json={"email": email, "password": pw, "full_name": "x"},
    )
    assert reg.status_code == 201
    bad = client.post("/api/auth/login", json={"email": email, "password": "wrong"})
    assert bad.status_code in (400, 401)


def test_auth_me_returns_user(client: httpx.Client, auth_headers: dict[str, str]) -> None:
    r = client.get("/api/auth/me", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["email"]
    assert body["id"]
    assert body["role"] in ("user", "admin")


def test_messages_listing_authenticated(client: httpx.Client, auth_headers: dict[str, str]) -> None:
    r = client.get("/api/messages", headers=auth_headers, params={"limit": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body
    assert isinstance(body["items"], list)


def test_messages_unauth_rejected(client: httpx.Client) -> None:
    r = client.get("/api/messages")
    assert r.status_code == 401


def test_sources_list(client: httpx.Client, auth_headers: dict[str, str]) -> None:
    r = client.get("/api/sources", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    items = body["items"] if isinstance(body, dict) else body
    assert isinstance(items, list)


def test_subscriptions_list(client: httpx.Client, auth_headers: dict[str, str]) -> None:
    r = client.get("/api/subscriptions", headers=auth_headers)
    assert r.status_code == 200
