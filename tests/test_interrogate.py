"""tests/test_interrogate.py — CLIP Interrogator / WD14 Tagger 連携 (issue #81) のテスト

- SDClient.interrogate (単体テスト、requests をモック)
- POST /api/interrogate (SD の interrogate API をラップするエンドポイント)
- POST /api/generate-prompts の analysis_mode (llm / tagger / hybrid)
- LLMCache のキー後方互換性 (mode / tagger_model 追加分)
"""

import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import deps
import history as hist
import routes.sd as sd_routes
from main import app
from sd_client import SDClient

client = TestClient(app)


def _png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (1, 1), color=(0, 128, 255)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def disable_rate_limit(monkeypatch):
    import config

    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)


@pytest.fixture(autouse=True)
def temp_history_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_history.db"
    monkeypatch.setattr(hist, "DB_PATH", db_file)
    yield db_file


@pytest.fixture(autouse=True)
def no_cache(monkeypatch):
    """キャッシュは常にミスさせる（キャッシュキーのテストでは個別に上書き）"""
    cache = MagicMock()
    cache.get.return_value = None
    monkeypatch.setattr(deps, "llm_cache", cache)
    yield cache


# ------------------------------------------------------------------ #
# SDClient.interrogate（単体テスト、requests をモック）
# ------------------------------------------------------------------ #


class TestSDClientInterrogate:
    def test_interrogate_success_clip(self, monkeypatch):
        sd = SDClient(base_url="http://fake-sd:7860")

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"caption": "1girl, solo, blue eyes, masterpiece"}

        captured_payload = {}

        def fake_post(url, json=None, timeout=None):
            captured_payload.update(json or {})
            assert url == "http://fake-sd:7860/sdapi/v1/interrogate"
            assert timeout == 60
            return mock_response

        monkeypatch.setattr(requests, "post", fake_post)

        caption = sd.interrogate(b"fake-image-bytes", model="clip")
        assert caption == "1girl, solo, blue eyes, masterpiece"
        assert captured_payload["model"] == "clip"
        assert "image" in captured_payload

    def test_interrogate_success_deepdanbooru(self, monkeypatch):
        sd = SDClient(base_url="http://fake-sd:7860")

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"caption": "1girl, cat_ears, tail"}

        captured_payload = {}

        def fake_post(url, json=None, timeout=None):
            captured_payload.update(json or {})
            return mock_response

        monkeypatch.setattr(requests, "post", fake_post)

        caption = sd.interrogate(b"fake-image-bytes", model="deepdanbooru")
        assert caption == "1girl, cat_ears, tail"
        assert captured_payload["model"] == "deepdanbooru"

    def test_interrogate_missing_caption_returns_none(self, monkeypatch):
        sd = SDClient(base_url="http://fake-sd:7860")

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {}

        monkeypatch.setattr(requests, "post", lambda *a, **k: mock_response)

        assert sd.interrogate(b"fake-image-bytes") is None

    def test_interrogate_connection_error_raises(self, monkeypatch):
        sd = SDClient(base_url="http://fake-sd:7860")

        # retry デコレータの実待機を無くしてテストを高速化する
        monkeypatch.setattr("retry.time.sleep", lambda *a, **k: None)

        def fake_post(*a, **k):
            raise requests.exceptions.ConnectionError("refused")

        monkeypatch.setattr(requests, "post", fake_post)

        with pytest.raises(ConnectionError):
            sd.interrogate(b"fake-image-bytes")

    def test_interrogate_timeout_raises(self, monkeypatch):
        sd = SDClient(base_url="http://fake-sd:7860")
        monkeypatch.setattr("retry.time.sleep", lambda *a, **k: None)

        def fake_post(*a, **k):
            raise requests.exceptions.Timeout("too slow")

        monkeypatch.setattr(requests, "post", fake_post)

        with pytest.raises(TimeoutError):
            sd.interrogate(b"fake-image-bytes")


# ------------------------------------------------------------------ #
# POST /api/interrogate
# ------------------------------------------------------------------ #


class TestInterrogateEndpoint:
    def _install_sd_mock(self, monkeypatch, mock_sd):
        monkeypatch.setattr(deps, "sd_client", mock_sd)
        monkeypatch.setattr(sd_routes, "sd_client", mock_sd)

    def test_interrogate_endpoint_success(self, monkeypatch):
        mock_sd = MagicMock()
        mock_sd.interrogate.return_value = "1girl, solo, blue eyes, smiling"
        self._install_sd_mock(monkeypatch, mock_sd)

        r = client.post(
            "/api/interrogate",
            files={"file": ("test.png", _png_bytes(), "image/png")},
            data={"model": "clip"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["caption"] == "1girl, solo, blue eyes, smiling"
        assert data["tags"] == ["1girl", "solo", "blue eyes", "smiling"]
        mock_sd.interrogate.assert_called_once()
        assert mock_sd.interrogate.call_args.args[1] == "clip"

    def test_interrogate_endpoint_default_model_is_clip(self, monkeypatch):
        mock_sd = MagicMock()
        mock_sd.interrogate.return_value = "tag1, tag2"
        self._install_sd_mock(monkeypatch, mock_sd)

        r = client.post("/api/interrogate", files={"file": ("test.png", _png_bytes(), "image/png")})
        assert r.status_code == 200
        assert mock_sd.interrogate.call_args.args[1] == "clip"

    def test_interrogate_endpoint_invalid_model_returns_400(self, monkeypatch):
        mock_sd = MagicMock()
        self._install_sd_mock(monkeypatch, mock_sd)

        r = client.post(
            "/api/interrogate",
            files={"file": ("test.png", _png_bytes(), "image/png")},
            data={"model": "wd14-not-supported"},
        )
        assert r.status_code == 400
        mock_sd.interrogate.assert_not_called()

    def test_interrogate_endpoint_invalid_image_type_returns_400(self, monkeypatch):
        mock_sd = MagicMock()
        self._install_sd_mock(monkeypatch, mock_sd)

        r = client.post(
            "/api/interrogate",
            files={"file": ("test.txt", b"not an image", "text/plain")},
        )
        assert r.status_code == 400

    def test_interrogate_endpoint_sd_unreachable_returns_502(self, monkeypatch):
        mock_sd = MagicMock()
        mock_sd.interrogate.side_effect = ConnectionError("Cannot connect to Stable Diffusion API")
        self._install_sd_mock(monkeypatch, mock_sd)

        r = client.post("/api/interrogate", files={"file": ("test.png", _png_bytes(), "image/png")})
        assert r.status_code == 502

    def test_interrogate_endpoint_timeout_returns_504(self, monkeypatch):
        mock_sd = MagicMock()
        mock_sd.interrogate.side_effect = TimeoutError("timed out")
        self._install_sd_mock(monkeypatch, mock_sd)

        r = client.post("/api/interrogate", files={"file": ("test.png", _png_bytes(), "image/png")})
        assert r.status_code == 504

    def test_interrogate_endpoint_empty_caption_returns_502(self, monkeypatch):
        mock_sd = MagicMock()
        mock_sd.interrogate.return_value = ""
        self._install_sd_mock(monkeypatch, mock_sd)

        r = client.post("/api/interrogate", files={"file": ("test.png", _png_bytes(), "image/png")})
        assert r.status_code == 502


# ------------------------------------------------------------------ #
# POST /api/generate-prompts — analysis_mode
# ------------------------------------------------------------------ #


class TestGeneratePromptsAnalysisMode:
    def _install(self, monkeypatch, mock_pg=None, mock_sd=None, mock_llm=None):
        if mock_pg is not None:
            monkeypatch.setattr(deps, "prompt_generator", mock_pg)
        if mock_sd is not None:
            monkeypatch.setattr(deps, "sd_client", mock_sd)
        if mock_llm is not None:
            monkeypatch.setattr(deps, "llm_client", mock_llm)

    def test_invalid_analysis_mode_returns_400(self, monkeypatch):
        r = client.post(
            "/api/generate-prompts",
            files={"file": ("test.png", _png_bytes(), "image/png")},
            data={"analysis_mode": "not-a-real-mode"},
        )
        assert r.status_code == 400

    def test_invalid_tagger_model_returns_400(self, monkeypatch):
        r = client.post(
            "/api/generate-prompts",
            files={"file": ("test.png", _png_bytes(), "image/png")},
            data={"analysis_mode": "tagger", "tagger_model": "not-a-real-model"},
        )
        assert r.status_code == 400

    def test_llm_mode_does_not_call_interrogate(self, monkeypatch):
        mock_pg = MagicMock()
        mock_pg.generate_prompts.return_value = {
            "positive": "llm positive",
            "negative": "llm negative",
            "status": "success",
        }
        mock_sd = MagicMock()
        self._install(monkeypatch, mock_pg=mock_pg, mock_sd=mock_sd)

        r = client.post(
            "/api/generate-prompts",
            files={"file": ("test.png", _png_bytes(), "image/png")},
            data={"analysis_mode": "llm"},
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["positive"] == "llm positive"
        mock_sd.interrogate.assert_not_called()
        # tagger_tags は空文字で LLM に渡される
        assert mock_pg.generate_prompts.call_args.kwargs["tagger_tags"] == ""

    def test_tagger_mode_builds_from_tags_without_llm(self, monkeypatch):
        mock_pg = MagicMock()
        mock_pg.build_tagger_prompt.return_value = {
            "positive": "1girl, solo, best quality",
            "negative": "lowres, bad anatomy",
            "status": "success",
        }
        mock_sd = MagicMock()
        mock_sd.interrogate.return_value = "1girl, solo"
        self._install(monkeypatch, mock_pg=mock_pg, mock_sd=mock_sd)

        r = client.post(
            "/api/generate-prompts",
            files={"file": ("test.png", _png_bytes(), "image/png")},
            data={"analysis_mode": "tagger", "tagger_model": "deepdanbooru"},
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["positive"] == "1girl, solo, best quality"

        mock_sd.interrogate.assert_called_once()
        assert mock_sd.interrogate.call_args.args[1] == "deepdanbooru"

        mock_pg.build_tagger_prompt.assert_called_once()
        assert mock_pg.build_tagger_prompt.call_args.args[0] == "1girl, solo"
        # tagger モードは LLM を使わない
        mock_pg.generate_prompts.assert_not_called()

    def test_tagger_mode_interrogate_unreachable_returns_502(self, monkeypatch):
        mock_pg = MagicMock()
        mock_sd = MagicMock()
        mock_sd.interrogate.side_effect = ConnectionError("no SD")
        self._install(monkeypatch, mock_pg=mock_pg, mock_sd=mock_sd)

        r = client.post(
            "/api/generate-prompts",
            files={"file": ("test.png", _png_bytes(), "image/png")},
            data={"analysis_mode": "tagger"},
        )
        assert r.status_code == 502
        mock_pg.build_tagger_prompt.assert_not_called()

    def test_hybrid_mode_passes_tags_to_llm(self, monkeypatch):
        mock_pg = MagicMock()
        mock_pg.generate_prompts.return_value = {
            "positive": "hybrid positive",
            "negative": "hybrid negative",
            "status": "success",
        }
        mock_sd = MagicMock()
        mock_sd.interrogate.return_value = "1girl, cat ears, blue eyes"
        self._install(monkeypatch, mock_pg=mock_pg, mock_sd=mock_sd)

        r = client.post(
            "/api/generate-prompts",
            files={"file": ("test.png", _png_bytes(), "image/png")},
            data={"analysis_mode": "hybrid", "tagger_model": "clip"},
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["positive"] == "hybrid positive"

        mock_sd.interrogate.assert_called_once()
        assert mock_sd.interrogate.call_args.args[1] == "clip"

        mock_pg.generate_prompts.assert_called_once()
        assert mock_pg.generate_prompts.call_args.kwargs["tagger_tags"] == "1girl, cat ears, blue eyes"

    def test_hybrid_mode_uses_cache(self, monkeypatch, no_cache):
        mock_pg = MagicMock()
        mock_sd = MagicMock()
        mock_sd.interrogate.return_value = "1girl"
        self._install(monkeypatch, mock_pg=mock_pg, mock_sd=mock_sd)

        no_cache.get.return_value = {
            "positive": "cached hybrid positive",
            "negative": "cached hybrid negative",
            "status": "success",
        }

        r = client.post(
            "/api/generate-prompts",
            files={"file": ("test.png", _png_bytes(), "image/png")},
            data={"analysis_mode": "hybrid"},
        )
        assert r.status_code == 200
        assert r.json()["data"]["positive"] == "cached hybrid positive"
        mock_pg.generate_prompts.assert_not_called()

        # get() 呼び出しに mode / tagger_model が渡されている
        _, kwargs = no_cache.get.call_args
        assert kwargs["mode"] == "hybrid"
        assert kwargs["tagger_model"] == "clip"

    def test_tagger_mode_never_touches_cache(self, monkeypatch, no_cache):
        mock_pg = MagicMock()
        mock_pg.build_tagger_prompt.return_value = {
            "positive": "p",
            "negative": "n",
            "status": "success",
        }
        mock_sd = MagicMock()
        mock_sd.interrogate.return_value = "1girl"
        self._install(monkeypatch, mock_pg=mock_pg, mock_sd=mock_sd)

        r = client.post(
            "/api/generate-prompts",
            files={"file": ("test.png", _png_bytes(), "image/png")},
            data={"analysis_mode": "tagger"},
        )
        assert r.status_code == 200
        no_cache.get.assert_not_called()
        no_cache.set.assert_not_called()


# ------------------------------------------------------------------ #
# LLMCache — mode / tagger_model 追加による後方互換性
# ------------------------------------------------------------------ #


class TestCacheKeyBackwardCompatibility:
    def _make_cache(self, tmp_path, monkeypatch):
        import cache as cache_module

        monkeypatch.setattr(cache_module, "DB_PATH", tmp_path / "cache.db")
        return cache_module.LLMCache(ttl_seconds=3600, enabled=True)

    def test_default_mode_key_matches_legacy_call(self, tmp_path, monkeypatch):
        """mode を渡さない呼び出しと mode='llm' を明示した呼び出しは同一キーになる"""
        c = self._make_cache(tmp_path, monkeypatch)
        key_legacy = c._make_key(b"img", None, "anime", "vibrant", "high", provider="p", model="m")
        key_explicit_llm = c._make_key(
            b"img", None, "anime", "vibrant", "high", provider="p", model="m", mode="llm", tagger_model=""
        )
        assert key_legacy == key_explicit_llm

    def test_hybrid_mode_key_differs_from_llm(self, tmp_path, monkeypatch):
        c = self._make_cache(tmp_path, monkeypatch)
        key_llm = c._make_key(b"img", None, "anime", "vibrant", "high", provider="p", model="m", mode="llm")
        key_hybrid = c._make_key(
            b"img", None, "anime", "vibrant", "high", provider="p", model="m", mode="hybrid", tagger_model="clip"
        )
        assert key_llm != key_hybrid

    def test_hybrid_mode_key_differs_by_tagger_model(self, tmp_path, monkeypatch):
        c = self._make_cache(tmp_path, monkeypatch)
        key_clip = c._make_key(b"img", None, "", "", "high", mode="hybrid", tagger_model="clip")
        key_deepdanbooru = c._make_key(b"img", None, "", "", "high", mode="hybrid", tagger_model="deepdanbooru")
        assert key_clip != key_deepdanbooru

    def test_get_set_roundtrip_with_mode(self, tmp_path, monkeypatch):
        c = self._make_cache(tmp_path, monkeypatch)
        result = {"positive": "p", "negative": "n", "status": "success"}
        c.set(b"img", None, "", "", "high", result, mode="hybrid", tagger_model="clip")

        assert c.get(b"img", None, "", "", "high", mode="hybrid", tagger_model="clip") == result
        # 異なる tagger_model はミスする
        assert c.get(b"img", None, "", "", "high", mode="hybrid", tagger_model="deepdanbooru") is None
        # 従来通りの呼び出し (mode 省略) は別キー空間なのでミスする
        assert c.get(b"img", None, "", "", "high") is None
