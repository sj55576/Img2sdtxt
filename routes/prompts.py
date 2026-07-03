"""Prompt generation endpoints."""

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import iterate_in_threadpool, run_in_threadpool
from fastapi.responses import StreamingResponse

import deps
import history as hist
import presets as preset_mgr
from config import ALLOWED_IMAGE_TYPES, MAX_IMAGE_SIZE
from deps import _validate_image_bytes
from models import RefinePromptRequest, TextPromptRequest

logger = logging.getLogger("img2sdtxt.prompts")

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
    save_history: bool = Form(True),
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

    _prov = deps.llm_client.provider_name
    _mdl = deps.llm_client.model
    cached = deps.llm_cache.get(contents, None, eff_style, eff_tone, eff_quality, provider=_prov, model=_mdl)
    if cached is not None:
        result = cached
    else:
        result = await run_in_threadpool(
            deps.prompt_generator.generate_prompts,
            contents,
            style=eff_style,
            tone=eff_tone,
            quality=eff_quality,
            preset_suffix_positive=suffix_pos,
            preset_suffix_negative=suffix_neg,
        )
        if result.get("status") == "success":
            deps.llm_cache.set(contents, None, eff_style, eff_tone, eff_quality, result, provider=_prov, model=_mdl)

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error"))

    history_id = None
    if save_history:
        history_id = hist.save_history(
            positive=result["positive"],
            negative=result["negative"],
            image_name=file.filename or "",
            style=style,
            tone=tone,
            quality=quality,
        )

    response = {"success": True, "data": {"positive": result["positive"], "negative": result["negative"]}}
    if history_id is not None:
        response["history_id"] = history_id
    return response


# ------------------------------------------------------------------ #
# Prompt Generation (streaming / SSE)
# ------------------------------------------------------------------ #


def _sse_event(event: str, data: dict) -> str:
    """SSE 1イベント分の文字列を組み立てる"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/generate-prompts-stream")
async def generate_prompts_stream(
    file: Optional[UploadFile] = File(None),
    description: str = Form(""),
    style: str = Form(""),
    tone: str = Form(""),
    quality: str = Form("high"),
    preset_id: str = Form(""),
    save_history: bool = Form(True),
):
    """プロンプト生成を SSE でストリーミングする。

    画像 (file) またはテキスト (description) のどちらかを入力とする。
    イベント: start → token* → done、エラー時は error。
    非ストリーミング対応プロバイダーは基底クラスのフォールバックにより一括1チャンクで届く。
    """
    contents: Optional[bytes] = None
    image_name = "[text input]"
    if file is not None and file.filename:
        if file.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail="Invalid image type.")
        contents = await file.read()
        if len(contents) > MAX_IMAGE_SIZE:
            raise HTTPException(status_code=400, detail="Image too large (max 10MB).")
        _validate_image_bytes(contents)
        image_name = file.filename

    desc = description.strip()
    if contents is None and not desc:
        raise HTTPException(status_code=400, detail="Either an image file or a description is required.")

    preset = preset_mgr.get_preset(preset_id) if preset_id else None
    suffix_pos = preset.get("positive_suffix", "") if preset else ""
    suffix_neg = preset.get("negative_suffix", "") if preset else ""
    eff_style = style or (preset.get("style", "") if preset else "")
    eff_tone = tone or (preset.get("tone", "") if preset else "")
    eff_quality = quality or (preset.get("quality", "high") if preset else "high")

    provider = deps.llm_client
    generator = deps.prompt_generator
    prov_name = provider.provider_name
    mdl = provider.model

    cache_image = contents
    cache_text = None if contents is not None else desc
    cached = deps.llm_cache.get(
        cache_image, cache_text, eff_style, eff_tone, eff_quality, provider=prov_name, model=mdl
    )

    async def event_stream():
        yield _sse_event("start", {"provider": prov_name, "model": mdl, "cached": cached is not None})

        if cached is not None:
            result = cached
        else:
            if contents is not None:
                prompt = generator.build_image_analysis_prompt(eff_style, eff_tone, eff_quality)
                chunk_iter = provider.generate_response_with_image_stream(prompt, contents)
            else:
                prompt = generator.build_text_prompt(desc, eff_style, eff_tone, eff_quality)
                chunk_iter = provider.generate_response_stream(prompt)

            parts: List[str] = []
            try:
                async for chunk in iterate_in_threadpool(chunk_iter):
                    parts.append(chunk)
                    yield _sse_event("token", {"text": chunk})
            except Exception as e:
                logger.error("generate_prompts_stream error: %s", str(e))
                yield _sse_event("error", {"error": str(e)})
                return

            full_text = "".join(parts)
            if not full_text:
                yield _sse_event("error", {"error": "LLMからレスポンスがありません"})
                return

            result = generator.finalize_response(full_text, suffix_pos, suffix_neg)
            if result.get("status") == "success":
                deps.llm_cache.set(
                    cache_image, cache_text, eff_style, eff_tone, eff_quality, result,
                    provider=prov_name, model=mdl,
                )

        if result.get("status") == "error":
            yield _sse_event("error", {"error": result.get("error", "unknown error")})
            return

        history_id = None
        if save_history:
            history_id = hist.save_history(
                positive=result["positive"],
                negative=result["negative"],
                image_name=image_name,
                style=style,
                tone=tone,
                quality=quality,
            )

        done: dict = {
            "positive": result["positive"],
            "negative": result["negative"],
            "cached": cached is not None,
        }
        if history_id is not None:
            done["history_id"] = history_id
        yield _sse_event("done", done)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ------------------------------------------------------------------ #
# Prompt Generation (batch)
# ------------------------------------------------------------------ #


@router.post("/generate-prompts-batch")
async def generate_prompts_batch(
    files: List[UploadFile] = File(...),
    style: str = Form(""),
    tone: str = Form(""),
    quality: str = Form("high"),
    preset_id: str = Form(""),
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
            deps.prompt_generator.generate_prompts,
            contents,
            style=eff_style,
            tone=eff_tone,
            quality=eff_quality,
            preset_suffix_positive=suffix_pos,
            preset_suffix_negative=suffix_neg,
        )

        if r.get("status") == "success":
            hist.save_history(
                positive=r["positive"],
                negative=r["negative"],
                image_name=f.filename or "",
                style=eff_style,
                tone=eff_tone,
                quality=eff_quality,
            )
            results.append(
                {"filename": f.filename, "success": True, "positive": r["positive"], "negative": r["negative"]}
            )
        else:
            results.append({"filename": f.filename, "success": False, "error": r.get("error")})

    return {"success": True, "results": results, "total": len(files), "processed": len(results)}


# ------------------------------------------------------------------ #
# Prompt Generation (text)
# ------------------------------------------------------------------ #


@router.post("/generate-prompts-text")
def generate_prompts_text(request: TextPromptRequest):
    description = request.description.strip()
    style = request.style
    tone = request.tone
    quality = request.quality
    preset_id = request.preset_id
    save = request.save_history

    preset = preset_mgr.get_preset(preset_id) if preset_id else None
    suffix_pos = preset.get("positive_suffix", "") if preset else ""
    suffix_neg = preset.get("negative_suffix", "") if preset else ""

    eff_style = style or (preset.get("style", "") if preset else "")
    eff_tone = tone or (preset.get("tone", "") if preset else "")
    eff_quality = quality or (preset.get("quality", "high") if preset else "high")

    _prov = deps.llm_client.provider_name
    _mdl = deps.llm_client.model
    cached = deps.llm_cache.get(None, description, eff_style, eff_tone, eff_quality, provider=_prov, model=_mdl)
    if cached is not None:
        result = cached
    else:
        result = deps.prompt_generator.generate_prompts_text_only(
            description,
            style=eff_style,
            tone=eff_tone,
            quality=eff_quality,
            preset_suffix_positive=suffix_pos,
            preset_suffix_negative=suffix_neg,
        )
        if result.get("status") == "success":
            deps.llm_cache.set(None, description, eff_style, eff_tone, eff_quality, result, provider=_prov, model=_mdl)

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error"))

    history_id = None
    if save:
        history_id = hist.save_history(
            positive=result["positive"],
            negative=result["negative"],
            image_name="[text input]",
            style=style,
            tone=tone,
            quality=quality,
        )

    response = {"success": True, "data": {"positive": result["positive"], "negative": result["negative"]}}
    if history_id is not None:
        response["history_id"] = history_id
    return response


# ------------------------------------------------------------------ #
# Prompt Refinement
# ------------------------------------------------------------------ #


@router.post("/refine-prompt")
def refine_prompt(request: RefinePromptRequest):
    result = deps.prompt_generator.refine_prompt(
        positive=request.positive.strip(),
        negative=request.negative.strip(),
        instruction=request.instruction.strip(),
        style=request.style,
        tone=request.tone,
        quality=request.quality,
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error"))

    history_id = hist.save_history(
        positive=result["positive"],
        negative=result["negative"],
        image_name="[refine]",
        style=request.style,
        tone=request.tone,
        quality=request.quality,
        parent_id=request.parent_id,
    )

    return {
        "success": True,
        "data": {"positive": result["positive"], "negative": result["negative"], "changes": result.get("changes", "")},
        "history_id": history_id,
    }
