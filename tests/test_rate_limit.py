"""Tests for rate_limit module."""

import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import rate_limit as _rate_limit_module


@pytest.fixture(autouse=True)
def temp_rate_limit_db(tmp_path, monkeypatch):
    """Redirect rate_limit.DB_PATH to a temp file and reset state between tests."""
    db_file = tmp_path / "test_rate_limit.db"
    monkeypatch.setattr(_rate_limit_module, "DB_PATH", db_file)
    with sqlite3.connect(db_file) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_limit_entries (
                ip TEXT NOT NULL,
                tier TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ip_tier ON rate_limit_entries (ip, tier)")
        conn.commit()
    yield db_file


@pytest.fixture
def client(temp_rate_limit_db):
    config.RATE_LIMIT_ENABLED = True
    config.RATE_LIMIT_GENERATION = 3
    config.RATE_LIMIT_API = 5
    from main import app

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
