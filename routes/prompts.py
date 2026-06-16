"""Prompt generation endpoints."""

from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.concurrency import run_in_threadpool
from typing import List

import presets as preset_mgr
import history as hist
from config import ALLOWED_IMAGE_TYPES, MAX_IMAGE_SIZE
from deps import prompt_generator, llm_cache, _validate_image_bytes

router = APIRouter(prefix="/api", tags=["prompts"])


# ------------------------------------------------------------------ #
# Prompt Generation (single image)
# ------------------------------------------------------------------ #

@router.post("/generate-prompts")
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

    _validate_image_bytes(contents)

    preset = preset_mgr.get_preset(preset_id) if preset_id else None
    suffix_pos = preset.get("positive_suffix", "") if preset else ""
    suffix_neg = preset.get("negative_suffix", "") if preset else ""

    eff_style = style or (preset.get("style", "") if preset else "")
    eff_tone = tone or (preset.get("tone", "") if preset else "")
    eff_quality = quality or (preset.get("quality", "high") if preset else "high")

    cached = llm_cache.get(contents, None, eff_style, eff_tone, eff_quality)
    if cached is not None:
        result = cached
    else:
        result = await run_in_threadpool(
            prompt_generator.generate_prompts,
            contents,
            style=eff_style,
            tone=eff_tone,
            quality=eff_quality,
            preset_suffix_positive=suffix_pos,
            preset_suffix_negative=suffix_neg
        )
        if result.get("status") == "success":
            llm_cache.set(contents, None, eff_style, eff_tone, eff_quality, result)

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

@router.post("/generate-prompts-batch")
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

        try:
            _validate_image_bytes(contents)
        except HTTPException as exc:
            results.append({"filename": f.filename, "success": False, "error": exc.detail})
            continue

        r = await run_in_threadpool(
            prompt_generator.generate_prompts,
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

@router.post("/generate-prompts-text")
def generate_prompts_text(request_data: dict):
    description = request_data.get("description", "").strip()
    if not description:
        raise HTTPException(status_code=400, detail="Description is required.")

    if len(description) > 5000:
        raise HTTPException(status_code=422, detail="Description must not exceed 5000 characters.")

    style = request_data.get("style", "")
    tone = request_data.get("tone", "")
    quality = request_data.get("quality", "high")
    preset_id = request_data.get("preset_id", "")
    save = request_data.get("save_history", True)

    preset = preset_mgr.get_preset(preset_id) if preset_id else None
    suffix_pos = preset.get("positive_suffix", "") if preset else ""
    suffix_neg = preset.get("negative_suffix", "") if preset else ""

    eff_style = style or (preset.get("style", "") if preset else "")
    eff_tone = tone or (preset.get("tone", "") if preset else "")
    eff_quality = quality or (preset.get("quality", "high") if preset else "high")

    cached = llm_cache.get(None, description, eff_style, eff_tone, eff_quality)
    if cached is not None:
        result = cached
    else:
        result = prompt_generator.generate_prompts_text_only(
            description,
            style=eff_style,
            tone=eff_tone,
            quality=eff_quality,
            preset_suffix_positive=suffix_pos,
            preset_suffix_negative=suffix_neg
        )
        if result.get("status") == "success":
            llm_cache.set(None, description, eff_style, eff_tone, eff_quality, result)

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

@router.post("/refine-prompt")
def refine_prompt(request_data: dict):
    positive = request_data.get("positive", "").strip()
    if not positive:
        raise HTTPException(status_code=400, detail="Positive prompt is required.")

    if len(positive) > 10000:
        raise HTTPException(status_code=422, detail="Positive prompt must not exceed 10000 characters.")

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

    hist.save_history(
        positive=result["positive"],
        negative=result["negative"],
        image_name="[refine]",
        style=style,
        tone=tone,
        quality=quality
    )

    return {
        "success": True,
        "data": {
            "positive": result["positive"],
            "negative": result["negative"],
            "changes": result.get("changes", "")
        }
    }
