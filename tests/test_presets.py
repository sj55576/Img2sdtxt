"""tests/test_presets.py — 一時ファイルを使った presets モジュールのテスト"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import presets as preset_mgr


@pytest.fixture(autouse=True)
def temp_presets(tmp_path, monkeypatch):
    """各テストで新しい一時プリセットファイルを使用する"""
    presets_file = tmp_path / "presets.json"
    monkeypatch.setattr(preset_mgr, "PRESETS_PATH", presets_file)
    yield presets_file


# ------------------------------------------------------------------ #
# デフォルトプリセット
# ------------------------------------------------------------------ #

def test_load_defaults_when_no_file():
    """ファイルが存在しない場合はデフォルトプリセットを返す"""
    presets = preset_mgr.get_all_presets()
    assert len(presets) > 0
    ids = [p["id"] for p in presets]
    assert "anime" in ids
    assert "photorealistic" in ids


def test_default_presets_have_is_default_flag():
    presets = preset_mgr.get_all_presets()
    for p in presets:
        assert p.get("is_default") is True


# ------------------------------------------------------------------ #
# プリセットの追加
# ------------------------------------------------------------------ #

def test_add_preset():
    new_p = {
        "name": "Test Preset",
        "positive_suffix": "test positive",
        "negative_suffix": "test negative",
    }
    added = preset_mgr.add_preset(new_p)
    assert added["is_default"] is False
    assert "id" in added

    all_presets = preset_mgr.get_all_presets()
    ids = [p["id"] for p in all_presets]
    assert added["id"] in ids


def test_add_preset_with_explicit_id():
    new_p = {
        "id": "my_custom_id",
        "name": "Custom",
        "positive_suffix": "custom positive",
        "negative_suffix": "custom negative",
    }
    added = preset_mgr.add_preset(new_p)
    assert added["id"] == "my_custom_id"


def test_add_preset_saves_to_file(temp_presets):
    new_p = {
        "name": "File Test",
        "positive_suffix": "pos",
        "negative_suffix": "neg",
    }
    preset_mgr.add_preset(new_p)
    assert temp_presets.exists()
    data = json.loads(temp_presets.read_text(encoding="utf-8"))
    assert any(p["name"] == "File Test" for p in data)


# ------------------------------------------------------------------ #
# プリセットの削除
# ------------------------------------------------------------------ #

def test_delete_user_preset():
    new_p = {
        "name": "To Delete",
        "positive_suffix": "pos",
        "negative_suffix": "neg",
    }
    added = preset_mgr.add_preset(new_p)
    result = preset_mgr.delete_preset(added["id"])
    assert result is True

    all_presets = preset_mgr.get_all_presets()
    ids = [p["id"] for p in all_presets]
    assert added["id"] not in ids


def test_cannot_delete_default_preset():
    """デフォルトプリセットは削除できない"""
    result = preset_mgr.delete_preset("anime")
    assert result is False
    # anime プリセットがまだ存在することを確認
    presets = preset_mgr.get_all_presets()
    assert any(p["id"] == "anime" for p in presets)


def test_delete_nonexistent_preset():
    result = preset_mgr.delete_preset("does_not_exist")
    assert result is False


# ------------------------------------------------------------------ #
# get_preset
# ------------------------------------------------------------------ #

def test_get_preset_by_id():
    p = preset_mgr.get_preset("anime")
    assert p is not None
    assert p["id"] == "anime"


def test_get_preset_not_found():
    p = preset_mgr.get_preset("nonexistent")
    assert p is None
