"""Regression tests for request correlation, health status, and Prometheus metrics."""

import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import config
import deps
import metrics
from logging_utils import JsonFormatter, request_id_context
from main import app


def test_json_formatter_contains_request_id_and_structured_fields():
    token = request_id_context.set("request-123")
    try:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="request complete",
            args=(),
            exc_info=None,
        )
        record.duration_ms = 12.5
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_context.reset(token)

    assert payload["request_id"] == "request-123"
    assert payload["msg"] == "request complete"
    assert payload["duration_ms"] == 12.5


def _reset_recent_health_metrics():
    with metrics._recent_lock:
        metrics._recent_llm.clear()
        metrics._recent_sd.clear()


def test_llm_health_stats_default_to_no_data():
    _reset_recent_health_metrics()
    assert metrics.get_llm_health_stats("unused-provider") == {
        "requests": 0,
        "success_rate": None,
        "avg_latency_ms": None,
    }


def test_llm_health_stats_reflect_recent_requests():
    _reset_recent_health_metrics()
    metrics.observe_llm_request("acme", "model-1", "vision", "success", 0.2)
    metrics.observe_llm_request("acme", "model-1", "vision", "success", 0.4)
    metrics.observe_llm_request("acme", "model-1", "vision", "error", 0.6)

    stats = metrics.get_llm_health_stats("acme")

    assert stats["requests"] == 3
    assert stats["success_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert stats["avg_latency_ms"] == pytest.approx(400.0)


def test_sd_health_stats_only_record_when_duration_is_known():
    _reset_recent_health_metrics()
    metrics.observe_sd_request("/sdapi/v1/txt2img", "success", 0.5)
    metrics.observe_sd_request("/sdapi/v1/txt2img", "error", 1.5)
    metrics.observe_sd_request("/sdapi/v1/interrogate", "success")  # no duration -> not counted

    stats = metrics.get_sd_health_stats()

    assert stats["requests"] == 2
    assert stats["success_rate"] == pytest.approx(0.5)
    assert stats["avg_latency_ms"] == pytest.approx(1000.0)


def test_health_endpoint_includes_recent_llm_and_sd_stats(monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
    _reset_recent_health_metrics()
    metrics.observe_llm_request("test", "test-model", "vision", "success", 0.1)
    metrics.observe_sd_request("/sdapi/v1/txt2img", "success", 0.2)

    llm = MagicMock()
    llm.is_available.return_value = True
    llm.provider_name = "test"
    llm.model = "test-model"
    sd = MagicMock()
    sd.is_available.return_value = True

    with patch.object(deps, "llm_client", llm), patch.object(deps, "sd_client", sd):
        with TestClient(app) as client:
            response = client.get("/health")

    body = response.json()
    assert body["components"]["llm"]["recent"] == {
        "requests": 1,
        "success_rate": 1.0,
        "avg_latency_ms": 100.0,
    }
    assert body["components"]["sd_api"]["recent"] == {
        "requests": 1,
        "success_rate": 1.0,
        "avg_latency_ms": 200.0,
    }


def test_request_id_is_returned_and_health_reflects_sd_failure(monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
    llm = MagicMock()
    llm.is_available.return_value = True
    llm.provider_name = "test"
    llm.model = "test-model"
    sd = MagicMock()
    sd.is_available.return_value = False

    with patch.object(deps, "llm_client", llm), patch.object(deps, "sd_client", sd):
        with TestClient(app) as client:
            response = client.get("/health", headers={"X-Request-ID": "request-from-client"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "request-from-client"
    assert response.json()["status"] == "degraded"


def test_metrics_endpoint_is_available_and_can_be_token_protected(monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(config, "API_TOKEN", "metrics-secret")

    with TestClient(app) as client:
        assert client.get("/metrics").status_code == 401
        response = client.get("/metrics", headers={"Authorization": "Bearer metrics-secret"})

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]


@pytest.mark.skipif(not metrics._PROMETHEUS_AVAILABLE, reason="prometheus-client not installed")
def test_unmatched_paths_collapse_to_a_single_metric_label(monkeypatch):
    """Issue: unauthenticated path scans must not create unbounded Prometheus label series."""
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)

    with TestClient(app) as client:
        for i in range(5):
            response = client.get(f"/no-such-route-{i}")
            assert response.status_code == 404

    from prometheus_client import generate_latest

    body = generate_latest(metrics._REGISTRY).decode()
    unmatched_lines = [
        line
        for line in body.splitlines()
        if line.startswith("img2sdtxt_http_requests_total") and 'path="unmatched"' in line
    ]
    scanned_path_lines = [line for line in body.splitlines() if "no-such-route" in line]

    assert scanned_path_lines == []
    assert len(unmatched_lines) == 1
    assert unmatched_lines[0].strip().endswith("5.0")
