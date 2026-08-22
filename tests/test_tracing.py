"""Tests for optional OpenTelemetry tracing."""

import pytest
from fastapi import FastAPI

import tracing

try:
    import opentelemetry.instrumentation.fastapi  # noqa: F401
    import opentelemetry.instrumentation.requests  # noqa: F401
    import opentelemetry.sdk.trace  # noqa: F401

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when the extra isn't installed
    _OTEL_AVAILABLE = False


@pytest.fixture(autouse=True)
def _reset_tracing_state():
    """Tracing module state is global; keep it isolated between tests."""
    yield
    tracing._TRACING_ENABLED = False
    tracing._tracer = None


def test_configure_tracing_is_a_noop_without_an_endpoint():
    tracing.configure_tracing(FastAPI(), "test-service", "")
    assert tracing._TRACING_ENABLED is False
    assert tracing._tracer is None


def test_llm_span_yields_none_when_tracing_is_disabled():
    with tracing.llm_span("acme", "model-1", "vision") as span:
        assert span is None


def test_record_llm_span_result_is_a_noop_for_a_none_span():
    # Must not raise even though there is no real span to update.
    tracing.record_llm_span_result(None, "acme", "model-1", "success", 0.1)


@pytest.mark.skipif(not _OTEL_AVAILABLE, reason="opentelemetry packages not installed")
def test_configure_tracing_enables_tracing_and_records_llm_spans(monkeypatch):
    # The OTLP exporter posts over HTTP via `requests`; fake a successful response so
    # a forced flush below doesn't retry against the (unreachable) endpoint for real.
    import requests
    from opentelemetry import trace

    monkeypatch.setattr(requests.Session, "post", lambda self, *a, **kw: _FakeOtlpResponse())

    tracing.configure_tracing(FastAPI(), "test-service", "http://localhost:4318/v1/traces")
    assert tracing._TRACING_ENABLED is True
    assert tracing._tracer is not None

    try:
        with tracing.llm_span("acme", "model-1", "vision") as span:
            assert span is not None
            tracing.record_llm_span_result(span, "acme", "model-1", "success", 0.2)

        with tracing.llm_span("acme", "model-1", "vision") as span:
            tracing.record_llm_span_result(span, "acme", "model-1", "error", 0.5)
            assert span.status.status_code.name == "ERROR"
    finally:
        # Force the flush now, while the fake response is still patched in, so no
        # background retry against the unreachable endpoint survives the test.
        trace.get_tracer_provider().shutdown()


class _FakeOtlpResponse:
    status_code = 200
    text = ""
    reason = "OK"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
