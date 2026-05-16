from __future__ import annotations

import os

import httpx
import pytest

BASE_URL = os.environ.get("AISI_BASE_URL", "http://localhost")


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=15.0, follow_redirects=True) as c:
        yield c


def test_objects_list_returns_items(client: httpx.Client) -> None:
    r = client.get("/api/objects", params={"limit": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    items = body["items"] if isinstance(body, dict) else body
    assert isinstance(items, list)


def test_top_undervalued_returns_marked_objects(client: httpx.Client) -> None:
    r = client.get(
        "/api/objects/top-undervalued",
        params={"city": "Moscow", "limit": 50},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    items = body["items"] if isinstance(body, dict) else body
    assert isinstance(items, list)
    assert len(items) > 0, "seed should provide undervalued objects"
    sample = items[0]
    assert "evaluation" in sample
    assert sample["evaluation"]["is_undervalued"] is True


def test_top_undervalued_district_filter(client: httpx.Client) -> None:
    r = client.get(
        "/api/objects/top-undervalued",
        params={"city": "Moscow", "district": "tverskoy", "limit": 50},
    )
    assert r.status_code == 200
    body = r.json()
    items = body["items"] if isinstance(body, dict) else body
    for it in items:
        addr = it.get("listing", {}).get("address", {})
        assert addr.get("district_slug") == "tverskoy"


def test_object_detail_or_history(client: httpx.Client) -> None:
    list_resp = client.get("/api/objects", params={"limit": 1})
    items = list_resp.json().get("items", [])
    if not items:
        pytest.skip("no objects to test detail against")
    oid = items[0]["id"]
    r = client.get(f"/api/objects/{oid}")
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["id"] == oid


def test_objects_diversity_across_districts(client: httpx.Client) -> None:
    r = client.get(
        "/api/objects/top-undervalued",
        params={"city": "Moscow", "limit": 200},
    )
    body = r.json()
    items = body["items"] if isinstance(body, dict) else body
    districts = {
        it.get("listing", {}).get("address", {}).get("district_slug")
        for it in items
        if it.get("listing")
    }
    districts.discard(None)
    assert len(districts) >= 20, f"expected >=20 distinct districts, got {len(districts)}"
