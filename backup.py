"""Data backup and restore utilities.

Creates/restores zip archives containing the application's ``data/`` directory
(SQLite databases, presets, wildcards, etc.) and, optionally, the ``outputs/``
directory. SQLite databases are copied using the ``sqlite3`` online backup API
so a consistent snapshot is taken even while the application is writing to
them concurrently.

Restoring data does NOT reload in-process state: modules such as ``cache``,
``rate_limit``, and ``history`` hold their own long-lived sqlite3 connections
and/or in-memory state. After calling :func:`restore_backup`, a server
restart is strongly recommended so every module reopens its connections
against the restored files.
"""

import json
import logging
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import config

logger = logging.getLogger("img2sdtxt.backup")

APP_ROOT = Path(__file__).parent
DATA_DIR = APP_ROOT / "data"
OUTPUTS_DIR = APP_ROOT / "outputs"
BACKUP_DIR = Path(config.BACKUP_DIR)

BACKUP_SCHEMA_VERSION = 1
APP_VERSION = "2.0.0"

BACKUP_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")


def _backup_dir(backup_dir: Optional[Path] = None) -> Path:
    """Resolve the directory backups are stored in (default: module-level BACKUP_DIR)."""
    return Path(backup_dir) if backup_dir is not None else Path(BACKUP_DIR)


def _is_sqlite_file(path: Path) -> bool:
    if path.suffix in (".db-wal", ".db-shm"):
        return False
    if path.name.endswith("-wal") or path.name.endswith("-shm"):
        return False
    return path.suffix == ".db"


def _iter_files(root: Path, exclude: Optional[Path] = None):
    """Yield every regular file under ``root``, skipping ``exclude`` (and its contents)."""
    if not root.exists():
        return
    # Resolve both sides: BACKUP_DIR may be configured as a relative path, in
    # which case a naive comparison would fail and the backup directory would
    # end up nested inside its own archive.
    exclude_resolved = exclude.resolve() if exclude is not None else None
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if exclude_resolved is not None:
            try:
                path.resolve().relative_to(exclude_resolved)
                continue
            except ValueError:
                pass
        if path.name.endswith("-wal") or path.name.endswith("-shm"):
            continue
        yield path


def _sqlite_backup_copy(src: Path, dest: Path) -> None:
    """Copy a SQLite database file to ``dest`` using the online backup API.

    This produces a consistent snapshot even if another connection is
    actively writing to ``src``.
    """
    src_conn = sqlite3.connect(str(src))
    dest_conn = sqlite3.connect(str(dest))
    try:
        src_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        src_conn.close()


def create_backup(include_outputs: bool = False, backup_dir: Optional[Path] = None) -> Dict:
    """Create a zip backup of the ``data/`` directory (and optionally ``outputs/``).

    Returns a dict describing the created backup: id, filename, path, size,
    created_at, include_outputs, file_count.
    """
    target_dir = _backup_dir(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    backup_id = f"img2sdtxt-backup-{now.strftime('%Y%m%d-%H%M%S')}"
    # Ids have second granularity; two backups within the same second (e.g. a
    # safety backup immediately followed by a manual one) must not overwrite
    # each other.
    if (target_dir / f"{backup_id}.zip").exists():
        suffix = 2
        while (target_dir / f"{backup_id}-{suffix}.zip").exists():
            suffix += 1
        backup_id = f"{backup_id}-{suffix}"
    filename = f"{backup_id}.zip"
    zip_path = target_dir / filename

    manifest_files: List[Dict] = []

    with tempfile.TemporaryDirectory(prefix="img2sdtxt-backup-") as tmp_dir_name:
        tmp_dir = Path(tmp_dir_name)
        tmp_zip_path = tmp_dir / filename

        with zipfile.ZipFile(tmp_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for src in _iter_files(DATA_DIR, exclude=target_dir):
                rel = src.relative_to(APP_ROOT)
                arcname = rel.as_posix()
                if _is_sqlite_file(src):
                    tmp_db = tmp_dir / f"{src.name}.snapshot"
                    _sqlite_backup_copy(src, tmp_db)
                    zf.write(tmp_db, arcname)
                    size = tmp_db.stat().st_size
                    tmp_db.unlink(missing_ok=True)
                else:
                    zf.write(src, arcname)
                    size = src.stat().st_size
                manifest_files.append({"path": arcname, "size": size})

            if include_outputs:
                for src in _iter_files(OUTPUTS_DIR):
                    rel = src.relative_to(APP_ROOT)
                    arcname = rel.as_posix()
                    zf.write(src, arcname)
                    manifest_files.append({"path": arcname, "size": src.stat().st_size})

            manifest = {
                "schema_version": BACKUP_SCHEMA_VERSION,
                "app_version": APP_VERSION,
                "created_at": now.isoformat(),
                "include_outputs": include_outputs,
                "files": manifest_files,
                "file_count": len(manifest_files),
                "total_size": sum(f["size"] for f in manifest_files),
            }
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        shutil.move(str(tmp_zip_path), str(zip_path))

    size = zip_path.stat().st_size
    logger.info("Created backup %s (%d files, %d bytes)", backup_id, len(manifest_files), size)

    return {
        "id": backup_id,
        "filename": filename,
        "path": str(zip_path),
        "size": size,
        "created_at": now.isoformat(),
        "include_outputs": include_outputs,
        "file_count": len(manifest_files),
    }


def list_backups(backup_dir: Optional[Path] = None) -> List[Dict]:
    """List all backups in ``backup_dir``, newest first.

    Corrupt or unreadable zip files are still listed with ``"valid": False``
    rather than raising.
    """
    target_dir = _backup_dir(backup_dir)
    if not target_dir.exists():
        return []

    entries: List[Dict] = []
    for zip_path in target_dir.glob("*.zip"):
        entry: Dict = {
            "id": zip_path.stem,
            "filename": zip_path.name,
            "size": zip_path.stat().st_size,
            "created_at": None,
            "include_outputs": None,
            "file_count": None,
            "valid": True,
        }
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                with zf.open("manifest.json") as f:
                    manifest = json.load(f)
            entry["created_at"] = manifest.get("created_at")
            entry["include_outputs"] = manifest.get("include_outputs")
            entry["file_count"] = manifest.get("file_count")
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, OSError) as exc:
            logger.warning("Backup %s is invalid: %s", zip_path.name, exc)
            entry["valid"] = False

        entries.append(entry)

    def _sort_key(e: Dict):
        return e["created_at"] or ""

    entries.sort(key=_sort_key, reverse=True)
    return entries


def _resolve_backup_id(backup_id: str, backup_dir: Optional[Path] = None) -> Optional[Path]:
    """Validate ``backup_id`` and resolve it to a path strictly inside ``backup_dir``."""
    if not BACKUP_ID_RE.match(backup_id):
        return None
    target_dir = _backup_dir(backup_dir).resolve()
    candidate = (target_dir / f"{backup_id}.zip").resolve()
    try:
        candidate.relative_to(target_dir)
    except ValueError:
        return None
    if not candidate.exists():
        return None
    return candidate


def get_backup_path(backup_id: str, backup_dir: Optional[Path] = None) -> Optional[Path]:
    """Return the absolute path for ``backup_id``, or None if invalid/not found."""
    return _resolve_backup_id(backup_id, backup_dir)


def delete_backup(backup_id: str, backup_dir: Optional[Path] = None) -> bool:
    """Delete a backup by id. Returns False if the id is invalid or unknown."""
    path = _resolve_backup_id(backup_id, backup_dir)
    if path is None:
        return False
    path.unlink()
    logger.info("Deleted backup %s", backup_id)
    return True


def _validate_zip_member(name: str) -> Path:
    """Validate a single zip member name for zip-slip / traversal safety.

    Returns the resolved destination path (still inside APP_ROOT) or raises
    ValueError.
    """
    if name == "manifest.json":
        return (APP_ROOT / name).resolve()

    if not name or name.startswith("/") or name.startswith("\\"):
        raise ValueError(f"Unsafe path in backup archive: {name!r}")
    if re.match(r"^[A-Za-z]:", name):  # Windows drive letter
        raise ValueError(f"Unsafe path in backup archive: {name!r}")

    parts = Path(name).parts
    if not parts or ".." in parts:
        raise ValueError(f"Unsafe path in backup archive: {name!r}")
    if parts[0] not in ("data", "outputs"):
        raise ValueError(f"Unexpected top-level entry in backup archive: {name!r}")

    dest = (APP_ROOT / name).resolve()
    try:
        dest.relative_to(APP_ROOT.resolve())
    except ValueError:
        raise ValueError(f"Unsafe path in backup archive: {name!r}") from None
    return dest


def restore_backup(
    zip_path: Path,
    *,
    create_safety_backup: bool = True,
    backup_dir: Optional[Path] = None,
) -> Dict:
    """Restore application data from a backup zip archive.

    SECURITY: every archive member is validated before anything is written —
    absolute paths, drive letters, ``..`` traversal, symlinks, and any entry
    whose first path segment is not ``data``/``outputs`` (aside from
    ``manifest.json``) are rejected with a :class:`ValueError`.

    IMPORTANT: modules that already hold open SQLite connections or
    in-memory state (``cache``, ``rate_limit``, ``history``, ...) are not
    reloaded by this call. A process/server restart is recommended after a
    successful restore so all modules reopen against the restored files.
    """
    zip_path = Path(zip_path)
    if not zipfile.is_zipfile(zip_path):
        raise ValueError("Not a valid zip file.")

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        if "manifest.json" not in names:
            raise ValueError("Backup archive is missing manifest.json.")

        try:
            manifest = json.loads(zf.read("manifest.json"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Backup archive has an invalid manifest.json: {exc}") from exc

        schema_version = manifest.get("schema_version")
        if not isinstance(schema_version, int) or schema_version > BACKUP_SCHEMA_VERSION:
            raise ValueError(
                f"Backup schema_version {schema_version!r} is newer than supported ({BACKUP_SCHEMA_VERSION})."
            )

        # Validate every member BEFORE writing anything.
        validated: List[tuple] = []
        for info in zf.infolist():
            if info.is_dir():
                continue
            # zipfile flags Unix symlinks via the upper 16 bits of external_attr.
            mode = (info.external_attr >> 16) & 0xFFFF
            if mode and stat.S_ISLNK(mode):
                raise ValueError(f"Backup archive contains a symlink, which is not allowed: {info.filename!r}")
            dest = _validate_zip_member(info.filename)
            validated.append((info, dest))

        safety_backup_id: Optional[str] = None
        if create_safety_backup:
            safety = create_backup(include_outputs=False, backup_dir=backup_dir)
            safety_backup_id = safety["id"]

        restored_files = 0
        for info, dest in validated:
            if info.filename == "manifest.json":
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Write to a sibling temp file and os.replace() it into place.
            # Truncating the destination in-place would corrupt the view of any
            # SQLite connection this process still holds open on that file;
            # replacing gives those connections the old inode instead, so they
            # keep working (with pre-restore data) until the server restarts.
            tmp_dest = dest.with_name(f"{dest.name}.restore-tmp")
            try:
                with zf.open(info) as src_f, open(tmp_dest, "wb") as dest_f:
                    shutil.copyfileobj(src_f, dest_f)
                os.replace(tmp_dest, dest)
            finally:
                tmp_dest.unlink(missing_ok=True)
            restored_files += 1

    # Best-effort VACUUM of restored sqlite databases.
    for _info, dest in validated:
        if dest.name == "manifest.json" or not _is_sqlite_file(dest):
            continue
        if not dest.exists():
            continue
        try:
            conn = sqlite3.connect(str(dest))
            try:
                conn.execute("VACUUM")
                conn.commit()
            finally:
                conn.close()
        except sqlite3.Error as exc:
            logger.warning("VACUUM failed for restored database %s: %s", dest, exc)

    logger.info("Restored %d files from backup %s", restored_files, zip_path)

    return {
        "restored_files": restored_files,
        "manifest": manifest,
        "safety_backup_id": safety_backup_id,
        "requires_restart": True,
    }


def rotate_backups(retention: int, backup_dir: Optional[Path] = None) -> List[str]:
    """Delete backups older than the newest ``retention``. Returns deleted ids."""
    if retention < 0:
        return []
    backups = list_backups(backup_dir)
    to_delete = backups[retention:]
    deleted: List[str] = []
    for entry in to_delete:
        if delete_backup(entry["id"], backup_dir):
            deleted.append(entry["id"])
    return deleted


class AutoBackupScheduler:
    """Background daemon thread that periodically creates and rotates backups.

    Modeled on ``health_monitor.HealthMonitor``: a daemon ``threading.Thread``
    driven by a ``threading.Event`` for cooperative shutdown, with all
    exceptions swallowed and logged so a backup failure never crashes the app.
    """

    def __init__(self, interval_hours: int, retention: int, backup_dir: Optional[Path] = None):
        self.interval_hours = interval_hours
        self.retention = retention
        self.backup_dir = backup_dir
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _run_once(self) -> None:
        try:
            result = create_backup(include_outputs=False, backup_dir=self.backup_dir)
            logger.info("Auto-backup created: %s", result["id"])
        except Exception as exc:
            logger.error("Auto-backup failed: %s", exc)
            return
        try:
            deleted = rotate_backups(self.retention, backup_dir=self.backup_dir)
            if deleted:
                logger.info("Auto-backup rotation deleted %d old backup(s): %s", len(deleted), deleted)
        except Exception as exc:
            logger.error("Auto-backup rotation failed: %s", exc)

    def _run(self) -> None:
        interval_seconds = max(1, self.interval_hours) * 3600
        while not self._stop_event.wait(interval_seconds):
            self._run_once()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="auto-backup", daemon=True)
        self._thread.start()
        logger.info("AutoBackupScheduler started (interval=%dh, retention=%d)", self.interval_hours, self.retention)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        logger.info("AutoBackupScheduler stopped")


def start_auto_backup(interval_hours: int, retention: int, backup_dir: Optional[Path] = None) -> AutoBackupScheduler:
    """Create and start an :class:`AutoBackupScheduler`. Returns the scheduler."""
    scheduler = AutoBackupScheduler(interval_hours=interval_hours, retention=retention, backup_dir=backup_dir)
    scheduler.start()
    return scheduler
