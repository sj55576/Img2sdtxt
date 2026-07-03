"""tests/test_streaming.py — SSE ストリーミングエンドポイントとプロバイダーのストリーミングフォールバックのテスト"""

import sys
from pathlib import Path
from typing import Iterator, Optional
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import deps
import history as hist
from llm_provider import LLMProvider
from main import app
from prompt_generator import PromptGenerator

client = TestClient(app)

_JSON_RESPONSE = '{"positive": "1girl, cute, masterpiece", "negative": "blurry, lowres"}'


def _png_bytes() -> bytes:
    """テスト用の 1x1 PNG 画像を生成する"""
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (1, 1), color=(255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


class FakeStreamingProvider(LLMProvider):
    """チャンク列を逐次返すテスト用プロバイダー"""

    def __init__(self, chunks=None, error: Optional[Exception] = None):
        self._chunks = chunks if chunks is not None else [_JSON_RESPONSE[:20], _JSON_RESPONSE[20:]]
        self._error = error

    @property
    def provider_name(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return "fake-model"

    def is_available(self) -> bool:
        return True

    def generate_response(self, prompt: str, max_tokens: int = 500) -> Optional[str]:
        return "".join(self._chunks)

    def generate_response_with_image(self, prompt: str, image_bytes: bytes, max_tokens: int = 500) -> Optional[str]:
        return "".join(self._chunks)

    def supports_streaming(self) -> bool:
        return True

    def _iter(self) -> Iterator[str]:
        for c in self._chunks:
            yield c
        if self._error is not None:
            raise self._error

    def generate_response_stream(self, prompt: str, max_tokens: int = 500) -> Iterator[str]:
        return self._iter()

    def generate_response_with_image_stream(
        self, prompt: str, image_bytes: bytes, max_tokens: int = 500
    ) -> Iterator[str]:
        return self._iter()


class FakeNonStreamingProvider(LLMProvider):
    """ストリーミング未対応（基底クラスのフォールバックを使う）テスト用プロバイダー"""

    @property
    def provider_name(self) -> str:
        return "fake_plain"

    @property
    def model(self) -> str:
        return "plain-model"

    def is_available(self) -> bool:
        return True

    def generate_response(self, prompt: str, max_tokens: int = 500) -> Optional[str]:
        return _JSON_RESPONSE

    def generate_response_with_image(self, prompt: str, image_bytes: bytes, max_tokens: int = 500) -> Optional[str]:
        return _JSON_RESPONSE


def _parse_sse(body: str):
    """SSE レスポンスを (event, data) のリストにパースする"""
    import json as _json

    events = []
    for block in body.strip().split("\n\n"):
        event = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = _json.loads(line[len("data:"):].strip())
        if event is not None:
            events.append((event, data))
    return events


@pytest.fixture(autouse=True)
def disable_rate_limit(monkeypatch):
    import config

    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_history.db"
    monkeypatch.setattr(hist, "DB_PATH", db_file)
    yield db_file


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    """キャッシュは常にミスさせる（キャッシュヒットのテストでは個別に上書き）"""
    cache = MagicMock()
    cache.get.return_value = None
    monkeypatch.setattr(deps, "llm_cache", cache)
    yield cache


def _install_provider(monkeypatch, provider: LLMProvider):
    monkeypatch.setattr(deps, "llm_client", provider)
    monkeypatch.setattr(deps, "prompt_generator", PromptGenerator(provider))


# ------------------------------------------------------------------ #
# テキスト入力のストリーミング
# ------------------------------------------------------------------ #


def test_stream_text_success(monkeypatch):
    _install_provider(monkeypatch, FakeStreamingProvider())

    r = client.post(
        "/api/generate-prompts-stream",
        data={"description": "a cute girl", "save_history": "true"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(r.text)
    names = [e for e, _ in events]
    assert names[0] == "start"
    assert names.count("token") == 2
    assert names[-1] == "done"

    start = events[0][1]
    assert start["provider"] == "fake"
    assert start["cached"] is False

    done = events[-1][1]
    assert done["positive"] == "1girl, cute, masterpiece"
    assert done["negative"] == "blurry, lowres"
    assert done["cached"] is False
    assert "history_id" in done

    items = hist.get_history()
    assert len(items) == 1
    assert items[0]["image_name"] == "[text input]"


def test_stream_token_events_reconstruct_full_text(monkeypatch):
    chunks = ['{"positive": "a', ' cat", "negative"', ': "bad"}']
    _install_provider(monkeypatch, FakeStreamingProvider(chunks=chunks))

    r = client.post("/api/generate-prompts-stream", data={"description": "x", "save_history": "false"})
    events = _parse_sse(r.text)
    tokens = [d["text"] for e, d in events if e == "token"]
    assert "".join(tokens) == "".join(chunks)


def test_stream_image_success(monkeypatch):
    _install_provider(monkeypatch, FakeStreamingProvider())

    r = client.post(
        "/api/generate-prompts-stream",
        files={"file": ("test.png", _png_bytes(), "image/png")},
        data={"save_history": "true"},
    )
    assert r.status_code == 200
    events = _parse_sse(r.text)
    names = [e for e, _ in events]
    assert names[0] == "start"
    assert names[-1] == "done"
    assert events[-1][1]["positive"] == "1girl, cute, masterpiece"

    items = hist.get_history()
    assert len(items) == 1
    assert items[0]["image_name"] == "test.png"


def test_stream_image_invalid_type_rejected(monkeypatch):
    _install_provider(monkeypatch, FakeStreamingProvider())

    r = client.post(
        "/api/generate-prompts-stream",
        files={"file": ("test.txt", b"not an image", "text/plain")},
    )
    assert r.status_code == 400


def test_stream_save_history_false(monkeypatch):
    _install_provider(monkeypatch, FakeStreamingProvider())

    r = client.post("/api/generate-prompts-stream", data={"description": "x", "save_history": "false"})
    events = _parse_sse(r.text)
    done = events[-1][1]
    assert "history_id" not in done
    assert hist.get_history() == []


# ------------------------------------------------------------------ #
# エラーパス
# ------------------------------------------------------------------ #


def test_stream_error_mid_stream(monkeypatch):
    _install_provider(
        monkeypatch,
        FakeStreamingProvider(chunks=["partial"], error=ConnectionError("connection lost")),
    )

    r = client.post("/api/generate-prompts-stream", data={"description": "x"})
    assert r.status_code == 200  # ストリーム開始後のエラーは error イベントで通知
    events = _parse_sse(r.text)
    names = [e for e, _ in events]
    assert names[-1] == "error"
    assert "connection lost" in events[-1][1]["error"]
    assert hist.get_history() == []


def test_stream_invalid_json_yields_error(monkeypatch):
    _install_provider(monkeypatch, FakeStreamingProvider(chunks=["this is not json"]))

    r = client.post("/api/generate-prompts-stream", data={"description": "x"})
    events = _parse_sse(r.text)
    assert events[-1][0] == "error"
    assert "JSON parse error" in events[-1][1]["error"]


def test_stream_empty_response_yields_error(monkeypatch):
    _install_provider(monkeypatch, FakeStreamingProvider(chunks=[]))

    r = client.post("/api/generate-prompts-stream", data={"description": "x"})
    events = _parse_sse(r.text)
    assert events[-1][0] == "error"


def test_stream_requires_input():
    r = client.post("/api/generate-prompts-stream", data={"description": "   "})
    assert r.status_code == 400


# ------------------------------------------------------------------ #
# キャッシュヒット
# ------------------------------------------------------------------ #


def test_stream_cache_hit_skips_tokens(monkeypatch, no_cache):
    _install_provider(monkeypatch, FakeStreamingProvider())
    no_cache.get.return_value = {"positive": "cached pos", "negative": "cached neg", "status": "success"}

    r = client.post("/api/generate-prompts-stream", data={"description": "x", "save_history": "false"})
    events = _parse_sse(r.text)
    names = [e for e, _ in events]
    assert "token" not in names
    done = events[-1][1]
    assert done["positive"] == "cached pos"
    assert done["cached"] is True


def test_stream_success_stores_cache(monkeypatch, no_cache):
    _install_provider(monkeypatch, FakeStreamingProvider())

    client.post("/api/generate-prompts-stream", data={"description": "x", "save_history": "false"})
    assert no_cache.set.called


# ------------------------------------------------------------------ #
# 非ストリーミングプロバイダーのフォールバック
# ------------------------------------------------------------------ #


def test_stream_fallback_single_chunk(monkeypatch):
    provider = FakeNonStreamingProvider()
    assert provider.supports_streaming() is False
    _install_provider(monkeypatch, provider)

    r = client.post("/api/generate-prompts-stream", data={"description": "x", "save_history": "false"})
    events = _parse_sse(r.text)
    names = [e for e, _ in events]
    assert names.count("token") == 1  # 基底クラスのフォールバックで一括1チャンク
    assert names[-1] == "done"
    assert events[-1][1]["positive"] == "1girl, cute, masterpiece"


def test_base_class_stream_fallback_yields_whole_text():
    provider = FakeNonStreamingProvider()
    assert list(provider.generate_response_stream("p")) == [_JSON_RESPONSE]
    assert list(provider.generate_response_with_image_stream("p", b"img")) == [_JSON_RESPONSE]
