"""tests/test_tags.py — /api/tags/suggest と /api/tags/categories のテスト"""

import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import routes.tags as tags_routes  # noqa: E402

SAMPLE_TAGS = {
    "version": 1,
    "tags": [
        {"name": "masterpiece", "cat": "quality", "a": ["masterwork"], "p": 100},
        {"name": "best quality", "cat": "quality", "a": [], "p": 90},
        {"name": "1girl", "cat": "people", "a": ["one girl"], "p": 80},
        {"name": "girl with hat", "cat": "people", "a": [], "p": 10},
        {"name": "cat ears", "cat": "feature", "a": ["nekomimi"], "p": 50},
        {"name": "catastrophe", "cat": "misc", "a": [], "p": 5},
        {"name": "background", "cat": "scene", "a": ["bg", "scenery cat"], "p": 30},
    ],
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """tags.json を一時ファイルに差し替えた TestClient を生成"""
    tags_file = tmp_path / "tags.json"
    tags_file.write_text(json.dumps(SAMPLE_TAGS), encoding="utf-8")

    monkeypatch.setattr(tags_routes, "_TAGS_FILE", tags_file)
    monkeypatch.setattr(tags_routes, "_tags_cache", None)

    app = FastAPI()
    app.include_router(tags_routes.router)

    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_missing_file(tmp_path, monkeypatch):
    """tags.json が存在しない場合の TestClient を生成"""
    missing_file = tmp_path / "does_not_exist.json"

    monkeypatch.setattr(tags_routes, "_TAGS_FILE", missing_file)
    monkeypatch.setattr(tags_routes, "_tags_cache", None)

    app = FastAPI()
    app.include_router(tags_routes.router)

    with TestClient(app) as c:
        yield c


# ------------------------------------------------------------------ #
# Basic suggestion behavior
# ------------------------------------------------------------------ #


def test_suggest_known_query_returns_results(client):
    """既知のクエリで候補が返ること"""
    response = client.get("/api/tags/suggest", params={"q": "cat"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["tags"]) > 0
    names = [t["name"] for t in data["tags"]]
    assert "cat ears" in names
    assert "catastrophe" in names


def test_suggest_empty_query_returns_422(client):
    """空のクエリ文字列は 422 を返す（min_length=1）"""
    response = client.get("/api/tags/suggest", params={"q": ""})
    assert response.status_code == 422


def test_suggest_missing_query_returns_422(client):
    """q パラメータ未指定は 422 を返す"""
    response = client.get("/api/tags/suggest")
    assert response.status_code == 422


def test_suggest_category_filter(client):
    """category フィルタが正しく適用されること"""
    response = client.get("/api/tags/suggest", params={"q": "a", "category": "quality"})
    assert response.status_code == 200
    data = response.json()
    assert all(t["cat"] == "quality" for t in data["tags"])
    names = [t["name"] for t in data["tags"]]
    assert "masterpiece" in names
    assert "1girl" not in names


def test_suggest_limit_parameter(client):
    """limit パラメータで結果数が制限されること"""
    response = client.get("/api/tags/suggest", params={"q": "a", "limit": 2})
    assert response.status_code == 200
    data = response.json()
    assert len(data["tags"]) <= 2


def test_suggest_limit_over_max_returns_422(client):
    """limit が 100 を超えると 422 を返す"""
    response = client.get("/api/tags/suggest", params={"q": "a", "limit": 101})
    assert response.status_code == 422


# ------------------------------------------------------------------ #
# Ranking
# ------------------------------------------------------------------ #


def test_suggest_ranking_exact_prefix_substring(client):
    """完全一致 > 前方一致 > 部分一致の順でランキングされること"""
    response = client.get("/api/tags/suggest", params={"q": "cat ears", "limit": 100})
    assert response.status_code == 200
    names = [t["name"] for t in response.json()["tags"]]
    # "cat ears" exact-matches the "cat ears" tag, so it should rank first.
    assert names[0] == "cat ears"


def test_suggest_ranking_prefix_before_substring(client):
    """前方一致が部分一致より上位に来ること"""
    response = client.get("/api/tags/suggest", params={"q": "cat", "limit": 100})
    assert response.status_code == 200
    names = [t["name"] for t in response.json()["tags"]]
    # "cat ears" starts with "cat" (prefix match, 5000+50=5050)
    # "catastrophe" starts with "cat" (prefix match, 5000+5=5005)
    # "background" matches via alias substring "scenery cat" (500+30=530)
    assert names.index("cat ears") < names.index("background")
    assert names.index("catastrophe") < names.index("background")


def test_suggest_ranking_alias_match(client):
    """エイリアスの前方一致／部分一致が検出されること"""
    response = client.get("/api/tags/suggest", params={"q": "nekomimi"})
    assert response.status_code == 200
    names = [t["name"] for t in response.json()["tags"]]
    assert "cat ears" in names


def test_suggest_case_insensitive(client):
    """大文字小文字を区別しないこと"""
    response = client.get("/api/tags/suggest", params={"q": "MASTER"})
    assert response.status_code == 200
    names = [t["name"] for t in response.json()["tags"]]
    assert "masterpiece" in names


# ------------------------------------------------------------------ #
# Categories endpoint
# ------------------------------------------------------------------ #


def test_categories_returns_distinct_list(client):
    """/api/tags/categories は重複のないカテゴリ一覧を返す"""
    response = client.get("/api/tags/categories")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert set(data["categories"]) == {"quality", "people", "feature", "misc", "scene"}
    assert len(data["categories"]) == len(set(data["categories"]))


# ------------------------------------------------------------------ #
# Missing file handling
# ------------------------------------------------------------------ #


def test_suggest_missing_tags_file_returns_empty(client_missing_file):
    """tags.json が存在しない場合は空の結果を返す（エラーにしない）"""
    response = client_missing_file.get("/api/tags/suggest", params={"q": "cat"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["tags"] == []


def test_categories_missing_tags_file_returns_empty(client_missing_file):
    """tags.json が存在しない場合 categories は空配列を返す"""
    response = client_missing_file.get("/api/tags/categories")
    assert response.status_code == 200
    assert response.json()["categories"] == []
