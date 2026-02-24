from fastapi import FastAPI, UploadFile, File, HTTPException, Form
import base64
import json
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import List

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
# History
# ------------------------------------------------------------------ #

@app.get("/api/history")
async def get_history(limit: int = 50, offset: int = 0):
    items = hist.get_history(limit=limit, offset=offset)
    total = hist.get_history_count()
    return {"success": True, "items": items, "total": total}


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
            loras = sd_client.get_loras()
        except Exception:
            pass
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
_VALID_FEATURES = {"generate", "sd", "img2img"}


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
    print(f"[API] GET /api/last-params/{feature} -> {len(params)} keys")
    print(f"[API] File exists: {_LAST_PARAMS_FILE.exists()}")
    print(f"[API] Return params: {params}")
    return {"success": True, "params": params}


@app.post("/api/last-params/{feature}")
async def save_last_params(feature: str, request_data: dict):
    if feature not in _VALID_FEATURES:
        raise HTTPException(status_code=400, detail="Invalid feature name.")
    data = _read_last_params()
    data[feature] = request_data
    _write_last_params(data)
    print(f"[API] POST /api/last-params/{feature} -> Saved {len(request_data)} keys")
    print(f"[API] File path: {_LAST_PARAMS_FILE}")
    print(f"[API] File exists: {_LAST_PARAMS_FILE.exists()}")
    return {"success": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=API_HOST, port=API_PORT, reload=DEBUG)
