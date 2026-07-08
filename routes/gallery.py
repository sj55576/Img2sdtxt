"""Gallery/outputs, last-params, and LLM cache endpoints."""

import io
import json
import os
import re
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from PIL import Image

from deps import llm_cache

router = APIRouter(prefix="/api", tags=["gallery"])

# ------------------------------------------------------------------ #
# Gallery cache
# ------------------------------------------------------------------ #

_gallery_cache: dict = {}
_gallery_cache_lock = threading.Lock()
_GALLERY_CACHE_TTL = 30  # seconds


def _scan_date_dir(date_dir: Path, date_str: str) -> list:
    """Scan all images in date_dir and return their metadata (cached)."""
    metadata_map = {}
    for meta_file in sorted(date_dir.glob("*_metadata.json")):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            ts = meta.get("timestamp", "")
            metadata_map[ts] = meta
        except Exception:
            pass

    date_images = []
    for img_file in sorted(date_dir.glob("*.png"), reverse=True):
        fname = img_file.name
        parts = fname.replace(".png", "").split("_")
        if parts[0] == "i2i":
            file_mode = "img2img"
        elif parts[0] == "inp":
            file_mode = "inpaint"
        else:
            file_mode = "txt2img"

        timestamp = "_".join(parts[1:3]) if len(parts) >= 3 else ""
        meta = metadata_map.get(timestamp, {})

        stem = img_file.stem
        thumbs_dir = date_dir / "thumbs"
        thumb_jpg = thumbs_dir / f"{stem}.jpg"
        thumb_png_legacy = thumbs_dir / f"{fname}"

        if thumb_jpg.exists():
            thumb_url = f"/outputs/{date_str}/thumbs/{stem}.jpg"
        elif thumb_png_legacy.exists():
            thumb_url = f"/outputs/{date_str}/thumbs/{fname}"
        else:
            thumb_path = thumb_jpg
            try:
                thumbs_dir.mkdir(exist_ok=True)
                with Image.open(img_file) as pil_img:
                    pil_img.thumbnail((200, 200), Image.LANCZOS)
                    pil_img.save(thumb_path, "JPEG", quality=80, optimize=True)
                thumb_url = f"/outputs/{date_str}/thumbs/{stem}.jpg"
            except Exception as e:
                print(f"Warning: on-demand thumbnail generation failed for {fname}: {e}")
                thumb_url = None

        date_images.append(
            {
                "date": date_str,
                "filename": fname,
                "url": f"/outputs/{date_str}/{fname}",
                "thumb_url": thumb_url,
                "mode": file_mode,
                "timestamp": timestamp,
                "parameters": meta.get("parameters", {}),
            }
        )
    return date_images


# ------------------------------------------------------------------ #
# Outputs gallery
# ------------------------------------------------------------------ #

_OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"


@router.get("/outputs/filters")
def get_gallery_filters():
    """Return distinct model names and sampler names from gallery metadata."""
    models: set[str] = set()
    samplers: set[str] = set()

    if not _OUTPUTS_DIR.exists():
        return {"success": True, "models": [], "samplers": []}

    for meta_file in _OUTPUTS_DIR.glob("*/*_metadata.json"):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            params = meta.get("parameters", {})
            model_val = params.get("model") or ""
            if model_val:
                models.add(model_val)
            sampler_val = params.get("sampler") or ""
            if sampler_val:
                samplers.add(sampler_val)
        except Exception:
            continue

    return {
        "success": True,
        "models": sorted(models),
        "samplers": sorted(samplers),
    }


@router.post("/outputs/download-zip")
async def download_zip(request_data: dict):
    """Create and return a ZIP archive of the requested output image files."""
    paths = request_data.get("paths", [])
    if not isinstance(paths, list):
        raise HTTPException(status_code=422, detail="paths must be a list.")
    if len(paths) > 100:
        raise HTTPException(status_code=400, detail="Cannot download more than 100 files at once.")

    outputs_resolved = _OUTPUTS_DIR.resolve()

    def _build_zip() -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for raw_path in paths:
                # Strip leading slash so Path() doesn't treat it as absolute
                relative = raw_path.lstrip("/")
                # The paths are expected to start with "outputs/..."
                # Resolve against the parent of _OUTPUTS_DIR for safety
                candidate = (_OUTPUTS_DIR.parent / relative).resolve()
                try:
                    arc_name = candidate.relative_to(outputs_resolved)
                except ValueError:
                    continue  # path traversal attempt – skip silently
                if not candidate.is_file():
                    continue  # missing file – skip silently
                # Use the path relative to outputs dir as the name inside the ZIP
                zf.write(candidate, arcname=arc_name)
        return buf.getvalue()

    zip_bytes = await run_in_threadpool(_build_zip)

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="images.zip"'},
    )


@router.get("/outputs")
def list_outputs(
    date: Optional[str] = None,
    mode: Optional[str] = None,
    limit: int = 24,
    offset: int = 0,
    search: Optional[str] = None,
    model: Optional[str] = None,
    sampler: Optional[str] = None,
):
    """Return a paginated list of generated images from the outputs folder."""
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be a positive integer.")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be non-negative.")

    if date is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise HTTPException(status_code=422, detail="date must be in YYYY-MM-DD format.")

    if not _OUTPUTS_DIR.exists():
        return {"success": True, "images": [], "dates": [], "total": 0}

    dates = sorted([d.name for d in _OUTPUTS_DIR.iterdir() if d.is_dir() and d.name != "thumbs"], reverse=True)

    target_dates = [date] if date else dates

    all_images: list[dict] = []
    for date_str in target_dates:
        date_dir = _OUTPUTS_DIR / date_str
        if not date_dir.is_dir():
            continue

        dir_mtime = date_dir.stat().st_mtime

        with _gallery_cache_lock:
            cached = _gallery_cache.get(date_str)
            if cached and cached[0] == dir_mtime and (time.time() - cached[1]) < _GALLERY_CACHE_TTL:
                date_images = cached[2]
            else:
                date_images = None

        if date_images is None:
            date_images = _scan_date_dir(date_dir, date_str)
            with _gallery_cache_lock:
                _gallery_cache[date_str] = (dir_mtime, time.time(), date_images)

        if mode:
            all_images.extend(img for img in date_images if img["mode"] == mode)
        else:
            all_images.extend(date_images)

    if search:
        search_lower = search.lower()
        all_images = [
            img
            for img in all_images
            if search_lower
            in (
                img.get("parameters", {}).get("positive_prompt", "")
                + " "
                + img.get("parameters", {}).get("negative_prompt", "")
            ).lower()
        ]
    if model:
        model_lower = model.lower()
        all_images = [
            img for img in all_images if model_lower in (img.get("parameters", {}).get("model", "") or "").lower()
        ]
    if sampler:
        sampler_lower = sampler.lower()
        all_images = [
            img for img in all_images if (img.get("parameters", {}).get("sampler", "") or "").lower() == sampler_lower
        ]

    total = len(all_images)
    page_images = all_images[offset : offset + limit]

    return {"success": True, "images": page_images, "dates": dates, "total": total}


# ------------------------------------------------------------------ #
# Last parameter persistence
# ------------------------------------------------------------------ #

_DATA_DIR = Path(__file__).parent.parent / "data"
_LAST_PARAMS_FILE = _DATA_DIR / "last_params.json"
_VALID_FEATURES = {"generate", "sd", "img2img", "inpaint", "multi_model"}
_last_params_lock = threading.Lock()


def _read_last_params() -> dict:
    if _LAST_PARAMS_FILE.exists():
        try:
            return json.loads(_LAST_PARAMS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _write_last_params(data: dict):
    """Atomically update last_params.json."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, ensure_ascii=False, indent=2)
    fd, tmp_path = tempfile.mkstemp(dir=str(_DATA_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(_LAST_PARAMS_FILE))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


@router.get("/last-params/{feature}")
def get_last_params(feature: str):
    if feature not in _VALID_FEATURES:
        raise HTTPException(status_code=400, detail="Invalid feature name.")
    with _last_params_lock:
        data = _read_last_params()
    params = data.get(feature, {})
    return {"success": True, "params": params}


@router.post("/last-params/{feature}")
def save_last_params(feature: str, request_data: dict):
    if feature not in _VALID_FEATURES:
        raise HTTPException(status_code=400, detail="Invalid feature name.")
    with _last_params_lock:
        data = _read_last_params()
        data[feature] = request_data
        _write_last_params(data)
    return {"success": True}


# ------------------------------------------------------------------ #
# LLM cache stats/clear
# ------------------------------------------------------------------ #


@router.get("/cache/stats")
async def cache_stats():
    return llm_cache.stats()


@router.delete("/cache")
async def clear_cache():
    count = llm_cache.clear()
    return {"cleared": count}
