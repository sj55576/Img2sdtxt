"""tests/test_version_management.py — Issue #78 Prompt Version Management のテスト"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from history import (  # noqa: E402
    get_history_item,
    get_version_diff,
    get_version_tree,
    init_db,
    rollback_to_version,
    save_history,
)


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """Use a temporary database for each test."""
    db = tmp_path / "test_history.db"
    monkeypatch.setattr("history.DB_PATH", db)
    init_db()
    yield db


class TestVersionTree:
    def test_save_with_parent_id(self):
        root_id = save_history("tag1, tag2", "bad1", parent_id=None)
        child_id = save_history("tag1, tag2, tag3", "bad1", parent_id=root_id)
        child = get_history_item(child_id)
        assert child["parent_id"] == root_id

    def test_get_version_tree_single(self):
        root_id = save_history("test", "neg")
        tree = get_version_tree(root_id)
        assert len(tree) == 1
        assert tree[0]["id"] == root_id
        assert tree[0]["depth"] == 0

    def test_get_version_tree_chain(self):
        root = save_history("v1", "neg1")
        child = save_history("v2", "neg2", parent_id=root)
        grandchild = save_history("v3", "neg3", parent_id=child)
        tree = get_version_tree(grandchild)
        assert len(tree) == 3
        assert tree[0]["id"] == root
        assert tree[0]["depth"] == 0
        assert tree[1]["id"] == child
        assert tree[1]["depth"] == 1
        assert tree[2]["id"] == grandchild
        assert tree[2]["depth"] == 2

    def test_get_version_tree_branching(self):
        root = save_history("v1", "neg1")
        branch_a = save_history("v2a", "neg2a", parent_id=root)
        branch_b = save_history("v2b", "neg2b", parent_id=root)
        tree = get_version_tree(root)
        assert len(tree) == 3
        ids = [v["id"] for v in tree]
        assert ids[0] == root
        assert set(ids[1:]) == {branch_a, branch_b}

    def test_get_version_tree_from_leaf(self):
        """Starting from a leaf should still return the full tree."""
        root = save_history("v1", "n1")
        child = save_history("v2", "n2", parent_id=root)
        tree = get_version_tree(child)
        assert len(tree) == 2
        assert tree[0]["id"] == root

    def test_get_version_tree_includes_required_fields(self):
        root = save_history("v1", "n1", style="anime", tone="vivid", quality="high")
        tree = get_version_tree(root)
        item = tree[0]
        for field in (
            "id",
            "parent_id",
            "positive",
            "negative",
            "style",
            "tone",
            "quality",
            "created_at",
            "is_favorite",
            "depth",
        ):
            assert field in item

    def test_get_version_tree_nonexistent(self):
        tree = get_version_tree(99999)
        assert tree == []


class TestVersionDiff:
    def test_diff_added_tags(self):
        id_a = save_history("tag1, tag2", "neg")
        id_b = save_history("tag1, tag2, tag3", "neg")
        diff = get_version_diff(id_a, id_b)
        assert "tag3" in diff["positive"]["added"]
        assert len(diff["positive"]["removed"]) == 0

    def test_diff_removed_tags(self):
        id_a = save_history("tag1, tag2, tag3", "neg")
        id_b = save_history("tag1, tag2", "neg")
        diff = get_version_diff(id_a, id_b)
        assert "tag3" in diff["positive"]["removed"]

    def test_diff_unchanged(self):
        id_a = save_history("tag1, tag2", "neg1")
        id_b = save_history("tag1, tag2", "neg2")
        diff = get_version_diff(id_a, id_b)
        assert set(diff["positive"]["unchanged"]) == {"tag1", "tag2"}

    def test_diff_nonexistent(self):
        id_a = save_history("test", "neg")
        result = get_version_diff(id_a, 99999)
        assert result is None

    def test_diff_negative_prompt(self):
        id_a = save_history("pos", "bad1, bad2")
        id_b = save_history("pos", "bad1, bad3")
        diff = get_version_diff(id_a, id_b)
        assert "bad3" in diff["negative"]["added"]
        assert "bad2" in diff["negative"]["removed"]
        assert "bad1" in diff["negative"]["unchanged"]

    def test_diff_whitespace_trimmed(self):
        id_a = save_history("tag1,  tag2 ,tag3", "neg")
        id_b = save_history("tag1, tag2,tag3", "neg")
        diff = get_version_diff(id_a, id_b)
        assert diff["positive"]["added"] == []
        assert diff["positive"]["removed"] == []
        assert set(diff["positive"]["unchanged"]) == {"tag1", "tag2", "tag3"}


class TestRollback:
    def test_rollback_creates_new_version(self):
        root = save_history("original", "neg_orig")
        child = save_history("modified", "neg_mod", parent_id=root)
        rolled_back = rollback_to_version(child, root)
        assert rolled_back is not None
        assert rolled_back["positive"] == "original"
        assert rolled_back["negative"] == "neg_orig"
        assert rolled_back["parent_id"] == child
        assert rolled_back["image_name"] == "[rollback]"

    def test_rollback_nonexistent_source(self):
        target = save_history("test", "neg")
        result = rollback_to_version(99999, target)
        assert result is None

    def test_rollback_nonexistent_target(self):
        source = save_history("test", "neg")
        result = rollback_to_version(source, 99999)
        assert result is None

    def test_rollback_preserves_tree(self):
        root = save_history("v1", "n1")
        child = save_history("v2", "n2", parent_id=root)
        rollback_to_version(child, root)
        tree = get_version_tree(root)
        assert len(tree) == 3  # root, child, rolled-back


from fastapi.testclient import TestClient  # noqa: E402

import config  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture
def client(fresh_db):
    # Avoid 429s from the global IP-based rate limiter leaking across test files.
    config.RATE_LIMIT_ENABLED = False
    try:
        yield TestClient(app)
    finally:
        config.RATE_LIMIT_ENABLED = True


class TestVersionAPI:
    def test_get_versions(self, client):
        root = save_history("test", "neg")
        save_history("test2", "neg2", parent_id=root)
        r = client.get(f"/api/history/{root}/versions")
        assert r.status_code == 200
        data = r.json()
        assert data["success"]
        assert len(data["versions"]) == 2

    def test_get_versions_not_found(self, client):
        r = client.get("/api/history/99999/versions")
        assert r.status_code == 404

    def test_diff_endpoint(self, client):
        id_a = save_history("tag1, tag2", "neg")
        id_b = save_history("tag1, tag3", "neg")
        r = client.get(f"/api/history/diff?id_a={id_a}&id_b={id_b}")
        assert r.status_code == 200
        diff = r.json()["diff"]
        assert "tag3" in diff["positive"]["added"]
        assert "tag2" in diff["positive"]["removed"]

    def test_diff_endpoint_not_found(self, client):
        id_a = save_history("tag1", "neg")
        r = client.get(f"/api/history/diff?id_a={id_a}&id_b=99999")
        assert r.status_code == 404

    def test_rollback_endpoint(self, client):
        root = save_history("original", "neg")
        child = save_history("modified", "neg2", parent_id=root)
        r = client.post(f"/api/history/{child}/rollback", json={"target_id": root})
        assert r.status_code == 200
        assert r.json()["item"]["positive"] == "original"

    def test_rollback_missing_target_id(self, client):
        root = save_history("test", "neg")
        r = client.post(f"/api/history/{root}/rollback", json={})
        assert r.status_code == 400

    def test_rollback_endpoint_not_found(self, client):
        root = save_history("test", "neg")
        r = client.post(f"/api/history/{root}/rollback", json={"target_id": 99999})
        assert r.status_code == 404
