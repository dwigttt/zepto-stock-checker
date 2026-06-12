import pytest
from fastapi.testclient import TestClient

from app import config, main
from app.ratelimit import RateLimiter

VALID_PVID = "0059ff6a-7eb0-477a-a7f5-69256f2c444b"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_PATH", ":memory:")
    with TestClient(main.app) as c:
        yield c


def test_open_when_no_token_configured(client, monkeypatch):
    monkeypatch.setattr(config, "APP_TOKEN", None)
    assert client.get("/api/stats").status_code == 200


def test_requires_token_when_configured(client, monkeypatch):
    monkeypatch.setattr(config, "APP_TOKEN", "secret")
    assert client.get("/api/stats").status_code == 401
    assert client.get("/api/stats", headers={"X-App-Token": "secret"}).status_code == 200
    assert client.get("/api/stats?token=secret").status_code == 200


def test_wrong_token_rejected(client, monkeypatch):
    monkeypatch.setattr(config, "APP_TOKEN", "secret")
    assert client.get("/api/stats", headers={"X-App-Token": "nope"}).status_code == 401


def test_config_endpoint_is_open_and_reports_settings(client, monkeypatch):
    monkeypatch.setattr(config, "APP_TOKEN", "secret")
    monkeypatch.setattr(config, "MAX_RADIUS_KM", 25.0)
    r = client.get("/api/config")  # reachable without a token
    assert r.status_code == 200
    body = r.json()
    assert body["auth_required"] is True
    assert body["max_radius_km"] == 25.0


def test_request_rate_limit_returns_429(client, monkeypatch):
    monkeypatch.setattr(config, "APP_TOKEN", None)
    client.app.state.limiter = RateLimiter(
        request_capacity=1,
        request_refill_per_sec=0.0,
        search_capacity=1,
        search_refill_per_sec=0.0,
    )
    assert client.get("/api/stats").status_code == 200
    assert client.get("/api/stats").status_code == 429


def test_search_budget_exhausted_emits_sse_error(client, monkeypatch):
    monkeypatch.setattr(config, "APP_TOKEN", None)
    client.app.state.limiter = RateLimiter(
        request_capacity=10,
        request_refill_per_sec=0.0,
        search_capacity=0,  # no search budget at all
        search_refill_per_sec=0.0,
    )
    r = client.get(f"/api/search?pvid={VALID_PVID}&lat=12.97&lng=77.59&radius_km=5")
    assert r.status_code == 200  # SSE channel opens, then reports the error
    assert '"type": "error"' in r.text
    assert "limit" in r.text.lower()
