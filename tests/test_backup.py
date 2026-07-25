"""tests/test_backup.py — backup/restore module tests using temporary directories"""

import io
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backup as backup_mgr


@pytest.fixture(autouse=True)
def temp_dirs(tmp_path, monkeypatch):
    """Point backup.APP_ROOT/DATA_DIR/OUTPUTS_DIR/BACKUP_DIR at a temp tree."""
    app_root = tmp_path / "app"
    data_dir = app_root / "data"
    outputs_dir = app_root / "outputs"
    backup_dir = data_dir / "backups"
    data_dir.mkdir(parents=True)
    outputs_dir.mkdir(parents=True)

    monkeypatch.setattr(backup_mgr, "APP_ROOT", app_root)
    monkeypatch.setattr(backup_mgr, "DATA_DIR", data_dir)
    monkeypatch.setattr(backup_mgr, "OUTPUTS_DIR", outputs_dir)
    monkeypatch.setattr(backup_mgr, "BACKUP_DIR", backup_dir)

    yield {"app_root": app_root, "data_dir": data_dir, "outputs_dir": outputs_dir, "backup_dir": backup_dir}


def _make_sqlite_db(path: Path, rows=(("hello", 1),)):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE items (name TEXT, value INTEGER)")
    conn.executemany("INSERT INTO items (name, value) VALUES (?, ?)", rows)
    conn.commit()
    conn.close()


def _populate_data_dir(data_dir: Path):
    _make_sqlite_db(data_dir / "history.db")
    (data_dir / "presets.json").write_text(json.dumps([{"id": "anime"}]), encoding="utf-8")
    (data_dir / "wildcards").mkdir(parents=True, exist_ok=True)
    (data_dir / "wildcards" / "x.txt").write_text("foo\nbar\n", encoding="utf-8")


# ------------------------------------------------------------------ #
# create_backup / restore_backup round trip
# ------------------------------------------------------------------ #


def test_round_trip_restores_files_and_sqlite_row(temp_dirs):
    data_dir = temp_dirs["data_dir"]
    _populate_data_dir(data_dir)

    result = backup_mgr.create_backup(include_outputs=False)
    assert result["file_count"] >= 3

    # Copy the backup out of data/ before wiping, since data/backups/ lives under data_dir.
    import shutil

    saved_zip = temp_dirs["app_root"].parent / "saved_backup.zip"
    shutil.copy(result["path"], saved_zip)

    # Wipe the data dir (simulate data loss), then restore.
    for item in list(data_dir.iterdir()):
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    restore_result = backup_mgr.restore_backup(saved_zip, create_safety_backup=False)

    assert restore_result["restored_files"] >= 3
    assert (data_dir / "presets.json").exists()
    assert (data_dir / "wildcards" / "x.txt").read_text(encoding="utf-8") == "foo\nbar\n"

    conn = sqlite3.connect(str(data_dir / "history.db"))
    rows = conn.execute("SELECT name, value FROM items").fetchall()
    conn.close()
    assert rows == [("hello", 1)]


def test_manifest_contents(temp_dirs):
    _populate_data_dir(temp_dirs["data_dir"])
    result = backup_mgr.create_backup()
    with zipfile.ZipFile(result["path"]) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    assert manifest["schema_version"] == backup_mgr.BACKUP_SCHEMA_VERSION
    assert manifest["file_count"] == result["file_count"]
    assert manifest["created_at"]


def test_include_outputs_false_excludes_outputs(temp_dirs):
    _populate_data_dir(temp_dirs["data_dir"])
    (temp_dirs["outputs_dir"] / "img1.json").write_text("{}", encoding="utf-8")

    result = backup_mgr.create_backup(include_outputs=False)
    with zipfile.ZipFile(result["path"]) as zf:
        names = zf.namelist()
    assert not any(n.startswith("outputs/") for n in names)


def test_include_outputs_true_includes_outputs(temp_dirs):
    _populate_data_dir(temp_dirs["data_dir"])
    (temp_dirs["outputs_dir"] / "img1.json").write_text("{}", encoding="utf-8")

    result = backup_mgr.create_backup(include_outputs=True)
    with zipfile.ZipFile(result["path"]) as zf:
        names = zf.namelist()
    assert any(n.startswith("outputs/") for n in names)


def test_backups_dir_not_nested_in_its_own_archive(temp_dirs):
    _populate_data_dir(temp_dirs["data_dir"])
    backup_mgr.create_backup()
    result = backup_mgr.create_backup()
    with zipfile.ZipFile(result["path"]) as zf:
        names = zf.namelist()
    assert not any("backups/" in n for n in names)


# ------------------------------------------------------------------ #
# get_backup_path / delete_backup id validation
# ------------------------------------------------------------------ #


@pytest.mark.parametrize("bad_id", ["../etc/passwd", "/abs/path", "a/b"])
def test_get_backup_path_rejects_unsafe_ids(temp_dirs, bad_id):
    assert backup_mgr.get_backup_path(bad_id) is None


def test_get_backup_path_rejects_unknown_id(temp_dirs):
    assert backup_mgr.get_backup_path("img2sdtxt-backup-20200101-000000") is None


def test_get_backup_path_returns_known_id(temp_dirs):
    _populate_data_dir(temp_dirs["data_dir"])
    result = backup_mgr.create_backup()
    path = backup_mgr.get_backup_path(result["id"])
    assert path is not None
    assert path.exists()


# ------------------------------------------------------------------ #
# restore_backup security / validation
# ------------------------------------------------------------------ #


def _write_malicious_zip(zip_path: Path, manifest: dict, entries: dict):
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        for name, content in entries.items():
            zf.writestr(name, content)


def _default_manifest():
    return {
        "schema_version": 1,
        "app_version": "2.0.0",
        "created_at": "2026-01-01T00:00:00+00:00",
        "include_outputs": False,
        "files": [],
        "file_count": 0,
        "total_size": 0,
    }


def test_restore_rejects_path_traversal(temp_dirs, tmp_path):
    evil_zip = tmp_path / "evil.zip"
    _write_malicious_zip(evil_zip, _default_manifest(), {"data/../../evil.txt": "pwned"})

    with pytest.raises(ValueError):
        backup_mgr.restore_backup(evil_zip, create_safety_backup=False)

    assert not (temp_dirs["app_root"].parent / "evil.txt").exists()
    for path in temp_dirs["app_root"].parent.iterdir():
        assert path == temp_dirs["app_root"] or path.name != "evil.txt"


def test_restore_rejects_absolute_member_path(temp_dirs, tmp_path):
    evil_zip = tmp_path / "evil_abs.zip"
    _write_malicious_zip(evil_zip, _default_manifest(), {"/etc/evil.txt": "pwned"})

    with pytest.raises(ValueError):
        backup_mgr.restore_backup(evil_zip, create_safety_backup=False)

    assert not Path("/etc/evil.txt").exists()


def test_restore_rejects_missing_manifest(tmp_path):
    bad_zip = tmp_path / "no_manifest.zip"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("data/foo.txt", "hi")

    with pytest.raises(ValueError, match="manifest"):
        backup_mgr.restore_backup(bad_zip, create_safety_backup=False)


def test_restore_rejects_future_schema_version(tmp_path):
    bad_zip = tmp_path / "future_schema.zip"
    manifest = _default_manifest()
    manifest["schema_version"] = 999
    _write_malicious_zip(bad_zip, manifest, {"data/foo.txt": "hi"})

    with pytest.raises(ValueError, match="schema_version"):
        backup_mgr.restore_backup(bad_zip, create_safety_backup=False)


def test_restore_creates_safety_backup_when_requested(temp_dirs):
    _populate_data_dir(temp_dirs["data_dir"])
    result = backup_mgr.create_backup()
    zip_path = Path(result["path"])

    restore_result = backup_mgr.restore_backup(zip_path, create_safety_backup=True)
    assert restore_result["safety_backup_id"] is not None
    assert backup_mgr.get_backup_path(restore_result["safety_backup_id"]) is not None


def test_restore_skips_safety_backup_when_disabled(temp_dirs):
    _populate_data_dir(temp_dirs["data_dir"])
    result = backup_mgr.create_backup()
    zip_path = Path(result["path"])

    before = {b["id"] for b in backup_mgr.list_backups()}
    restore_result = backup_mgr.restore_backup(zip_path, create_safety_backup=False)
    after = {b["id"] for b in backup_mgr.list_backups()}

    assert restore_result["safety_backup_id"] is None
    assert before == after


# ------------------------------------------------------------------ #
# rotate_backups
# ------------------------------------------------------------------ #


def test_rotate_backups_keeps_only_retention_newest(temp_dirs):
    _populate_data_dir(temp_dirs["data_dir"])
    ids = []
    for _ in range(5):
        result = backup_mgr.create_backup()
        ids.append(result["id"])
        # Ensure distinct timestamps in filenames across fast test execution.
        import time as _time

        _time.sleep(1.1)

    deleted = backup_mgr.rotate_backups(retention=2)
    remaining = backup_mgr.list_backups()

    assert len(remaining) == 2
    assert len(deleted) == 3
    assert set(deleted) | {b["id"] for b in remaining} == set(ids)


# ------------------------------------------------------------------ #
# 回帰テスト（レビュー指摘分）
# ------------------------------------------------------------------ #


def test_relative_backup_dir_is_still_excluded(temp_dirs, monkeypatch):
    """BACKUP_DIR が相対パスでもバックアップ先自身がアーカイブに含まれない"""
    _populate_data_dir(temp_dirs["data_dir"])
    monkeypatch.chdir(temp_dirs["app_root"])
    monkeypatch.setattr(backup_mgr, "BACKUP_DIR", Path("data/backups"))

    first = backup_mgr.create_backup()
    second = backup_mgr.create_backup()

    with zipfile.ZipFile(second["path"]) as zf:
        names = zf.namelist()
    assert not any("backups/" in n for n in names)
    assert Path(first["path"]).name not in " ".join(names)


def test_backups_in_same_second_do_not_overwrite(temp_dirs):
    """同一秒に作成しても ID が衝突せず両方残る"""
    _populate_data_dir(temp_dirs["data_dir"])

    original = backup_mgr.datetime
    frozen = original(2026, 1, 2, 3, 4, 5, tzinfo=backup_mgr.timezone.utc)

    class _FrozenClock:
        @staticmethod
        def now(tz=None):
            return frozen

    backup_mgr.datetime = _FrozenClock  # type: ignore[misc,assignment]
    try:
        a = backup_mgr.create_backup()
        b = backup_mgr.create_backup()
    finally:
        backup_mgr.datetime = original  # type: ignore[misc]

    assert a["id"] != b["id"]
    assert Path(a["path"]).exists() and Path(b["path"]).exists()
    assert len(backup_mgr.list_backups()) == 2


def test_restore_replaces_inode_instead_of_truncating(temp_dirs):
    """復元は同一 inode を切り詰めず置き換える（開いている接続を壊さない）"""
    data_dir = temp_dirs["data_dir"]
    _populate_data_dir(data_dir)
    db_path = data_dir / "history.db"
    created = backup_mgr.create_backup()

    inode_before = db_path.stat().st_ino
    # 復元前にデータを書き換える
    conn = sqlite3.connect(str(db_path))
    conn.execute("INSERT INTO items (name, value) VALUES ('later', 99)")
    conn.commit()
    conn.close()

    backup_mgr.restore_backup(Path(created["path"]), create_safety_backup=False)

    assert db_path.stat().st_ino != inode_before
    conn = sqlite3.connect(str(db_path))
    names = [r[0] for r in conn.execute("SELECT name FROM items")]
    conn.close()
    assert "later" not in names
    assert not list(data_dir.glob("*.restore-tmp"))


# ------------------------------------------------------------------ #
# ルート (routes/backup.py)
# ------------------------------------------------------------------ #


@pytest.fixture
def client(temp_dirs):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routes.backup import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_route_create_list_download_delete(client, temp_dirs):
    _populate_data_dir(temp_dirs["data_dir"])

    created = client.post("/api/backup/create", json={})
    assert created.status_code == 200
    backup_id = created.json()["backup"]["id"]
    assert "path" not in created.json()["backup"]  # サーバー内部パスは返さない

    listed = client.get("/api/backup/list")
    assert [b["id"] for b in listed.json()["backups"]] == [backup_id]

    assert client.get(f"/api/backup/download/{backup_id}").status_code == 200
    assert client.get("/api/backup/download/does-not-exist").status_code == 404

    assert client.delete(f"/api/backup/{backup_id}").status_code == 200
    assert client.delete(f"/api/backup/{backup_id}").status_code == 404


def test_route_restore_stored_backup(client, temp_dirs):
    """サーバー上のバックアップは再アップロードなしで復元できる"""
    data_dir = temp_dirs["data_dir"]
    _populate_data_dir(data_dir)
    backup_id = client.post("/api/backup/create", json={}).json()["backup"]["id"]

    (data_dir / "presets.json").write_text("CHANGED", encoding="utf-8")

    assert client.post(f"/api/backup/restore/{backup_id}", json={}).status_code == 400  # confirm 必須
    assert client.post("/api/backup/restore/unknown-id", json={"confirm": True}).status_code == 404

    resp = client.post(f"/api/backup/restore/{backup_id}", json={"confirm": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["requires_restart"] is True
    assert body["safety_backup_id"] is not None
    assert "files" not in body["manifest"]  # 巨大なファイル一覧は返さない
    assert (data_dir / "presets.json").read_text(encoding="utf-8") != "CHANGED"


def test_route_restore_upload_rejects_unsafe_archive(client, temp_dirs):
    _populate_data_dir(temp_dirs["data_dir"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"schema_version": 1}))
        zf.writestr("../evil.txt", "pwn")
    buf.seek(0)

    resp = client.post(
        "/api/backup/restore",
        files={"file": ("evil.zip", buf, "application/zip")},
        data={"confirm": "true"},
    )
    assert resp.status_code == 400
    assert "Unsafe path" in resp.json()["detail"]
    assert not (temp_dirs["app_root"].parent / "evil.txt").exists()


def test_route_restore_requires_confirm_and_zip(client, temp_dirs):
    _populate_data_dir(temp_dirs["data_dir"])
    buf = io.BytesIO(b"not a zip")
    assert (
        client.post(
            "/api/backup/restore",
            files={"file": ("x.zip", io.BytesIO(b"x"), "application/zip")},
            data={"confirm": "false"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/backup/restore",
            files={"file": ("x.txt", buf, "text/plain")},
            data={"confirm": "true"},
        ).status_code
        == 400
    )
