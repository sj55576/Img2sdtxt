"""tests/test_fallback.py — FallbackChain と HealthMonitor、/api/llm/health エンドポイントのテスト"""

import sys
import time
from pathlib import Path
from typing import Iterator, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import deps
from fallback import FallbackChain
from health_monitor import STATUS_DEGRADED, STATUS_HEALTHY, STATUS_UNAVAILABLE, HealthMonitor, HealthStatus
from llm_provider import LLMProvider
from main import app


class FakeProvider(LLMProvider):
    """テスト用の設定可能な LLMProvider 実装"""

    def __init__(
        self,
        name: str,
        available: bool = True,
        vision: bool = True,
        streaming: bool = True,
        text_response: str = "ok",
        raise_on_generate: Optional[Exception] = None,
        raise_on_image: Optional[Exception] = None,
        stream_chunks: Optional[List[str]] = None,
        raise_on_stream: Optional[Exception] = None,
        response_delay: float = 0.0,
    ):
        self._name = name
        self._available = available
        self._vision = vision
        self._streaming = streaming
        self._text_response = text_response
        self._raise_on_generate = raise_on_generate
        self._raise_on_image = raise_on_image
        self._stream_chunks = stream_chunks if stream_chunks is not None else [text_response]
        self._raise_on_stream = raise_on_stream
        self._response_delay = response_delay
        self.generate_calls = 0
        self.image_calls = 0
        self.stream_calls = 0

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return f"{self._name}-model"

    def is_available(self) -> bool:
        if self._response_delay:
            time.sleep(self._response_delay)
        return self._available

    def supports_vision(self) -> bool:
        return self._vision

    def supports_streaming(self) -> bool:
        return self._streaming

    def generate_response(self, prompt: str, max_tokens: int = 500) -> Optional[str]:
        self.generate_calls += 1
        if self._raise_on_generate:
            raise self._raise_on_generate
        return self._text_response

    def generate_response_with_image(self, prompt: str, image_bytes: bytes, max_tokens: int = 500) -> Optional[str]:
        self.image_calls += 1
        if self._raise_on_image:
            raise self._raise_on_image
        return self._text_response

    def generate_response_stream(self, prompt: str, max_tokens: int = 500) -> Iterator[str]:
        self.stream_calls += 1
        if self._raise_on_stream:
            raise self._raise_on_stream
        yield from self._stream_chunks

    def generate_response_with_image_stream(
        self, prompt: str, image_bytes: bytes, max_tokens: int = 500
    ) -> Iterator[str]:
        self.stream_calls += 1
        if self._raise_on_stream:
            raise self._raise_on_stream
        yield from self._stream_chunks


# ------------------------------------------------------------------ #
# FallbackChain
# ------------------------------------------------------------------ #


class TestFallbackChainBasics:
    def test_is_llm_provider_subclass(self):
        assert issubclass(FallbackChain, LLMProvider)

    def test_requires_at_least_one_provider(self):
        with pytest.raises(ValueError):
            FallbackChain([])

    def test_provider_name_is_fallback(self):
        chain = FallbackChain([FakeProvider("a")])
        assert chain.provider_name == "fallback"

    def test_model_returns_primary_provider_model(self):
        chain = FallbackChain([FakeProvider("a"), FakeProvider("b")])
        assert chain.model == "a-model"

    def test_is_available_true_if_any_provider_available(self):
        chain = FallbackChain([FakeProvider("a", available=False), FakeProvider("b", available=True)])
        assert chain.is_available() is True

    def test_is_available_false_if_all_unavailable(self):
        chain = FallbackChain([FakeProvider("a", available=False), FakeProvider("b", available=False)])
        assert chain.is_available() is False

    def test_supports_vision_true_if_any_provider_supports(self):
        chain = FallbackChain([FakeProvider("a", vision=False), FakeProvider("b", vision=True)])
        assert chain.supports_vision() is True

    def test_supports_vision_false_if_none_support(self):
        chain = FallbackChain([FakeProvider("a", vision=False), FakeProvider("b", vision=False)])
        assert chain.supports_vision() is False

    def test_supports_streaming_true_if_available_streaming_provider_exists(self):
        chain = FallbackChain([FakeProvider("a", streaming=False), FakeProvider("b", streaming=True)])
        assert chain.supports_streaming() is True

    def test_supports_streaming_false_if_no_streaming_provider_available(self):
        chain = FallbackChain([FakeProvider("a", streaming=False, available=True)])
        assert chain.supports_streaming() is False

    def test_last_used_provider_starts_none(self):
        chain = FallbackChain([FakeProvider("a")])
        assert chain.last_used_provider is None


class TestFallbackChainGenerateResponse:
    def test_tries_providers_in_order_and_uses_first_success(self):
        a = FakeProvider("a", text_response="from-a")
        b = FakeProvider("b", text_response="from-b")
        chain = FallbackChain([a, b])

        result = chain.generate_response("prompt")

        assert result == "from-a"
        assert a.generate_calls == 1
        assert b.generate_calls == 0
        assert chain.last_used_provider == "a"

    def test_skips_failed_provider_and_uses_next(self):
        a = FakeProvider("a", raise_on_generate=ConnectionError("boom"))
        b = FakeProvider("b", text_response="from-b")
        chain = FallbackChain([a, b])

        result = chain.generate_response("prompt")

        assert result == "from-b"
        assert a.generate_calls == 1
        assert b.generate_calls == 1
        assert chain.last_used_provider == "b"

    def test_raises_last_exception_if_all_providers_fail(self):
        a = FakeProvider("a", raise_on_generate=ConnectionError("a-down"))
        b = FakeProvider("b", raise_on_generate=TimeoutError("b-timeout"))
        chain = FallbackChain([a, b])

        with pytest.raises(TimeoutError, match="b-timeout"):
            chain.generate_response("prompt")

    def test_generic_exception_also_triggers_fallback(self):
        a = FakeProvider("a", raise_on_generate=Exception("generic failure"))
        b = FakeProvider("b", text_response="from-b")
        chain = FallbackChain([a, b])

        result = chain.generate_response("prompt")
        assert result == "from-b"


class TestFallbackChainGenerateResponseWithImage:
    def test_filters_to_vision_capable_providers_only(self):
        a = FakeProvider("a", vision=False, text_response="from-a")
        b = FakeProvider("b", vision=True, text_response="from-b")
        chain = FallbackChain([a, b])

        result = chain.generate_response_with_image("prompt", b"imgbytes")

        assert result == "from-b"
        assert a.image_calls == 0
        assert b.image_calls == 1
        assert chain.last_used_provider == "b"

    def test_raises_if_no_vision_capable_providers(self):
        a = FakeProvider("a", vision=False)
        chain = FallbackChain([a])

        with pytest.raises(RuntimeError):
            chain.generate_response_with_image("prompt", b"imgbytes")

    def test_falls_back_among_vision_providers_on_failure(self):
        a = FakeProvider("a", vision=True, raise_on_image=ConnectionError("down"))
        b = FakeProvider("b", vision=True, text_response="from-b")
        chain = FallbackChain([a, b])

        result = chain.generate_response_with_image("prompt", b"imgbytes")
        assert result == "from-b"


class TestFallbackChainStreaming:
    def test_uses_first_available_streaming_provider(self):
        a = FakeProvider("a", streaming=True, stream_chunks=["a1", "a2"])
        b = FakeProvider("b", streaming=True, stream_chunks=["b1"])
        chain = FallbackChain([a, b])

        chunks = list(chain.generate_response_stream("prompt"))

        assert chunks == ["a1", "a2"]
        assert a.stream_calls == 1
        assert b.stream_calls == 0

    def test_skips_non_streaming_provider(self):
        a = FakeProvider("a", streaming=False)
        b = FakeProvider("b", streaming=True, stream_chunks=["b1"])
        chain = FallbackChain([a, b])

        chunks = list(chain.generate_response_stream("prompt"))
        assert chunks == ["b1"]

    def test_falls_back_to_non_streaming_when_no_streaming_provider(self):
        a = FakeProvider("a", streaming=False, text_response="non-stream-a")
        chain = FallbackChain([a])

        chunks = list(chain.generate_response_stream("prompt"))
        assert chunks == ["non-stream-a"]
        assert a.generate_calls == 1

    def test_falls_back_to_generate_response_when_stream_raises(self):
        a = FakeProvider(
            "a", streaming=True, raise_on_stream=ConnectionError("stream-down"), text_response="fallback-text"
        )
        chain = FallbackChain([a])

        chunks = list(chain.generate_response_stream("prompt"))
        assert chunks == ["fallback-text"]
        assert a.generate_calls == 1

    def test_image_stream_filters_vision_capable(self):
        a = FakeProvider("a", vision=False, streaming=True)
        b = FakeProvider("b", vision=True, streaming=True, stream_chunks=["vision-chunk"])
        chain = FallbackChain([a, b])

        chunks = list(chain.generate_response_with_image_stream("prompt", b"imgbytes"))
        assert chunks == ["vision-chunk"]


# ------------------------------------------------------------------ #
# HealthMonitor
# ------------------------------------------------------------------ #


class TestHealthMonitor:
    def test_check_all_records_healthy_status(self):
        provider = FakeProvider("a", available=True)
        monitor = HealthMonitor({"a": provider}, check_interval=60)

        monitor.check_all()
        status = monitor.get_status()

        assert "a" in status
        assert status["a"].status == STATUS_HEALTHY
        assert isinstance(status["a"], HealthStatus)

    def test_check_all_records_unavailable_status(self):
        provider = FakeProvider("a", available=False)
        monitor = HealthMonitor({"a": provider}, check_interval=60)

        monitor.check_all()
        status = monitor.get_status()

        assert status["a"].status == STATUS_UNAVAILABLE

    def test_check_all_records_degraded_when_slow(self):
        provider = FakeProvider("a", available=True, response_delay=0.01)
        monitor = HealthMonitor({"a": provider}, check_interval=60)

        with patch("health_monitor.DEGRADED_THRESHOLD_SECONDS", 0.001):
            monitor.check_all()

        status = monitor.get_status()
        assert status["a"].status == STATUS_DEGRADED

    def test_check_all_handles_provider_exception_as_unavailable(self):
        provider = MagicMock(spec=LLMProvider)
        provider.provider_name = "broken"
        provider.is_available.side_effect = Exception("boom")
        monitor = HealthMonitor({"broken": provider}, check_interval=60)

        monitor.check_all()
        status = monitor.get_status()

        assert status["broken"].status == STATUS_UNAVAILABLE

    def test_get_status_returns_empty_before_any_check(self):
        provider = FakeProvider("a")
        monitor = HealthMonitor({"a": provider}, check_interval=60)
        assert monitor.get_status() == {}

    def test_start_and_stop_runs_background_thread(self):
        provider = FakeProvider("a", available=True)
        monitor = HealthMonitor({"a": provider}, check_interval=60)

        monitor.start()
        try:
            # start() triggers an immediate check before waiting for the interval
            deadline = time.monotonic() + 2.0
            while not monitor.get_status() and time.monotonic() < deadline:
                time.sleep(0.01)
            status = monitor.get_status()
            assert "a" in status
        finally:
            monitor.stop()

    def test_multiple_providers_tracked_independently(self):
        a = FakeProvider("a", available=True)
        b = FakeProvider("b", available=False)
        monitor = HealthMonitor({"a": a, "b": b}, check_interval=60)

        monitor.check_all()
        status = monitor.get_status()

        assert status["a"].status == STATUS_HEALTHY
        assert status["b"].status == STATUS_UNAVAILABLE


# ------------------------------------------------------------------ #
# /api/llm/health endpoint and /api/llm/providers fallback info
# ------------------------------------------------------------------ #


class TestHealthEndpoint:
    def test_health_endpoint_returns_expected_shape_with_monitor(self):
        a = FakeProvider("a", available=True)
        b = FakeProvider("b", available=False)
        chain = FallbackChain([a, b])
        monitor = HealthMonitor({"a": a, "b": b}, check_interval=60)
        monitor.check_all()

        client = TestClient(app)

        with (
            patch.object(deps, "health_monitor", monitor),
            patch.object(deps, "fallback_chain", chain),
            patch.object(deps, "llm_client", chain),
        ):
            resp = client.get("/api/llm/health")

        assert resp.status_code == 200
        data = resp.json()
        assert "providers" in data
        assert data["providers"]["a"]["status"] == STATUS_HEALTHY
        assert data["providers"]["b"]["status"] == STATUS_UNAVAILABLE
        assert data["fallback_chain"] == ["a", "b"]
        assert data["active_provider"] == "fallback"

    def test_health_endpoint_without_monitor_returns_empty_providers(self):
        client = TestClient(app)

        with patch.object(deps, "health_monitor", None), patch.object(deps, "fallback_chain", None):
            resp = client.get("/api/llm/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data["providers"] == {}
        assert data["fallback_chain"] == []

    def test_providers_endpoint_includes_fallback_info(self):
        a = FakeProvider("a")
        b = FakeProvider("b")
        chain = FallbackChain([a, b])
        chain.generate_response("prompt")  # populate last_used_provider

        client = TestClient(app)

        with patch.object(deps, "fallback_chain", chain):
            resp = client.get("/api/llm/providers")

        assert resp.status_code == 200
        data = resp.json()
        assert data["fallback"]["enabled"] is True
        assert data["fallback"]["chain"] == ["a", "b"]
        assert data["fallback"]["last_used"] == "a"

    def test_providers_endpoint_fallback_disabled_when_no_chain(self):
        client = TestClient(app)

        with patch.object(deps, "fallback_chain", None):
            resp = client.get("/api/llm/providers")

        assert resp.status_code == 200
        data = resp.json()
        assert data["fallback"]["enabled"] is False
        assert data["fallback"]["chain"] == []
        assert data["fallback"]["last_used"] is None
