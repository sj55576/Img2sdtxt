"""Application metrics with an optional Prometheus client backend.

The application keeps instrumentation in this small module so request,
provider, cache, rate-limit, and queue code do not depend on the web route
that exposes ``/metrics``.  The dependency is optional at import time to keep
local tooling usable before the full requirements file is installed; CI and
production install ``prometheus-client``.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from typing import Any, Optional

try:
    from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest

    _REGISTRY = CollectorRegistry()
    _HTTP_REQUESTS = Counter(
        "img2sdtxt_http_requests_total",
        "Total HTTP requests handled by Img2sdtxt.",
        ("method", "path", "status"),
        registry=_REGISTRY,
    )
    _HTTP_DURATION = Histogram(
        "img2sdtxt_http_request_duration_seconds",
        "HTTP request duration in seconds.",
        ("path",),
        registry=_REGISTRY,
    )
    _LLM_REQUESTS = Counter(
        "img2sdtxt_llm_requests_total",
        "Total LLM requests.",
        ("provider", "model", "mode", "status"),
        registry=_REGISTRY,
    )
    _LLM_DURATION = Histogram(
        "img2sdtxt_llm_duration_seconds",
        "LLM request duration in seconds.",
        ("provider", "model"),
        registry=_REGISTRY,
    )
    _SD_REQUESTS = Counter(
        "img2sdtxt_sd_requests_total",
        "Total Stable Diffusion API requests.",
        ("endpoint", "status"),
        registry=_REGISTRY,
    )
    _CACHE_HITS = Counter("img2sdtxt_cache_hits_total", "LLM cache hits.", registry=_REGISTRY)
    _CACHE_MISSES = Counter("img2sdtxt_cache_misses_total", "LLM cache misses.", registry=_REGISTRY)
    _RATE_LIMIT_HITS = Counter(
        "img2sdtxt_rate_limit_hits_total",
        "Requests rejected by the rate limiter.",
        ("tier",),
        registry=_REGISTRY,
    )
    _JOB_QUEUE_SIZE = Gauge(
        "img2sdtxt_job_queue_size",
        "Current job queue size by status.",
        ("status",),
        registry=_REGISTRY,
    )
    _FALLBACK_SWITCHES = Counter(
        "img2sdtxt_fallback_switch_total",
        "Fallback provider switches.",
        ("from", "to"),
        registry=_REGISTRY,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only in minimal local envs
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    _PROMETHEUS_AVAILABLE = False


def _label(value: Any, default: str = "unknown") -> str:
    text = str(value or "").strip()
    return text or default


# Recent-outcome tracking for `/health`.  Kept independent of the optional
# prometheus_client backend (Histograms/Counters are cumulative and don't
# answer "how is this provider doing right now"), and bounded so it never
# grows unbounded in a long-running process.
_RECENT_WINDOW = 50
_recent_lock = threading.Lock()
_recent_llm: dict[str, deque[tuple[bool, float]]] = defaultdict(lambda: deque(maxlen=_RECENT_WINDOW))
_recent_sd: deque[tuple[bool, float]] = deque(maxlen=_RECENT_WINDOW)


def _summarize_recent(samples: deque[tuple[bool, float]]) -> dict[str, Any]:
    if not samples:
        return {"requests": 0, "success_rate": None, "avg_latency_ms": None}
    successes = sum(1 for ok, _ in samples if ok)
    total_latency = sum(duration for _, duration in samples)
    return {
        "requests": len(samples),
        "success_rate": round(successes / len(samples), 4),
        "avg_latency_ms": round((total_latency / len(samples)) * 1000, 1),
    }


def get_llm_health_stats(provider: str) -> dict[str, Any]:
    """Recent request count / success rate / avg latency for one LLM provider."""
    key = _label(provider)
    with _recent_lock:
        samples = deque(_recent_llm[key]) if key in _recent_llm else deque()
    return _summarize_recent(samples)


def get_sd_health_stats() -> dict[str, Any]:
    """Recent request count / success rate / avg latency for the Stable Diffusion API."""
    with _recent_lock:
        samples = deque(_recent_sd)
    return _summarize_recent(samples)


def observe_http(method: str, path: str, status: int, duration_seconds: float) -> None:
    if not _PROMETHEUS_AVAILABLE:
        return
    path_label = _label(path, "/unknown")
    _HTTP_REQUESTS.labels(_label(method, "UNKNOWN"), path_label, str(status)).inc()
    _HTTP_DURATION.labels(path_label).observe(max(duration_seconds, 0.0))


def observe_llm_request(
    provider: str,
    model: str,
    mode: str,
    status: str,
    duration_seconds: float,
) -> None:
    provider_label = _label(provider)
    model_label = _label(model)
    with _recent_lock:
        _recent_llm[provider_label].append((status == "success", max(duration_seconds, 0.0)))
    if not _PROMETHEUS_AVAILABLE:
        return
    _LLM_REQUESTS.labels(provider_label, model_label, _label(mode), _label(status)).inc()
    _LLM_DURATION.labels(provider_label, model_label).observe(max(duration_seconds, 0.0))


def observe_sd_request(endpoint: str, status: str, duration_seconds: Optional[float] = None) -> None:
    if duration_seconds is not None:
        with _recent_lock:
            _recent_sd.append((status == "success", max(duration_seconds, 0.0)))
    if _PROMETHEUS_AVAILABLE:
        _SD_REQUESTS.labels(_label(endpoint, "/unknown"), _label(status)).inc()


def observe_cache_hit() -> None:
    if _PROMETHEUS_AVAILABLE:
        _CACHE_HITS.inc()


def observe_cache_miss() -> None:
    if _PROMETHEUS_AVAILABLE:
        _CACHE_MISSES.inc()


def observe_rate_limit_hit(tier: str) -> None:
    if _PROMETHEUS_AVAILABLE:
        _RATE_LIMIT_HITS.labels(_label(tier)).inc()


def observe_fallback_switch(source: str, target: str) -> None:
    if _PROMETHEUS_AVAILABLE:
        _FALLBACK_SWITCHES.labels(_label(source), _label(target)).inc()


def set_job_queue_size(stats: dict[str, Any]) -> None:
    """Update queue gauges from ``JobQueue.stats()`` without exposing internals."""
    if not _PROMETHEUS_AVAILABLE:
        return
    by_status = stats.get("by_status", {})
    for status in ("pending", "running", "completed", "failed", "cancelled"):
        _JOB_QUEUE_SIZE.labels(status).set(float(by_status.get(status, 0)))


def render_prometheus() -> bytes:
    """Render the current metrics payload for the ``/metrics`` endpoint."""
    if not _PROMETHEUS_AVAILABLE:
        return b"# prometheus-client is not installed\n"
    return generate_latest(_REGISTRY)
