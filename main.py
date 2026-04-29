from fastapi import FastAPI, UploadFile, File, HTTPException, Form
import base64
import json
import time
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import List, Optional
from PIL import Image

from config import (
    API_HOST, API_PORT, DEBUG,
    ALLOWED_IMAGE_TYPES, MAX_IMAGE_SIZE,
    STYLES, TONES, QUALITY_LEVELS
)
from llm_client import LLMClient
from prompt_generator import PromptGenerator
from sd_client import SDClient
import history as hist
import presets as preset_mgr

app = FastAPI(
    title="Image to Stable Diffusion Prompt",
    description="Convert images to SD prompts using local LLM",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

llm_client = LLMClient()
prompt_generator = PromptGenerator(llm_client)
sd_client = SDClient()

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

outputs_dir = Path(__file__).parent / "outputs"
outputs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")


# ------------------------------------------------------------------ #
# Pages
# ------------------------------------------------------------------ #

@app.get("/")
async def root():
    return FileResponse("static/index.html")


# ------------------------------------------------------------------ #
# Health / Config
# ------------------------------------------------------------------ #

@app.get("/health")
async def health_check():
    try:
        response = llm_client.generate_response("Hello")
        status = "healthy" if response else "degraded"
        return {"status": status, "llm_server": "connected", "message": "OK"}
    except ConnectionError:
        raise HTTPException(status_code=503, detail="LLM server is not available.")
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/api/config")
async def get_config():
    from config import LLM_SERVER_URL, LLM_MODEL, SD_API_URL
    return {
        "llm_server": LLM_SERVER_URL,
        "model": LLM_MODEL,
        "sd_api": SD_API_URL,
        "styles": STYLES,
        "tones": TONES,
        "quality_levels": list(QUALITY_LEVELS.keys())
    }


# ------------------------------------------------------------------ #
# Prompt Generation (single image)
# ------------------------------------------------------------------ #

@app.post("/api/generate-prompts")
async def generate_prompts(
    file: UploadFile = File(...),
    style: str = Form(""),
    tone: str = Form(""),
    quality: str = Form("high"),
    preset_id: str = Form(""),
    save_history: bool = Form(True)
):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid image type.")

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image too large (max 10MB).")

    preset = preset_mgr.get_preset(preset_id) if preset_id else None
    suffix_pos = preset.get("positive_suffix", "") if preset else ""
    suffix_neg = preset.get("negative_suffix", "") if preset else ""

    result = prompt_generator.generate_prompts(
        contents,
        style=style or (preset.get("style", "") if preset else ""),
        tone=tone or (preset.get("tone", "") if preset else ""),
        quality=quality or (preset.get("quality", "high") if preset else "high"),
        preset_suffix_positive=suffix_pos,
        preset_suffix_negative=suffix_neg
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error"))

    if save_history:
        hist.save_history(
            positive=result["positive"],
            negative=result["negative"],
            image_name=file.filename or "",
            style=style, tone=tone, quality=quality
        )

    return {"success": True, "data": {"positive": result["positive"], "negative": result["negative"]}}


# ------------------------------------------------------------------ #
# Prompt Generation (batch)
# ------------------------------------------------------------------ #

@app.post("/api/generate-prompts-batch")
async def generate_prompts_batch(
    files: List[UploadFile] = File(...),
    style: str = Form(""),
    tone: str = Form(""),
    quality: str = Form("high"),
    preset_id: str = Form("")
):
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 images per batch.")

    preset = preset_mgr.get_preset(preset_id) if preset_id else None
    suffix_pos = preset.get("positive_suffix", "") if preset else ""
    suffix_neg = preset.get("negative_suffix", "") if preset else ""
    eff_style = style or (preset.get("style", "") if preset else "")
    eff_tone = tone or (preset.get("tone", "") if preset else "")
    eff_quality = quality or (preset.get("quality", "high") if preset else "high")

    results = []
    for f in files:
        if f.content_type not in ALLOWED_IMAGE_TYPES:
            results.append({"filename": f.filename, "success": False, "error": "Invalid image type"})
            continue

        contents = await f.read()
        if len(contents) > MAX_IMAGE_SIZE:
            results.append({"filename": f.filename, "success": False, "error": "File too large"})
            continue

        r = prompt_generator.generate_prompts(
            contents,
            style=eff_style, tone=eff_tone, quality=eff_quality,
            preset_suffix_positive=suffix_pos, preset_suffix_negative=suffix_neg
        )

        if r.get("status") == "success":
            hist.save_history(
                positive=r["positive"], negative=r["negative"],
                image_name=f.filename or "",
                style=eff_style, tone=eff_tone, quality=eff_quality
            )
            results.append({
                "filename": f.filename,
                "success": True,
                "positive": r["positive"],
                "negative": r["negative"]
            })
        else:
            results.append({"filename": f.filename, "success": False, "error": r.get("error")})

    return {"success": True, "results": results, "total": len(files), "processed": len(results)}


# ------------------------------------------------------------------ #
# Prompt Generation (text)
# ------------------------------------------------------------------ #

@app.post("/api/generate-prompts-text")
async def generate_prompts_text(request_data: dict):
    description = request_data.get("description", "").strip()
    if not description:
        raise HTTPException(status_code=400, detail="Description is required.")

    style = request_data.get("style", "")
    tone = request_data.get("tone", "")
    quality = request_data.get("quality", "high")
    preset_id = request_data.get("preset_id", "")
    save = request_data.get("save_history", True)

    preset = preset_mgr.get_preset(preset_id) if preset_id else None
    suffix_pos = preset.get("positive_suffix", "") if preset else ""
    suffix_neg = preset.get("negative_suffix", "") if preset else ""

    result = prompt_generator.generate_prompts_text_only(
        description,
        style=style or (preset.get("style", "") if preset else ""),
        tone=tone or (preset.get("tone", "") if preset else ""),
        quality=quality or (preset.get("quality", "high") if preset else "high"),
        preset_suffix_positive=suffix_pos,
        preset_suffix_negative=suffix_neg
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error"))

    if save:
        hist.save_history(
            positive=result["positive"], negative=result["negative"],
            image_name="[text input]", style=style, tone=tone, quality=quality
        )

    return {"success": True, "data": {"positive": result["positive"], "negative": result["negative"]}}


# ------------------------------------------------------------------ #
# Prompt Refinement
# ------------------------------------------------------------------ #

@app.post("/api/refine-prompt")
async def refine_prompt(request_data: dict):
    positive = request_data.get("positive", "").strip()
    if not positive:
        raise HTTPException(status_code=400, detail="Positive prompt is required.")

    negative = request_data.get("negative", "").strip()
    instruction = request_data.get("instruction", "").strip()
    style = request_data.get("style", "")
    tone = request_data.get("tone", "")
    quality = request_data.get("quality", "high")

    result = prompt_generator.refine_prompt(
        positive=positive,
        negative=negative,
        instruction=instruction,
        style=style,
        tone=tone,
        quality=quality
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error"))

    return {
        "success": True,
        "data": {
            "positive": result["positive"],
            "negative": result["negative"],
            "changes": result.get("changes", "")
        }
    }


# ------------------------------------------------------------------ #
# History
# ------------------------------------------------------------------ #

@app.get("/api/history")
async def get_history(
    limit: int = 50,
    offset: int = 0,
    search: str = "",
    style: str = "",
    quality: str = "",
    favorites_only: bool = False
):
    items = hist.get_history(
        limit=limit, offset=offset,
        search=search, style=style, quality=quality,
        favorites_only=favorites_only
    )
    total = hist.get_history_count(
        search=search, style=style, quality=quality,
        favorites_only=favorites_only
    )
    return {"success": True, "items": items, "total": total}


@app.get("/api/history/export")
async def export_history():
    """全履歴をJSONとしてダウンロード"""
    from datetime import datetime as _dt
    from fastapi.responses import JSONResponse
    items = hist.get_history(limit=10000)
    return JSONResponse(
        content={"exported_at": _dt.now().isoformat(), "items": items},
        headers={"Content-Disposition": "attachment; filename=prompt_history.json"}
    )


@app.put("/api/history/{item_id}/favorite")
async def toggle_history_favorite(item_id: int):
    updated = hist.toggle_favorite(item_id)
    if not updated:
        raise HTTPException(status_code=404, detail="History item not found.")
    return {"success": True, "item": updated}


@app.delete("/api/history/{item_id}")
async def delete_history(item_id: int):
    deleted = hist.delete_history_item(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="History item not found.")
    return {"success": True}


@app.delete("/api/history")
async def clear_history():
    count = hist.clear_all_history()
    return {"success": True, "deleted": count}


# ------------------------------------------------------------------ #
# Presets
# ------------------------------------------------------------------ #

@app.get("/api/presets")
async def get_presets():
    return {"success": True, "presets": preset_mgr.get_all_presets()}


@app.post("/api/presets")
async def create_preset(preset: dict):
    for field in ["name", "positive_suffix", "negative_suffix"]:
        if not preset.get(field):
            raise HTTPException(status_code=400, detail=f"Field '{field}' is required.")
    new_preset = preset_mgr.add_preset(preset)
    return {"success": True, "preset": new_preset}


@app.delete("/api/presets/{preset_id}")
async def delete_preset(preset_id: str):
    deleted = preset_mgr.delete_preset(preset_id)
    if not deleted:
        raise HTTPException(status_code=400, detail="Cannot delete default preset or not found.")
    return {"success": True}


# ------------------------------------------------------------------ #
# Stable Diffusion API
# ------------------------------------------------------------------ #

@app.get("/api/sd/status")
async def sd_status():
    available = sd_client.is_available()
    model = ""
    samplers = []
    models = []
    upscalers = []
    loras = []
    if available:
        try:
            model = sd_client.get_current_model()
            samplers = sd_client.get_samplers()
            models = sd_client.get_model_list()
            upscalers = sd_client.get_upscalers()
        except Exception:
            pass
        loras = sd_client.get_loras()
    return {"available": available, "model": model, "samplers": samplers, "models": models, "upscalers": upscalers, "loras": loras}


@app.get("/api/sd/loras")
async def sd_loras_list():
    try:
        loras = sd_client.get_loras()
        return {"success": True, "loras": loras}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/api/sd/upscalers")
async def sd_upscalers():
    try:
        upscalers = sd_client.get_upscalers()
        return {"success": True, "upscalers": upscalers}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/api/sd/generate")
async def sd_generate(request_data: dict):
    positive = request_data.get("positive", "").strip()
    negative = request_data.get("negative", "").strip()
    if not positive:
        raise HTTPException(status_code=400, detail="Positive prompt is required.")

    width = int(request_data.get("width", 512))
    height = int(request_data.get("height", 512))
    steps = int(request_data.get("steps", 20))
    cfg_scale = float(request_data.get("cfg_scale", 7.0))
    sampler = request_data.get("sampler", "Euler a")
    seed = int(request_data.get("seed", -1))
    batch_size = min(int(request_data.get("batch_size", 1)), 4)
    model = request_data.get("model", "")
    loras = request_data.get("loras", "")
    enable_hr = bool(request_data.get("enable_hr", False))
    hr_scale = float(request_data.get("hr_scale", 2.0))
    hr_upscaler = request_data.get("hr_upscaler", "R-ESRGAN 4x+")
    hr_second_pass_steps = int(request_data.get("hr_second_pass_steps", 0))
    hr_denoising_strength = float(request_data.get("hr_denoising_strength", 0.7))

    try:
        images = sd_client.txt2img(
            positive=positive,
            negative=negative,
            width=width,
            height=height,
            steps=steps,
            cfg_scale=cfg_scale,
            sampler=sampler,
            seed=seed,
            batch_size=batch_size,
            model=model,
            loras=loras,
            enable_hr=enable_hr,
            hr_scale=hr_scale,
            hr_upscaler=hr_upscaler,
            hr_second_pass_steps=hr_second_pass_steps,
            hr_denoising_strength=hr_denoising_strength
        )

        # 画像を自動保存
        saved_files = sd_client.save_images(
            images=images,
            positive=positive,
            negative=negative,
            width=width,
            height=height,
            steps=steps,
            cfg_scale=cfg_scale,
            sampler=sampler,
            seed=seed,
            model=model,
            loras=loras
        )

        return {
            "success": True,
            "images": images,
            "count": len(images),
            "saved_files": saved_files
        }
    except ConnectionError:
        raise HTTPException(status_code=503, detail="Stable Diffusion API is not available.")
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Generation timed out.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sd/img2img")
async def sd_img2img(
    file: UploadFile = File(...),
    positive: str = Form(...),
    negative: str = Form(""),
    denoising_strength: float = Form(0.75),
    width: int = Form(512),
    height: int = Form(512),
    steps: int = Form(20),
    cfg_scale: float = Form(7.0),
    sampler: str = Form("Euler a"),
    seed: int = Form(-1),
    batch_size: int = Form(1),
    resize_mode: int = Form(0),
    model: str = Form(""),
    loras: str = Form(""),
    enable_hr: bool = Form(False),
    hr_scale: float = Form(2.0),
    hr_upscaler: str = Form("R-ESRGAN 4x+"),
    hr_second_pass_steps: int = Form(0),
    hr_denoising_strength: float = Form(0.7)
):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid image type.")

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image too large (max 10MB).")

    init_image = base64.b64encode(contents).decode("utf-8")

    try:
        images = sd_client.img2img(
            init_image=init_image,
            positive=positive,
            negative=negative,
            denoising_strength=denoising_strength,
            width=width,
            height=height,
            steps=steps,
            cfg_scale=cfg_scale,
            sampler=sampler,
            seed=seed,
            batch_size=min(batch_size, 4),
            resize_mode=resize_mode,
            model=model,
            loras=loras,
            enable_hr=enable_hr,
            hr_scale=hr_scale,
            hr_upscaler=hr_upscaler,
            hr_second_pass_steps=hr_second_pass_steps,
            hr_denoising_strength=hr_denoising_strength
        )

        saved_files = sd_client.save_images(
            images=images,
            positive=positive,
            negative=negative,
            width=width,
            height=height,
            steps=steps,
            cfg_scale=cfg_scale,
            sampler=sampler,
            seed=seed,
            model=model,
            loras=loras,
            mode="img2img",
            denoising_strength=denoising_strength
        )

        return {
            "success": True,
            "images": images,
            "count": len(images),
            "saved_files": saved_files
        }
    except ConnectionError:
        raise HTTPException(status_code=503, detail="Stable Diffusion API is not available.")
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Generation timed out.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sd/inpaint")
async def sd_inpaint(
    file: UploadFile = File(...),
    mask: str = Form(...),
    positive: str = Form(...),
    negative: str = Form(""),
    denoising_strength: float = Form(0.75),
    width: int = Form(512),
    height: int = Form(512),
    steps: int = Form(20),
    cfg_scale: float = Form(7.0),
    sampler: str = Form("Euler a"),
    seed: int = Form(-1),
    batch_size: int = Form(1),
    mask_blur: int = Form(4),
    inpainting_fill: int = Form(1),
    inpaint_full_res: bool = Form(True),
    inpaint_full_res_padding: int = Form(32),
    model: str = Form(""),
    loras: str = Form("")
):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid image type.")

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image too large (max 10MB).")

    init_image = base64.b64encode(contents).decode("utf-8")

    try:
        images = sd_client.inpaint(
            init_image=init_image,
            mask=mask,
            positive=positive,
            negative=negative,
            denoising_strength=denoising_strength,
            width=width,
            height=height,
            steps=steps,
            cfg_scale=cfg_scale,
            sampler=sampler,
            seed=seed,
            batch_size=min(batch_size, 4),
            mask_blur=mask_blur,
            inpainting_fill=inpainting_fill,
            inpaint_full_res=inpaint_full_res,
            inpaint_full_res_padding=inpaint_full_res_padding,
            model=model,
            loras=loras
        )

        saved_files = sd_client.save_images(
            images=images,
            positive=positive,
            negative=negative,
            width=width,
            height=height,
            steps=steps,
            cfg_scale=cfg_scale,
            sampler=sampler,
            seed=seed,
            model=model,
            loras=loras,
            mode="inpaint",
            denoising_strength=denoising_strength
        )

        return {
            "success": True,
            "images": images,
            "count": len(images),
            "saved_files": saved_files
        }
    except ConnectionError:
        raise HTTPException(status_code=503, detail="Stable Diffusion API is not available.")
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Generation timed out.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sd/generate-multi-model")
async def sd_generate_multi_model(request_data: dict):
    models = request_data.get("models", [])
    if not models:
        raise HTTPException(status_code=400, detail="At least one model is required.")

    positive = request_data.get("positive", "").strip()
    if not positive:
        raise HTTPException(status_code=400, detail="Positive prompt is required.")

    negative = request_data.get("negative", "").strip()
    width = int(request_data.get("width", 512))
    height = int(request_data.get("height", 512))
    steps = int(request_data.get("steps", 20))
    cfg_scale = float(request_data.get("cfg_scale", 7.0))
    sampler = request_data.get("sampler", "Euler a")
    seed = int(request_data.get("seed", -1))
    batch_size = min(int(request_data.get("batch_size", 1)), 4)
    loras = request_data.get("loras", "")
    enable_hr = bool(request_data.get("enable_hr", False))
    hr_scale = float(request_data.get("hr_scale", 2.0))
    hr_upscaler = request_data.get("hr_upscaler", "R-ESRGAN 4x+")
    hr_second_pass_steps = int(request_data.get("hr_second_pass_steps", 0))
    hr_denoising_strength = float(request_data.get("hr_denoising_strength", 0.7))

    results = []
    for model in models:
        try:
            images = sd_client.txt2img(
                positive=positive,
                negative=negative,
                width=width,
                height=height,
                steps=steps,
                cfg_scale=cfg_scale,
                sampler=sampler,
                seed=seed,
                batch_size=batch_size,
                model=model,
                loras=loras,
                enable_hr=enable_hr,
                hr_scale=hr_scale,
                hr_upscaler=hr_upscaler,
                hr_second_pass_steps=hr_second_pass_steps,
                hr_denoising_strength=hr_denoising_strength
            )
            saved_files = sd_client.save_images(
                images=images,
                positive=positive,
                negative=negative,
                width=width,
                height=height,
                steps=steps,
                cfg_scale=cfg_scale,
                sampler=sampler,
                seed=seed,
                model=model,
                loras=loras
            )
            results.append({
                "model": model,
                "success": True,
                "images": images,
                "count": len(images),
                "saved_files": saved_files
            })
        except Exception as e:
            results.append({
                "model": model,
                "success": False,
                "error": str(e)
            })

    return {"success": True, "results": results, "total_models": len(models)}


@app.get("/api/sd/models")
async def sd_models():
    try:
        models = sd_client.get_models()
        return {"success": True, "models": [m.get("model_name", m.get("title", "")) for m in models]}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ------------------------------------------------------------------ #
# Last Parameter History
# ------------------------------------------------------------------ #

_DATA_DIR = Path(__file__).parent / "data"
_LAST_PARAMS_FILE = _DATA_DIR / "last_params.json"
_VALID_FEATURES = {"generate", "sd", "img2img", "inpaint"}


def _read_last_params() -> dict:
    if _LAST_PARAMS_FILE.exists():
        try:
            return json.loads(_LAST_PARAMS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _write_last_params(data: dict):
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _LAST_PARAMS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@app.get("/api/last-params/{feature}")
async def get_last_params(feature: str):
    if feature not in _VALID_FEATURES:
        raise HTTPException(status_code=400, detail="Invalid feature name.")
    data = _read_last_params()
    params = data.get(feature, {})
    return {"success": True, "params": params}


@app.post("/api/last-params/{feature}")
async def save_last_params(feature: str, request_data: dict):
    if feature not in _VALID_FEATURES:
        raise HTTPException(status_code=400, detail="Invalid feature name.")
    data = _read_last_params()
    data[feature] = request_data
    _write_last_params(data)
    return {"success": True}


# ------------------------------------------------------------------ #
# Outputs Gallery
# ------------------------------------------------------------------ #

# date_str → (dir_mtime, cache_time, images_list) のインメモリキャッシュ
_gallery_cache: dict = {}
_GALLERY_CACHE_TTL = 30  # 秒


def _scan_date_dir(date_dir: Path, date_str: str) -> list:
    """date_dir 内の画像を全件スキャンして返す（キャッシュ対象）"""
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

        thumb_path = date_dir / "thumbs" / fname
        if not thumb_path.exists():
            try:
                thumbs_dir = date_dir / "thumbs"
                thumbs_dir.mkdir(exist_ok=True)
                with Image.open(img_file) as pil_img:
                    pil_img.thumbnail((200, 200), Image.LANCZOS)
                    pil_img.save(thumb_path, "JPEG", quality=80, optimize=True)
            except Exception as e:
                print(f"Warning: on-demand thumbnail generation failed for {fname}: {e}")
        thumb_url = f"/outputs/{date_str}/thumbs/{fname}" if thumb_path.exists() else None

        date_images.append({
            "date": date_str,
            "filename": fname,
            "url": f"/outputs/{date_str}/{fname}",
            "thumb_url": thumb_url,
            "mode": file_mode,
            "timestamp": timestamp,
            "parameters": meta.get("parameters", {}),
        })
    return date_images


@app.get("/api/outputs")
async def list_outputs(
    date: Optional[str] = None,
    mode: Optional[str] = None,
    limit: int = 24,
    offset: int = 0,
):
    """outputsフォルダの生成済み画像一覧を返す（ページネーション対応）"""
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be a positive integer.")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be non-negative.")

    _OUTPUTS_DIR = Path(__file__).parent / "outputs"
    if not _OUTPUTS_DIR.exists():
        return {"success": True, "images": [], "dates": [], "total": 0}

    dates = sorted(
        [d.name for d in _OUTPUTS_DIR.iterdir() if d.is_dir() and d.name != "thumbs"],
        reverse=True
    )

    target_dates = [date] if date else dates

    # 全件収集（キャッシュ活用）してからフィルタ・スライス
    all_images = []
    for date_str in target_dates:
        date_dir = _OUTPUTS_DIR / date_str
        if not date_dir.is_dir():
            continue

        dir_mtime = date_dir.stat().st_mtime
        cached = _gallery_cache.get(date_str)
        if cached and cached[0] == dir_mtime and (time.time() - cached[1]) < _GALLERY_CACHE_TTL:
            date_images = cached[2]
        else:
            date_images = _scan_date_dir(date_dir, date_str)
            _gallery_cache[date_str] = (dir_mtime, time.time(), date_images)

        if mode:
            all_images.extend(img for img in date_images if img["mode"] == mode)
        else:
            all_images.extend(date_images)

    total = len(all_images)
    page_images = all_images[offset: offset + limit]

    return {"success": True, "images": page_images, "dates": dates, "total": total}



def _run_batch_cli() -> None:
    """Parse CLI arguments and run batch or watch mode when --input-dir is given."""
    import argparse
    from batch_processor import BatchProcessor

    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "Img2sdtxt — Image to Stable Diffusion Prompt Generator.\n"
            "Run without --input-dir to start the web server."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input-dir",
        dest="input_dirs",
        metavar="PATH",
        action="append",
        default=None,
        help="Directory containing images to process (can be specified multiple times).",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        metavar="PATH",
        default="./outputs",
        help="Directory where results are saved (default: ./outputs).",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch mode: monitor input directories and process new files automatically.",
    )
    parser.add_argument(
        "--format",
        dest="fmt",
        choices=["json", "txt", "both"],
        default="json",
        help="Output format (default: json).",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively scan sub-directories.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        metavar="N",
        help="Number of parallel workers (default: 1). Increase with care due to LLM rate limits.",
    )
    parser.add_argument(
        "--skip-existing",
        dest="skip_existing",
        action="store_true",
        help="Skip images that already have an output file.",
    )

    args, _unknown = parser.parse_known_args()

    if args.input_dirs is None:
        # No --input-dir → start the web server
        import uvicorn
        uvicorn.run(app, host=API_HOST, port=API_PORT, reload=DEBUG)
        return

    input_paths = [Path(d) for d in args.input_dirs]
    for p in input_paths:
        if not p.is_dir():
            parser.error(f"--input-dir '{p}' is not a valid directory.")

    output_path = Path(args.output_dir)

    processor = BatchProcessor(llm_client, concurrency=args.concurrency)

    if args.watch:
        processor.watch(
            input_dirs=input_paths,
            output_dir=output_path,
            fmt=args.fmt,
            recursive=args.recursive,
            skip_existing=args.skip_existing,
        )
    else:
        processor.run(
            input_dirs=input_paths,
            output_dir=output_path,
            fmt=args.fmt,
            recursive=args.recursive,
            skip_existing=args.skip_existing,
        )

if __name__ == "__main__":
    _run_batch_cli()
