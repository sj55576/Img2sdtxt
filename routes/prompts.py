"""Prompt generation endpoints."""

import json
import logging
import time
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import iterate_in_threadpool, run_in_threadpool
from fastapi.responses import StreamingResponse

import deps
import history as hist
import presets as preset_mgr
from config import ALLOWED_IMAGE_TYPES, MAX_IMAGE_SIZE
from deps import _validate_image_bytes
from metrics import observe_llm_request
from models import RefinePromptRequest, TextPromptRequest
from tracing import llm_span, record_llm_span_result
from validators import validate_quality, validate_style, validate_tone

logger = logging.getLogger("img2sdtxt.prompts")

router = APIRouter(prefix="/api", tags=["prompts"])

ANALYSIS_MODES = ("llm", "tagger", "hybrid")
TAGGER_MODELS = ("clip", "deepdanbooru")


def _cache_lookup(
    image_bytes: Optional[bytes],
    text_input: Optional[str],
    style: str,
    tone: str,
    quality: str,
    mode: str = "llm",
    tagger_model: str = "",
) -> tuple[Optional[dict], tuple[str, str]]:
    """Look up concrete provider keys in fallback order and return the hit identity."""
    identities = deps.get_llm_cache_identities()
    fallback_identity = identities[0] if identities else ("", "")
    for provider, model in identities:
        cached = deps.llm_cache.get(
            image_bytes,
            text_input,
            style,
            tone,
            quality,
            provider=provider,
            model=model,
            mode=mode,
            tagger_model=tagger_model,
        )
        if cached is not None:
            cached = dict(cached)
            cached.setdefault("provider", provider)
            cached.setdefault("model", model)
            return cached, (provider, model)
    return None, fallback_identity


def _result_identity(result: dict, fallback: tuple[str, str]) -> tuple[str, str]:
    provider = result.get("provider") or fallback[0]
    model = result.get("model") or fallback[1]
    return (
        provider if isinstance(provider, str) else fallback[0],
        model if isinstance(model, str) else fallback[1],
    )


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
    analysis_mode: str = Form("llm"),
    tagger_model: str = Form("clip"),
):
    if analysis_mode not in ANALYSIS_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid analysis_mode. Must be one of {ANALYSIS_MODES}.")
    if tagger_model not in TAGGER_MODELS:
        raise HTTPException(status_code=400, detail=f"Invalid tagger_model. Must be one of {TAGGER_MODELS}.")
    style = validate_style(style)
    tone = validate_tone(tone)
    quality = validate_quality(quality)

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

    async def _interrogate() -> str:
        """CLIP Interrogator / WD14 タガーで画像をタグ化する（エラーはHTTPエラーに変換）"""
        try:
            caption = await run_in_threadpool(deps.sd_client.interrogate, contents, tagger_model)
        except ConnectionError:
            raise HTTPException(status_code=502, detail="Stable Diffusion API is not available.")
        except TimeoutError:
            raise HTTPException(status_code=504, detail="Interrogate timed out.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        if not caption:
            raise HTTPException(status_code=502, detail="Interrogate returned no result.")
        return caption

    if analysis_mode == "tagger":
        # LLMを使わずタガーの結果のみからプロンプトを組み立てる（キャッシュ不要）
        result = deps.prompt_generator.build_tagger_prompt(
            await _interrogate(),
            quality=eff_quality,
            preset_suffix_positive=suffix_pos,
            preset_suffix_negative=suffix_neg,
        )
    else:
        cached, cache_identity = _cache_lookup(
            contents,
            None,
            eff_style,
            eff_tone,
            eff_quality,
            mode=analysis_mode,
            tagger_model=tagger_model if analysis_mode == "hybrid" else "",
        )
        if cached is not None:
            result = cached
        else:
            # hybrid モードの interrogate はキャッシュミス時のみ実行する
            # （タガー出力はキャッシュキーに含まれないため、ヒット時は不要）
            tagger_tags = await _interrogate() if analysis_mode == "hybrid" else ""
            result = await run_in_threadpool(
                deps.prompt_generator.generate_prompts,
                contents,
                style=eff_style,
                tone=eff_tone,
                quality=eff_quality,
                preset_suffix_positive=suffix_pos,
                preset_suffix_negative=suffix_neg,
                tagger_tags=tagger_tags,
            )
            if result.get("status") == "success":
                result.setdefault("provider", cache_identity[0])
                result.setdefault("model", cache_identity[1])
                result_identity = _result_identity(result, cache_identity)
                deps.llm_cache.set(
                    contents,
                    None,
                    eff_style,
                    eff_tone,
                    eff_quality,
                    result,
                    provider=result_identity[0],
                    model=result_identity[1],
                    mode=analysis_mode,
                    tagger_model=tagger_model if analysis_mode == "hybrid" else "",
                )

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
            provider=str(result.get("provider") or ""),
            model=str(result.get("model") or ""),
        )

    data = {"positive": result["positive"], "negative": result["negative"]}
    for key in ("provider", "model"):
        if result.get(key):
            data[key] = result[key]
    response = {"success": True, "data": data}
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
    style = validate_style(style)
    tone = validate_tone(tone)
    quality = validate_quality(quality)

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

    cache_image = contents
    cache_text = None if contents is not None else desc
    cached, cache_identity = _cache_lookup(
        cache_image,
        cache_text,
        eff_style,
        eff_tone,
        eff_quality,
    )
    prov_name, mdl = cache_identity

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
            last_chunk = None
            stream_started = time.monotonic()
            with llm_span(prov_name, mdl, "stream") as span:
                try:
                    async for chunk in iterate_in_threadpool(chunk_iter):
                        last_chunk = chunk
                        parts.append(str(chunk))
                        yield _sse_event("token", {"text": chunk})
                except Exception as e:
                    duration = time.monotonic() - stream_started
                    observe_llm_request(prov_name, mdl, "stream", "error", duration)
                    record_llm_span_result(span, prov_name, mdl, "error", duration)
                    logger.error("generate_prompts_stream error: %s", str(e))
                    yield _sse_event("error", {"error": str(e)})
                    return

                actual_provider = getattr(last_chunk, "provider_name", prov_name)
                actual_model = getattr(last_chunk, "model", mdl)
                if not isinstance(actual_provider, str):
                    actual_provider = prov_name
                if not isinstance(actual_model, str):
                    actual_model = mdl

                full_text = "".join(parts)
                if not full_text:
                    duration = time.monotonic() - stream_started
                    observe_llm_request(actual_provider, actual_model, "stream", "empty", duration)
                    record_llm_span_result(span, actual_provider, actual_model, "empty", duration)
                    yield _sse_event("error", {"error": "LLMからレスポンスがありません"})
                    return

                duration = time.monotonic() - stream_started
                observe_llm_request(actual_provider, actual_model, "stream", "success", duration)
                record_llm_span_result(span, actual_provider, actual_model, "success", duration)
            result = generator.finalize_response(full_text, suffix_pos, suffix_neg)
            result["provider"] = actual_provider
            result["model"] = actual_model
            if result.get("status") == "success":
                deps.llm_cache.set(
                    cache_image,
                    cache_text,
                    eff_style,
                    eff_tone,
                    eff_quality,
                    result,
                    provider=actual_provider,
                    model=actual_model,
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
                provider=str(result.get("provider") or ""),
                model=str(result.get("model") or ""),
            )

        done: dict = {
            "positive": result["positive"],
            "negative": result["negative"],
            "cached": cached is not None,
        }
        if result.get("provider"):
            done["provider"] = result["provider"]
        if result.get("model"):
            done["model"] = result["model"]
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
    style = validate_style(style)
    tone = validate_tone(tone)
    quality = validate_quality(quality)

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
                provider=str(r.get("provider") or ""),
                model=str(r.get("model") or ""),
            )
            results.append(
                {
                    "filename": f.filename,
                    "success": True,
                    "positive": r["positive"],
                    "negative": r["negative"],
                    "provider": r.get("provider", ""),
                    "model": r.get("model", ""),
                }
            )
        else:
            results.append({"filename": f.filename, "success": False, "error": r.get("error")})

    return {"success": True, "results": results, "total": len(files), "processed": len(results)}


@router.post("/generate-prompts-blend")
async def generate_prompts_blend(
    files: List[UploadFile] = File(...),
    roles: List[str] = Form(...),
    style: str = Form(""),
    tone: str = Form(""),
    quality: str = Form("high"),
    preset_id: str = Form(""),
    save_history: bool = Form(True),
):
    """Create one prompt from 2–3 labelled reference images."""
    if not 2 <= len(files) <= 3:
        raise HTTPException(status_code=400, detail="Provide 2 to 3 reference images.")
    if len(roles) != len(files):
        raise HTTPException(status_code=400, detail="Provide one role for each reference image.")
    cleaned_roles = [role.strip() for role in roles]
    if any(not role or len(role) > 80 for role in cleaned_roles):
        raise HTTPException(status_code=400, detail="Each reference role must be 1 to 80 characters.")

    style = validate_style(style)
    tone = validate_tone(tone)
    quality = validate_quality(quality)
    contents_list: list[bytes] = []
    for file in files:
        if file.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail="Invalid image type.")
        contents = await file.read()
        if len(contents) > MAX_IMAGE_SIZE:
            raise HTTPException(status_code=400, detail="Image too large (max 10MB).")
        _validate_image_bytes(contents)
        contents_list.append(contents)

    preset = preset_mgr.get_preset(preset_id) if preset_id else None
    result = await run_in_threadpool(
        deps.prompt_generator.generate_blended_prompts,
        contents_list,
        cleaned_roles,
        style or (preset.get("style", "") if preset else ""),
        tone or (preset.get("tone", "") if preset else ""),
        quality or (preset.get("quality", "high") if preset else "high"),
        preset.get("positive_suffix", "") if preset else "",
        preset.get("negative_suffix", "") if preset else "",
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "Prompt generation failed."))

    history_id = None
    if save_history:
        history_id = hist.save_history(
            positive=result["positive"],
            negative=result["negative"],
            image_name=", ".join(file.filename or "[image]" for file in files),
            style=style,
            tone=tone,
            quality=quality,
            provider=str(result.get("provider") or ""),
            model=str(result.get("model") or ""),
        )
    data: dict = {"positive": result["positive"], "negative": result["negative"], "roles": cleaned_roles}
    for key in ("provider", "model"):
        if result.get(key):
            data[key] = result[key]
    response: dict = {"success": True, "data": data}
    if history_id is not None:
        response["history_id"] = history_id
    return response


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

    cached, cache_identity = _cache_lookup(None, description, eff_style, eff_tone, eff_quality)
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
            result.setdefault("provider", cache_identity[0])
            result.setdefault("model", cache_identity[1])
            result_identity = _result_identity(result, cache_identity)
            deps.llm_cache.set(
                None,
                description,
                eff_style,
                eff_tone,
                eff_quality,
                result,
                provider=result_identity[0],
                model=result_identity[1],
            )

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
            provider=str(result.get("provider") or ""),
            model=str(result.get("model") or ""),
        )

    data = {"positive": result["positive"], "negative": result["negative"]}
    for key in ("provider", "model"):
        if result.get(key):
            data[key] = result[key]
    response = {"success": True, "data": data}
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
        provider=str(result.get("provider") or ""),
        model=str(result.get("model") or ""),
    )

    return {
        "success": True,
        "data": {
            "positive": result["positive"],
            "negative": result["negative"],
            "changes": result.get("changes", ""),
            "provider": result.get("provider", ""),
            "model": result.get("model", ""),
        },
        "history_id": history_id,
    }
