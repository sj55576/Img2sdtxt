"""Optional OpenTelemetry tracing.

Disabled unless ``OTEL_EXPORTER_OTLP_ENDPOINT`` is configured, and a no-op if the
``opentelemetry-*`` packages are unavailable — mirrors ``metrics.py``'s optional
prometheus_client backend so importing or running this module never fails or
changes behavior for installs that don't use tracing.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator, Optional

logger = logging.getLogger("img2sdtxt.tracing")

_TRACING_ENABLED = False
_tracer: Any = None


def configure_tracing(app: Any, service_name: str, otlp_endpoint: str) -> None:
    """Wire up OpenTelemetry tracing for ``app`` when an OTLP endpoint is configured."""
    global _TRACING_ENABLED, _tracer
    if not otlp_endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning(
            "OTEL_EXPORTER_OTLP_ENDPOINT is set but the opentelemetry packages are not installed; tracing is disabled."
        )
        return

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    RequestsInstrumentor().instrument()
    _tracer = trace.get_tracer("img2sdtxt")
    _TRACING_ENABLED = True
    logger.info("OpenTelemetry tracing enabled (endpoint=%s)", otlp_endpoint)


@contextmanager
def llm_span(provider: str, model: str, mode: str) -> Iterator[Optional[Any]]:
    """Wrap an LLM call in a span; yields ``None`` (a no-op) when tracing is disabled."""
    if not _TRACING_ENABLED or _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span("llm.generate") as span:
        span.set_attribute("llm.provider", provider)
        span.set_attribute("llm.model", model)
        span.set_attribute("llm.mode", mode)
        yield span


def record_llm_span_result(
    span: Optional[Any], provider: str, model: str, status: str, duration_seconds: float
) -> None:
    """Attach the resolved outcome of an LLM call to its span.

    ``provider``/``model`` are re-recorded because fallback chains only know the
    actual provider used once the call returns; ``token`` counts aren't captured
    here since no provider integration in this codebase currently parses response
    usage fields.
    """
    if span is None:
        return
    from opentelemetry.trace import Status, StatusCode

    span.set_attribute("llm.provider", provider)
    span.set_attribute("llm.model", model)
    span.set_attribute("llm.status", status)
    span.set_attribute("llm.duration_seconds", duration_seconds)
    if status == "error":
        span.set_status(Status(StatusCode.ERROR))
