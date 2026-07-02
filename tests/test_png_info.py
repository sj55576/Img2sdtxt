"""tests/test_png_info.py — PNG Info インポート機能（Issue #80）のテスト

parse_a1111_parameters() の単体テストと、/api/png-info エンドポイントのテストを含む。
"""

import sys
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from PIL.PngImagePlugin import PngInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import routes.png_info as png_info_routes  # noqa: E402
from sd_client import parse_a1111_parameters  # noqa: E402


def _make_png_bytes(parameters: str = None) -> bytes:
    """テスト用 PNG バイト列を生成。parameters を渡すと tEXt チャンクに埋め込む。"""
    buf = BytesIO()
    img = Image.new("RGB", (4, 4), color=(255, 0, 0))
    if parameters is not None:
        info = PngInfo()
        info.add_text("parameters", parameters)
        img.save(buf, format="PNG", pnginfo=info)
    else:
        img.save(buf, format="PNG")
    return buf.getvalue()


# ------------------------------------------------------------------ #
# parse_a1111_parameters 単体テスト
# ------------------------------------------------------------------ #


def test_parse_full_sample():
    """複数行ポジティブ／ネガティブ＋設定行（既知キー＋extras）を正しく解析する"""
    raw = (
        "a beautiful anime girl, masterpiece, best quality\n"
        "extremely detailed\n"
        "Negative prompt: bad hands, blurry\n"
        "extra negative line\n"
        "Steps: 20, Sampler: DPM++ 2M Karras, CFG scale: 7.5, Seed: 123456789, "
        "Size: 512x768, Model: sd_xl_base, Model hash: abc123, Denoising strength: 0.6, Clip skip: 2"
    )
    result = parse_a1111_parameters(raw)

    assert result["positive_prompt"] == "a beautiful anime girl, masterpiece, best quality\nextremely detailed"
    assert result["negative_prompt"] == "bad hands, blurry\nextra negative line"
    assert result["steps"] == 20
    assert isinstance(result["steps"], int)
    assert result["sampler"] == "DPM++ 2M Karras"
    assert result["cfg_scale"] == 7.5
    assert isinstance(result["cfg_scale"], float)
    assert result["seed"] == 123456789
    assert isinstance(result["seed"], int)
    assert result["width"] == 512
    assert result["height"] == 768
    assert result["model"] == "sd_xl_base"
    assert result["denoising_strength"] == 0.6
    assert isinstance(result["denoising_strength"], float)
    assert result["extras"]["Model hash"] == "abc123"
    assert result["extras"]["Clip skip"] == "2"
    assert result["raw"] == raw


def test_parse_quoted_value_not_split_by_comma():
    """引用符付き値（カンマを含む）が分割されず1つの extras 値になる"""
    raw = 'a cat\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 1, Lora hashes: "lora1: aaa, lora2: bbb"'
    result = parse_a1111_parameters(raw)

    assert result["extras"]["Lora hashes"] == "lora1: aaa, lora2: bbb"


def test_parse_no_negative_prompt():
    """ネガティブプロンプトが無い場合、negative_prompt キーが存在しない"""
    raw = "a cat sitting on a chair\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 1"
    result = parse_a1111_parameters(raw)

    assert "negative_prompt" not in result
    assert result["positive_prompt"] == "a cat sitting on a chair"


def test_parse_prompt_only_no_settings_line():
    """設定行が無い場合、positive_prompt と raw のみが返る"""
    raw = "a cat sitting on a chair"
    result = parse_a1111_parameters(raw)

    assert result["positive_prompt"] == "a cat sitting on a chair"
    assert result["raw"] == raw
    assert "negative_prompt" not in result
    assert "steps" not in result
    assert "extras" not in result
    assert set(result.keys()) == {"positive_prompt", "raw"}


def test_parse_size_field():
    """Size: 512x768 から width/height が正しく分離される"""
    raw = "a cat\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 1, Size: 512x768"
    result = parse_a1111_parameters(raw)

    assert result["width"] == 512
    assert result["height"] == 768


# ------------------------------------------------------------------ #
# /api/png-info エンドポイントテスト
# ------------------------------------------------------------------ #


@pytest.fixture
def client():
    """png_info ルーターのみを含む最小 FastAPI アプリで TestClient を生成
    （レートリミットミドルウェアは main app にのみ付与されるためここでは不要）"""
    app = FastAPI()
    app.include_router(png_info_routes.router)

    with TestClient(app) as c:
        yield c


def test_png_info_with_metadata(client):
    """parameters チャンクを含む PNG をアップロードすると has_metadata=True で解析結果を返す"""
    raw = "a cat\nNegative prompt: dog\nSteps: 10, Sampler: Euler a, CFG scale: 7, Seed: 42, Size: 256x256"
    png_bytes = _make_png_bytes(raw)

    response = client.post(
        "/api/png-info",
        files={"file": ("test.png", png_bytes, "image/png")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["has_metadata"] is True
    params = data["parameters"]
    assert params["positive_prompt"] == "a cat"
    assert params["negative_prompt"] == "dog"
    assert params["steps"] == 10
    assert params["sampler"] == "Euler a"
    assert params["cfg_scale"] == 7
    assert params["seed"] == 42
    assert params["width"] == 256
    assert params["height"] == 256
    assert params["raw"] == raw


def test_png_info_without_metadata(client):
    """parameters チャンクが無い PNG をアップロードすると has_metadata=False のみ返す"""
    png_bytes = _make_png_bytes()

    response = client.post(
        "/api/png-info",
        files={"file": ("test.png", png_bytes, "image/png")},
    )

    assert response.status_code == 200
    assert response.json() == {"has_metadata": False}


def test_png_info_invalid_content_type_returns_400(client):
    """不正な content_type（例: text/plain）は 400 を返す"""
    response = client.post(
        "/api/png-info",
        files={"file": ("test.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid image type."
