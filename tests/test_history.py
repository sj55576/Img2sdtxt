"""tests/test_history.py — 一時 SQLite DB を使った history モジュールの CRUD テスト"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import history as hist


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """各テストで新しい一時 DB を使用する"""
    db_file = tmp_path / "test_history.db"
    monkeypatch.setattr(hist, "DB_PATH", db_file)
    yield db_file


# ------------------------------------------------------------------ #
# 基本 CRUD
# ------------------------------------------------------------------ #


def test_save_and_get():
    rowid = hist.save_history(
        positive="1girl, cute", negative="blurry", image_name="test.png", style="anime", tone="vibrant", quality="high"
    )
    assert isinstance(rowid, int)
    items = hist.get_history()
    assert len(items) == 1
    assert items[0]["positive"] == "1girl, cute"
    assert items[0]["image_name"] == "test.png"


def test_get_with_limit():
    for i in range(5):
        hist.save_history(positive=f"prompt {i}", negative="neg")
    items = hist.get_history(limit=3)
    assert len(items) == 3


def test_get_with_offset():
    for i in range(5):
        hist.save_history(positive=f"item {i}", negative="neg")
    items_all = hist.get_history(limit=None)
    items_offset = hist.get_history(limit=None, offset=2)
    assert len(items_all) == 5
    assert len(items_offset) == 3


def test_limit_none_returns_all():
    for i in range(15):
        hist.save_history(positive=f"p{i}", negative="n")
    items = hist.get_history(limit=None)
    assert len(items) == 15


def test_search_filter():
    hist.save_history(positive="beautiful landscape", negative="ugly")
    hist.save_history(positive="anime girl", negative="bad")
    items = hist.get_history(search="landscape")
    assert len(items) == 1
    assert "landscape" in items[0]["positive"]


def test_search_with_percent_wildcard():
    """% を含む検索語はリテラルとして扱われ、全件マッチしない"""
    hist.save_history(positive="normal prompt", negative="bad")
    hist.save_history(positive="another prompt", negative="ugly")
    # "%" はエスケープされてリテラル % として検索される
    items = hist.get_history(search="%")
    assert len(items) == 0  # どちらの行も "%" を含まない


def test_search_with_underscore():
    """_ を含む検索語はリテラルとして扱われる"""
    hist.save_history(positive="has_underscore here", negative="bad")
    hist.save_history(positive="no special chars", negative="ugly")
    items = hist.get_history(search="_")
    assert len(items) == 1
    assert "has_underscore" in items[0]["positive"]


def test_style_filter():
    hist.save_history(positive="p1", negative="n", style="anime")
    hist.save_history(positive="p2", negative="n", style="photorealistic")
    items = hist.get_history(style="anime")
    assert len(items) == 1


def test_quality_filter():
    hist.save_history(positive="p1", negative="n", quality="high")
    hist.save_history(positive="p2", negative="n", quality="ultra")
    items = hist.get_history(quality="ultra")
    assert len(items) == 1


def test_favorites_only():
    rowid = hist.save_history(positive="fav", negative="n")
    hist.save_history(positive="not fav", negative="n")
    hist.toggle_favorite(rowid)
    items = hist.get_history(favorites_only=True)
    assert len(items) == 1
    assert items[0]["positive"] == "fav"


def test_toggle_favorite():
    rowid = hist.save_history(positive="test", negative="n")
    updated = hist.toggle_favorite(rowid)
    assert updated["is_favorite"] == 1
    updated2 = hist.toggle_favorite(rowid)
    assert updated2["is_favorite"] == 0


def test_toggle_favorite_not_found():
    result = hist.toggle_favorite(99999)
    assert result is None


def test_delete_history_item():
    rowid = hist.save_history(positive="to delete", negative="n")
    assert hist.delete_history_item(rowid) is True
    assert hist.get_history_item(rowid) is None


def test_delete_nonexistent():
    assert hist.delete_history_item(99999) is False


def test_clear_all_history():
    for i in range(3):
        hist.save_history(positive=f"p{i}", negative="n")
    count = hist.clear_all_history()
    assert count == 3
    assert hist.get_history() == []


def test_get_history_count():
    hist.save_history(positive="a", negative="n", style="anime")
    hist.save_history(positive="b", negative="n", style="photo")
    total = hist.get_history_count()
    assert total == 2
    filtered = hist.get_history_count(style="anime")
    assert filtered == 1


# ------------------------------------------------------------------ #
# Tags
# ------------------------------------------------------------------ #


def test_add_tags():
    rowid = hist.save_history(positive="tagged", negative="n")
    tags = hist.add_tags(rowid, ["portrait", "anime"])
    assert sorted(tags) == ["anime", "portrait"]


def test_add_tags_normalized():
    """Tags are lowercased and stripped"""
    rowid = hist.save_history(positive="tagged", negative="n")
    tags = hist.add_tags(rowid, ["  Portrait  ", "ANIME"])
    assert sorted(tags) == ["anime", "portrait"]


def test_add_duplicate_tags():
    """Adding duplicate tags is idempotent"""
    rowid = hist.save_history(positive="tagged", negative="n")
    hist.add_tags(rowid, ["portrait"])
    tags = hist.add_tags(rowid, ["portrait", "anime"])
    assert sorted(tags) == ["anime", "portrait"]


def test_remove_tag():
    rowid = hist.save_history(positive="tagged", negative="n")
    hist.add_tags(rowid, ["portrait", "anime"])
    remaining = hist.remove_tag(rowid, "portrait")
    assert remaining == ["anime"]


def test_get_tags_empty():
    rowid = hist.save_history(positive="no tags", negative="n")
    assert hist.get_tags(rowid) == []


def test_get_all_tags():
    r1 = hist.save_history(positive="p1", negative="n")
    r2 = hist.save_history(positive="p2", negative="n")
    hist.add_tags(r1, ["portrait", "anime"])
    hist.add_tags(r2, ["portrait"])
    all_tags = hist.get_all_tags()
    assert len(all_tags) == 2
    assert all_tags[0]["tag"] == "portrait"
    assert all_tags[0]["count"] == 2
    assert all_tags[1]["tag"] == "anime"
    assert all_tags[1]["count"] == 1


def test_history_filter_by_tag():
    r1 = hist.save_history(positive="p1", negative="n")
    hist.save_history(positive="p2", negative="n")
    hist.add_tags(r1, ["portrait"])
    items = hist.get_history(tag="portrait")
    assert len(items) == 1
    assert items[0]["positive"] == "p1"


def test_history_count_with_tag():
    r1 = hist.save_history(positive="p1", negative="n")
    hist.save_history(positive="p2", negative="n")
    hist.add_tags(r1, ["portrait"])
    assert hist.get_history_count(tag="portrait") == 1
    assert hist.get_history_count() == 2


def test_history_items_include_tags():
    """get_history returns items with 'tags' key"""
    rowid = hist.save_history(positive="with tags", negative="n")
    hist.add_tags(rowid, ["landscape", "hdr"])
    items = hist.get_history()
    assert "tags" in items[0]
    assert sorted(items[0]["tags"]) == ["hdr", "landscape"]


def test_delete_history_cascades_tags():
    """Deleting a history item should cascade-delete its tags"""
    rowid = hist.save_history(positive="to delete", negative="n")
    hist.add_tags(rowid, ["portrait"])
    hist.delete_history_item(rowid)
    assert hist.get_tags(rowid) == []
