"""Regression tests for local-by-default API exposure and token protection."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(config, "API_TOKEN", "test-api-token")
    from main import app

    with TestClient(app) as test_client:
        yield test_client


def test_sensitive_endpoint_rejects_missing_token(client):
    response = client.delete("/api/history")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_sensitive_endpoint_accepts_bearer_token(client):
    response = client.get("/api/backup/list", headers={"Authorization": "Bearer test-api-token"})
    assert response.status_code == 200


def test_api_token_comparison_rejects_wrong_scheme_and_value(client):
    assert client.get("/api/backup/list", headers={"Authorization": "Basic test-api-token"}).status_code == 401
    assert client.get("/api/backup/list", headers={"Authorization": "Bearer wrong-token"}).status_code == 401


def test_safe_defaults_are_loopback_and_no_cross_origin_access():
    assert config.API_HOST == "127.0.0.1"
    assert config.CORS_ALLOWED_ORIGINS == []
