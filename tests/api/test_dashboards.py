from __future__ import annotations

import os

import httpx
import pytest

BASE_URL = os.environ.get("AISI_BASE_URL", "http://localhost")


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=20.0, follow_redirects=True) as c:
        yield c


def test_overview(client: httpx.Client) -> None:
    r = client.get("/api/dashboards/overview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, dict)


def test_prices_by_district_has_many_districts(client: httpx.Client) -> None:
    r = client.get("/api/dashboards/prices/by-district", params={"city": "Moscow"})
    assert r.status_code == 200
    points = r.json().get("points", [])
    assert len(points) >= 50, f"expected populated MV, got {len(points)} rows"
    sample = points[0]
    assert sample["avg_price_per_m2"] > 0
    assert sample["district_slug"]


def test_prices_timeseries(client: httpx.Client) -> None:
    r = client.get("/api/dashboards/prices/timeseries", params={"city": "Moscow"})
    assert r.status_code == 200
    body = r.json()
    assert "points" in body or isinstance(body, list)


def test_sentiment_by_district(client: httpx.Client) -> None:
    r = client.get("/api/dashboards/sentiment/by-district")
    assert r.status_code == 200
    points = r.json().get("points", [])
    assert isinstance(points, list)


def test_listings_by_channel(client: httpx.Client) -> None:
    r = client.get("/api/dashboards/listings/by-channel")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict) or isinstance(body, list)


def test_model_quality(client: httpx.Client) -> None:
    r = client.get("/api/dashboards/model-quality")
    assert r.status_code == 200


def test_topics_activity_requires_topic(client: httpx.Client) -> None:
    r = client.get("/api/dashboards/topics/activity")
    assert r.status_code == 422


def test_topics_activity_with_topic(client: httpx.Client) -> None:
    r = client.get(
        "/api/dashboards/topics/activity",
        params={"topic": "mortgage_rates"},
    )
    assert r.status_code in (200, 404)


def test_geojson_assets_served(client: httpx.Client) -> None:
    r = client.get("/geo/moscow-districts.geojson")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) >= 100
    sample = body["features"][0]
    assert "slug" in sample["properties"]
    assert "name" in sample["properties"]
