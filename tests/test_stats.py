"""tests/test_stats.py — /api/stats のレスポンス構造と集計値のテスト"""

import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import history as hist  # noqa: E402
import routes.stats as stats_routes  # noqa: E402


def _write_metadata(date_dir: Path, filename: str, model: str, sampler: str, image_count: int = 1):
    date_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "timestamp": "20260101_000000",
        "mode": "txt2img",
        "image_count": image_count,
        "parameters": {
            "positive_prompt": "1girl",
            "negative_prompt": "blurry",
            "model": model,
            "sampler": sampler,
        },
        "files": [{"filename": f"sd_{i:03d}.png", "index": i} for i in range(image_count)],
    }
    (date_dir / filename).write_text(json.dumps(meta), encoding="utf-8")


@pytest.fixture
def client(tmp_path, monkeypatch):
    """一時 history DB + 一時 outputs ディレクトリを使う TestClient を生成"""
    db_file = tmp_path / "test_history.db"
    monkeypatch.setattr(hist, "DB_PATH", db_file)

    outputs_dir = tmp_path / "outputs"
    monkeypatch.setattr(stats_routes, "_OUTPUTS_DIR", outputs_dir)

    app = FastAPI()
    app.include_router(stats_routes.router)

    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ #
# タグ正規化
# ------------------------------------------------------------------ #


def test_normalize_tag_strips_weight_syntax():
    assert stats_routes._normalize_tag("(masterpiece:1.2)") == "masterpiece"
    assert stats_routes._normalize_tag("((cute))") == "cute"
    assert stats_routes._normalize_tag("[low quality]") == "low quality"
    assert stats_routes._normalize_tag("  Plain Tag  ") == "plain tag"
    assert stats_routes._normalize_tag("") == ""


def test_extract_tags_splits_and_normalizes():
    tags = stats_routes._extract_tags("1girl, (masterpiece:1.3), ((cute)), ")
    assert tags == ["1girl", "masterpiece", "cute"]


# ------------------------------------------------------------------ #
# レスポンス構造・空の状態
# ------------------------------------------------------------------ #


def test_stats_empty_state(client):
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total_history"] == 0
    assert data["total_generated_images"] == 0
    assert data["favorite_rate"] == 0.0
    assert data["avg_prompt_length"] == 0.0
    assert data["avg_tag_count"] == 0.0
    assert data["top_tags"] == {"positive": [], "negative": []}
    assert data["styles"] == {"total": 0, "counts": []}
    assert data["models"] == []
    assert data["samplers"] == []
    assert len(data["activity"]["daily"]) == 30
    assert all(day["count"] == 0 for day in data["activity"]["daily"])
    assert data["activity"]["weekly"] == [] or all(w["count"] == 0 for w in data["activity"]["weekly"])


def test_stats_invalid_top_n_returns_400(client):
    response = client.get("/api/stats", params={"top_n": 0})
    assert response.status_code == 400


# ------------------------------------------------------------------ #
# 履歴の集計
# ------------------------------------------------------------------ #


def test_stats_top_tags_positive_negative(client):
    hist.save_history(positive="1girl, (masterpiece:1.2), cute", negative="blurry, (bad anatomy:1.1)")
    hist.save_history(positive="1girl, outdoors", negative="blurry")

    response = client.get("/api/stats", params={"top_n": 5})
    data = response.json()

    positive_tags = {t["tag"]: t["count"] for t in data["top_tags"]["positive"]}
    negative_tags = {t["tag"]: t["count"] for t in data["top_tags"]["negative"]}

    assert positive_tags["1girl"] == 2
    assert positive_tags["masterpiece"] == 1
    assert positive_tags["cute"] == 1
    assert negative_tags["blurry"] == 2
    assert negative_tags["bad anatomy"] == 1


def test_stats_top_n_limits_results(client):
    hist.save_history(positive="a, b, c, d, e", negative="n")
    response = client.get("/api/stats", params={"top_n": 2})
    data = response.json()
    assert len(data["top_tags"]["positive"]) == 2


def test_stats_style_tone_quality_breakdown(client):
    hist.save_history(positive="p1", negative="n", style="anime", tone="vibrant", quality="high")
    hist.save_history(positive="p2", negative="n", style="anime", tone="warm", quality="high")
    hist.save_history(positive="p3", negative="n", style="photorealistic", tone="warm", quality="ultra")

    response = client.get("/api/stats")
    data = response.json()

    styles = {c["value"]: c for c in data["styles"]["counts"]}
    assert data["styles"]["total"] == 3
    assert styles["anime"]["count"] == 2
    assert styles["anime"]["percent"] == pytest.approx(66.7, abs=0.1)
    assert styles["photorealistic"]["count"] == 1

    qualities = {c["value"]: c["count"] for c in data["quality_levels"]["counts"]}
    assert qualities["high"] == 2
    assert qualities["ultra"] == 1


def test_stats_favorite_rate(client):
    r1 = hist.save_history(positive="p1", negative="n")
    hist.save_history(positive="p2", negative="n")
    hist.toggle_favorite(r1)

    response = client.get("/api/stats")
    data = response.json()
    assert data["favorite_count"] == 1
    assert data["favorite_rate"] == 50.0


def test_stats_avg_prompt_length_and_tag_count(client):
    r1 = hist.save_history(positive="abcde", negative="fghij")  # 10 chars total
    hist.add_tags(r1, ["portrait", "anime"])
    hist.save_history(positive="ab", negative="cd")  # 4 chars total, no tags

    response = client.get("/api/stats")
    data = response.json()
    assert data["total_history"] == 2
    assert data["avg_prompt_length"] == pytest.approx(7.0)  # (10 + 4) / 2
    assert data["avg_tag_count"] == pytest.approx(1.0)  # (2 + 0) / 2


# ------------------------------------------------------------------ #
# outputs メタデータの集計
# ------------------------------------------------------------------ #


def test_stats_model_sampler_generation_counts(client, tmp_path):
    outputs_dir = tmp_path / "outputs"
    date_dir = outputs_dir / "2026-01-01"
    _write_metadata(date_dir, "sd_20260101_000000_metadata.json", model="modelA", sampler="Euler a", image_count=2)
    _write_metadata(date_dir, "sd_20260101_000001_metadata.json", model="modelB", sampler="Euler a", image_count=1)

    response = client.get("/api/stats")
    data = response.json()

    models = {m["value"]: m["count"] for m in data["models"]}
    samplers = {s["value"]: s["count"] for s in data["samplers"]}

    assert models["modelA"] == 2
    assert models["modelB"] == 1
    assert samplers["Euler a"] == 3
    assert data["total_generated_images"] == 3


def test_stats_daily_activity_last_30_days(client, tmp_path):
    from datetime import date

    outputs_dir = tmp_path / "outputs"
    today_str = date.today().isoformat()
    date_dir = outputs_dir / today_str
    _write_metadata(date_dir, "sd_today_metadata.json", model="modelA", sampler="Euler a", image_count=4)

    response = client.get("/api/stats")
    data = response.json()

    daily = {d["date"]: d["count"] for d in data["activity"]["daily"]}
    assert len(data["activity"]["daily"]) == 30
    assert daily[today_str] == 4
    # Dates should be in ascending order (oldest first)
    dates_list = [d["date"] for d in data["activity"]["daily"]]
    assert dates_list == sorted(dates_list)
    assert dates_list[-1] == today_str


def test_stats_weekly_aggregates_daily(client, tmp_path):
    from datetime import date

    outputs_dir = tmp_path / "outputs"
    today_str = date.today().isoformat()
    date_dir = outputs_dir / today_str
    _write_metadata(date_dir, "sd_today_metadata.json", model="modelA", sampler="Euler a", image_count=5)

    response = client.get("/api/stats")
    data = response.json()
    weekly_total = sum(w["count"] for w in data["activity"]["weekly"])
    assert weekly_total == 5


def test_stats_outputs_dir_missing_returns_empty(client):
    """outputs ディレクトリ自体が存在しない場合でもエラーにならない"""
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["models"] == []
    assert data["total_generated_images"] == 0
