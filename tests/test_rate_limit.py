"""Tests for rate_limit module."""

import pytest
from fastapi.testclient import TestClient

import config


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset rate limiter state between tests."""
    from main import app
    for mw in app.user_middleware:
        pass
    yield
    from rate_limit import RateLimitMiddleware
    for route in app.routes:
        pass
    # Clear the middleware's internal store directly
    for mw_instance in getattr(app, '_middleware_stack', None) or []:
        if hasattr(mw_instance, '_store'):
            mw_instance._store.clear()
            break


@pytest.fixture
def client():
    config.RATE_LIMIT_ENABLED = True
    config.RATE_LIMIT_GENERATION = 3
    config.RATE_LIMIT_API = 5
    from main import app
    # Clear rate limiter state by accessing the middleware
    stack = app.middleware_stack
    while stack:
        if hasattr(stack, '_store'):
            stack._store.clear()
            break
        stack = getattr(stack, 'app', None)
    return TestClient(app)


def test_rate_limit_allows_under_limit(client):
    for _ in range(3):
        r = client.get("/api/config")
        assert r.status_code == 200


def test_rate_limit_blocks_over_limit(client):
    for _ in range(5):
        client.get("/api/config")
    r = client.get("/api/config")
    assert r.status_code == 429
    assert "Rate limit exceeded" in r.json()["detail"]
    assert "Retry-After" in r.headers


def test_static_not_rate_limited(client):
    for _ in range(20):
        r = client.get("/")
        assert r.status_code == 200


def test_rate_limit_disabled():
    config.RATE_LIMIT_ENABLED = False
    from main import app
    c = TestClient(app)
    for _ in range(100):
        r = c.get("/api/config")
        assert r.status_code == 200
    config.RATE_LIMIT_ENABLED = True
