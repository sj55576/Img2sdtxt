"""Backup and restore endpoints."""

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

import backup as backup_mgr
import config

logger = logging.getLogger("img2sdtxt.routes.backup")

router = APIRouter(prefix="/api/backup", tags=["backup"])

UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1MB


@router.post("/create")
async def create_backup(body: Optional[dict] = None):
    include_outputs = bool((body or {}).get("include_outputs", False))
    try:
        result = await run_in_threadpool(backup_mgr.create_backup, include_outputs=include_outputs)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create backup: {exc}") from exc

    return {
        "success": True,
        "backup": {
            "id": result["id"],
            "filename": result["filename"],
            "size": result["size"],
            "created_at": result["created_at"],
            "include_outputs": result["include_outputs"],
            "file_count": result["file_count"],
        },
    }


@router.get("/list")
async def list_backups():
    backups = await run_in_threadpool(backup_mgr.list_backups)
    return {"success": True, "backups": backups}


@router.get("/download/{backup_id}")
async def download_backup(backup_id: str):
    path = await run_in_threadpool(backup_mgr.get_backup_path, backup_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Backup not found.")
    return FileResponse(path=str(path), media_type="application/zip", filename=path.name)


@router.post("/restore")
async def restore_backup(
    file: UploadFile = File(...),
    confirm: bool = Form(False),
    create_safety_backup: bool = Form(True),
):
    if not confirm:
        raise HTTPException(status_code=400, detail="Restore requires confirm=true.")

    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a .zip archive.")

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            total_bytes = 0
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > config.MAX_BACKUP_UPLOAD_SIZE:
                    raise HTTPException(status_code=400, detail="Uploaded backup exceeds the maximum allowed size.")
                tmp.write(chunk)

        try:
            result = await run_in_threadpool(
                backup_mgr.restore_backup,
                tmp_path,
                create_safety_backup=create_safety_backup,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # The manifest's "files" list can hold thousands of entries; the client
    # only needs the summary fields.
    manifest = {k: v for k, v in result["manifest"].items() if k != "files"}

    return {
        "success": True,
        "restored_files": result["restored_files"],
        "safety_backup_id": result["safety_backup_id"],
        "requires_restart": result["requires_restart"],
        "manifest": manifest,
    }


@router.post("/restore/{backup_id}")
async def restore_stored_backup(backup_id: str, body: Optional[dict] = None):
    """Restore from a backup already stored on the server (no upload round trip)."""
    payload = body or {}
    if not bool(payload.get("confirm", False)):
        raise HTTPException(status_code=400, detail="Restore requires confirm=true.")

    path = await run_in_threadpool(backup_mgr.get_backup_path, backup_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Backup not found.")

    try:
        result = await run_in_threadpool(
            backup_mgr.restore_backup,
            path,
            create_safety_backup=bool(payload.get("create_safety_backup", True)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    manifest = {k: v for k, v in result["manifest"].items() if k != "files"}
    return {
        "success": True,
        "restored_files": result["restored_files"],
        "safety_backup_id": result["safety_backup_id"],
        "requires_restart": result["requires_restart"],
        "manifest": manifest,
    }


@router.delete("/{backup_id}")
async def delete_backup(backup_id: str):
    deleted = await run_in_threadpool(backup_mgr.delete_backup, backup_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Backup not found.")
    return {"success": True}
