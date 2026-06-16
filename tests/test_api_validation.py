"""tests/test_api_validation.py — FastAPI エンドポイントの入力バリデーションテスト"""
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_png_bytes() -> bytes:
    """テスト用の 1×1 PNG バイト列を生成"""
    buf = BytesIO()
    Image.new("RGB", (1, 1), color=(255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def client():
    """モック済みクライアントを注入した TestClient を生成"""
    import main as main_module

    # SD/LLM クライアントをモックして実ネットワーク接続を回避
    mock_sd = MagicMock()
    mock_sd.get_progress.return_value = None  # SD 未到達を模擬
    mock_sd.is_available.return_value = False
    mock_sd.txt2img.return_value = []
    mock_sd.save_images.return_value = []

    mock_llm = MagicMock()
    mock_llm.is_available.return_value = False

    mock_pg = MagicMock()
    mock_pg.generate_prompts.return_value = {
        "positive": "test positive",
        "negative": "test negative",
        "status": "success",
    }
    mock_pg.generate_prompts_text_only.return_value = {
        "positive": "test positive",
        "negative": "test negative",
        "status": "success",
    }
    mock_pg.refine_prompt.return_value = {
        "positive": "refined",
        "negative": "refined neg",
        "changes": "",
        "status": "success",
    }

    main_module.sd_client = mock_sd
    main_module.llm_client = mock_llm
    main_module.prompt_generator = mock_pg

    with TestClient(main_module.app) as c:
        yield c


# ------------------------------------------------------------------ #
# BE-3: 数値パラメータの 422 バリデーション
# ------------------------------------------------------------------ #

def test_sd_generate_bad_width_returns_422(client):
    """/api/sd/generate に不正な width を渡すと 422 を返す"""
    payload = {
        "positive": "a cat",
        "width": "abc",  # 不正な値
        "height": 512,
    }
    response = client.post("/api/sd/generate", json=payload)
    assert response.status_code == 422
    assert "width" in response.json()["detail"]


def test_sd_generate_bad_steps_returns_422(client):
    payload = {"positive": "a cat", "steps": "not_a_number"}
    response = client.post("/api/sd/generate", json=payload)
    assert response.status_code == 422


def test_sd_generate_bad_cfg_scale_returns_422(client):
    payload = {"positive": "a cat", "cfg_scale": "nan_value"}
    response = client.post("/api/sd/generate", json=payload)
    assert response.status_code == 422


# ------------------------------------------------------------------ #
# BE-3: date パラメータのバリデーション
# ------------------------------------------------------------------ #

def test_outputs_bad_date_returns_422(client):
    """/api/outputs に不正な date を渡すと 422 を返す"""
    response = client.get("/api/outputs", params={"date": "not-a-date"})
    assert response.status_code == 422


def test_outputs_valid_date_accepted(client):
    """/api/outputs に正しい日付形式を渡すと 400 未満を返す（ディレクトリなしで 200）"""
    response = client.get("/api/outputs", params={"date": "2024-01-15"})
    assert response.status_code == 200


# ------------------------------------------------------------------ #
# BE-3: description 長さ制限
# ------------------------------------------------------------------ #

def test_generate_prompts_text_oversized_description_returns_422(client):
    """/api/generate-prompts-text に 5000 文字超の description を渡すと 422"""
    payload = {"description": "x" * 5001}
    response = client.post("/api/generate-prompts-text", json=payload)
    assert response.status_code == 422


def test_generate_prompts_text_exact_limit_accepted(client):
    """/api/generate-prompts-text に 5000 文字の description は受け入れられる"""
    payload = {"description": "x" * 5000}
    response = client.post("/api/generate-prompts-text", json=payload)
    # 200 OK（モックされた LLM が返す）
    assert response.status_code == 200


def test_refine_prompt_oversized_positive_returns_422(client):
    """/api/refine-prompt に 10000 文字超の positive を渡すと 422"""
    payload = {"positive": "y" * 10001}
    response = client.post("/api/refine-prompt", json=payload)
    assert response.status_code == 422


def test_refine_prompt_exact_limit_accepted(client):
    """/api/refine-prompt に 10000 文字の positive は受け入れられる"""
    payload = {"positive": "y" * 10000}
    response = client.post("/api/refine-prompt", json=payload)
    assert response.status_code == 200


# ------------------------------------------------------------------ #
# BE-2: /api/sd/progress
# ------------------------------------------------------------------ #

def test_sd_progress_unavailable_shape(client):
    """/api/sd/progress は SD 未到達時に available=False の形で返す"""
    response = client.get("/api/sd/progress")
    assert response.status_code == 200
    data = response.json()
    assert "available" in data
    assert "progress" in data
    assert "eta_relative" in data
    assert "state" in data
    # モックが None を返すので available=False
    assert data["available"] is False
    assert data["progress"] == 0.0
    assert data["eta_relative"] == 0.0
    assert data["state"] == {}


# ------------------------------------------------------------------ #
# BE-4: /health の形状確認
# ------------------------------------------------------------------ #

def test_health_shape(client):
    """/health は status, components, uptime_seconds フィールドを含む"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "components" in data
    assert "uptime_seconds" in data
    assert "llm" in data["components"]
    assert "sd_api" in data["components"]
    # モックが False を返すので degraded
    assert data["status"] == "degraded"


# ------------------------------------------------------------------ #
# Tags API
# ------------------------------------------------------------------ #

def test_add_tags_to_history(client):
    """POST /api/history/{id}/tags adds tags"""
    # First create a history entry via text generation
    response = client.post("/api/generate-prompts-text", json={"description": "test"})
    assert response.status_code == 200
    # Get the history to find the ID
    hist_r = client.get("/api/history", params={"limit": 1})
    items = hist_r.json()["items"]
    if not items:
        pytest.skip("No history items available")
    item_id = items[0]["id"]
    # Add tags
    r = client.post(f"/api/history/{item_id}/tags", json={"tags": ["portrait", "test"]})
    assert r.status_code == 200
    assert "tags" in r.json()


def test_add_tags_empty_list_returns_400(client):
    """POST /api/history/{id}/tags with empty tags returns 400"""
    r = client.post("/api/history/1/tags", json={"tags": []})
    assert r.status_code == 400


def test_add_tags_not_found_returns_404(client):
    """POST /api/history/{id}/tags with non-existent ID returns 404"""
    r = client.post("/api/history/99999/tags", json={"tags": ["test"]})
    assert r.status_code == 404


def test_list_all_tags(client):
    """GET /api/tags returns tag list"""
    r = client.get("/api/tags")
    assert r.status_code == 200
    assert "tags" in r.json()


def test_history_with_tag_filter(client):
    """GET /api/history with tag filter"""
    r = client.get("/api/history", params={"tag": "nonexistent_tag_xyz"})
    assert r.status_code == 200
    assert r.json()["items"] == []
