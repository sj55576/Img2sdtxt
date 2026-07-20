"""tests/test_compare.py — プロンプト比較 / A/Bテスト エンドポイントのテスト"""

import json
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import history as hist  # noqa: E402


def _make_png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (1, 1), color=(255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """各テストで新しい一時 DB を使用する"""
    db_file = tmp_path / "test_compare.db"
    monkeypatch.setattr(hist, "DB_PATH", db_file)
    yield db_file


@pytest.fixture
def client(monkeypatch):
    import config
    import deps
    import main as main_module
    import routes.jobs as jobs_routes
    import routes.sd as sd_routes

    config.RATE_LIMIT_ENABLED = False

    mock_sd = MagicMock()
    mock_sd.get_progress.return_value = None
    mock_sd.is_available.return_value = False
    mock_sd.txt2img.return_value = ["base64img"]
    mock_sd.save_images.return_value = []

    mock_llm = MagicMock()
    mock_llm.is_available.return_value = False
    mock_llm.provider_name = "mock"
    mock_llm.model = "mock-model"

    mock_pg = MagicMock()
    mock_pg.generate_prompts.return_value = {
        "positive": "test positive",
        "negative": "test negative",
        "status": "success",
    }

    mock_cache = MagicMock()
    mock_cache.get.return_value = None

    deps.sd_client = mock_sd
    deps.llm_client = mock_llm
    deps.prompt_generator = mock_pg
    deps.llm_cache = mock_cache
    sd_routes.sd_client = mock_sd
    jobs_routes.sd_client = mock_sd

    with TestClient(main_module.app) as c:
        yield c


def _variants_json(items):
    return json.dumps(items)


# ------------------------------------------------------------------ #
# generate-prompts-compare: バリデーション
# ------------------------------------------------------------------ #


def test_compare_invalid_json_returns_400(client):
    files = {"file": ("test.png", _make_png_bytes(), "image/png")}
    data = {"variants": "not json", "save_history": "false"}
    resp = client.post("/api/generate-prompts-compare", files=files, data=data)
    assert resp.status_code == 400


def test_compare_too_few_variants_returns_400(client):
    files = {"file": ("test.png", _make_png_bytes(), "image/png")}
    data = {"variants": _variants_json([{"style": "anime", "tone": "", "quality": "high"}]), "save_history": "false"}
    resp = client.post("/api/generate-prompts-compare", files=files, data=data)
    assert resp.status_code == 400


def test_compare_too_many_variants_returns_400(client):
    files = {"file": ("test.png", _make_png_bytes(), "image/png")}
    items = [{"style": f"s{i}", "tone": "", "quality": "high"} for i in range(5)]
    data = {"variants": _variants_json(items), "save_history": "false"}
    resp = client.post("/api/generate-prompts-compare", files=files, data=data)
    assert resp.status_code == 400


# ------------------------------------------------------------------ #
# generate-prompts-compare: 正常系 / 部分失敗
# ------------------------------------------------------------------ #


def test_compare_success(client):
    files = {"file": ("test.png", _make_png_bytes(), "image/png")}
    items = [
        {"style": "anime", "tone": "vibrant", "quality": "high"},
        {"style": "realistic", "tone": "muted", "quality": "medium"},
    ]
    data = {"variants": _variants_json(items), "save_history": "true"}
    resp = client.post("/api/generate-prompts-compare", files=files, data=data)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["results"]) == 2
    for r in body["results"]:
        assert r["success"] is True
        assert r["positive"] == "test positive"
        assert r["history_id"] is not None


def test_compare_per_variant_failure_isolated(client):
    import deps

    deps.prompt_generator.generate_prompts.side_effect = [
        {"positive": "ok", "negative": "ok neg", "status": "success"},
        {"positive": "", "negative": "", "error": "LLM failed", "status": "error"},
    ]
    files = {"file": ("test.png", _make_png_bytes(), "image/png")}
    items = [
        {"style": "anime", "tone": "", "quality": "high"},
        {"style": "realistic", "tone": "", "quality": "high"},
    ]
    data = {"variants": _variants_json(items), "save_history": "false"}
    resp = client.post("/api/generate-prompts-compare", files=files, data=data)
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"][0]["success"] is True
    assert body["results"][1]["success"] is False
    assert "error" in body["results"][1]


def test_compare_cache_hit_skips_generation(client):
    import deps

    deps.llm_cache.get.return_value = {"positive": "cached pos", "negative": "cached neg", "status": "success"}
    files = {"file": ("test.png", _make_png_bytes(), "image/png")}
    items = [
        {"style": "anime", "tone": "", "quality": "high"},
        {"style": "realistic", "tone": "", "quality": "high"},
    ]
    data = {"variants": _variants_json(items), "save_history": "false"}
    resp = client.post("/api/generate-prompts-compare", files=files, data=data)
    assert resp.status_code == 200
    body = resp.json()
    for r in body["results"]:
        assert r["positive"] == "cached pos"
    deps.prompt_generator.generate_prompts.assert_not_called()


# ------------------------------------------------------------------ #
# A/B テスト
# ------------------------------------------------------------------ #


def _ab_payload(seed=-1):
    return {
        "config_a": {"positive": "a cat", "negative": "", "steps": 20, "cfg_scale": 7.0, "sampler": "Euler a"},
        "config_b": {"positive": "a dog", "negative": "", "steps": 25, "cfg_scale": 8.0, "sampler": "DDIM"},
        "seed": seed,
    }


def test_ab_generate_shared_seed(client):
    import deps

    resp = client.post("/api/compare/ab-generate", json=_ab_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "comparison_id" in body
    assert isinstance(body["seed"], int)
    assert body["a"]["images"] == ["base64img"]
    assert body["b"]["images"] == ["base64img"]

    calls = deps.sd_client.txt2img.call_args_list
    assert len(calls) == 2
    seed_a = calls[0].kwargs["seed"]
    seed_b = calls[1].kwargs["seed"]
    assert seed_a == seed_b == body["seed"]


def test_ab_generate_explicit_seed_used(client):
    resp = client.post("/api/compare/ab-generate", json=_ab_payload(seed=42))
    assert resp.status_code == 200
    body = resp.json()
    assert body["seed"] == 42


def test_ab_generate_sd_connection_error_returns_502(client):
    import deps

    deps.sd_client.txt2img.side_effect = ConnectionError("no sd")
    resp = client.post("/api/compare/ab-generate", json=_ab_payload())
    assert resp.status_code == 502


def test_ab_vote_success(client):
    resp = client.post("/api/compare/ab-generate", json=_ab_payload())
    comparison_id = resp.json()["comparison_id"]

    vote_resp = client.post(f"/api/compare/ab/{comparison_id}/vote", json={"winner": "a", "note": "better colors"})
    assert vote_resp.status_code == 200
    assert vote_resp.json()["success"] is True


def test_ab_vote_invalid_winner_returns_400(client):
    resp = client.post("/api/compare/ab-generate", json=_ab_payload())
    comparison_id = resp.json()["comparison_id"]

    vote_resp = client.post(f"/api/compare/ab/{comparison_id}/vote", json={"winner": "c"})
    assert vote_resp.status_code == 400


def test_ab_vote_not_found_returns_404(client):
    vote_resp = client.post("/api/compare/ab/99999/vote", json={"winner": "a"})
    assert vote_resp.status_code == 404


def test_ab_history(client):
    client.post("/api/compare/ab-generate", json=_ab_payload())
    client.post("/api/compare/ab-generate", json=_ab_payload())

    resp = client.get("/api/compare/ab-history?limit=50")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["comparisons"]) == 2
    assert body["comparisons"][0]["config_a"]["positive"] == "a cat"
