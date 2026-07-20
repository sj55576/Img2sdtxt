"""プロンプト比較 / A/Bテスト エンドポイント。"""

import json
import logging
import random
from typing import Any, Dict, List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

import deps
import history as hist
from config import ALLOWED_IMAGE_TYPES, MAX_IMAGE_SIZE
from deps import _validate_image_bytes
from models import ABGenerateRequest, ABVoteRequest

logger = logging.getLogger("img2sdtxt.compare")

router = APIRouter(prefix="/api", tags=["compare"])

MIN_VARIANTS = 2
MAX_VARIANTS = 4


# ------------------------------------------------------------------ #
# 複数プロンプト比較（同一画像・複数のスタイル/トーン/クオリティ）
# ------------------------------------------------------------------ #


@router.post("/generate-prompts-compare")
async def generate_prompts_compare(
    file: UploadFile = File(...),
    variants: str = Form(...),
    save_history: bool = Form(True),
):
    try:
        parsed_variants = json.loads(variants)
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid variants JSON: {e}")

    if not isinstance(parsed_variants, list) or not all(isinstance(v, dict) for v in parsed_variants):
        raise HTTPException(status_code=400, detail="variants must be a JSON array of objects.")

    if not (MIN_VARIANTS <= len(parsed_variants) <= MAX_VARIANTS):
        raise HTTPException(
            status_code=400, detail=f"variants must contain between {MIN_VARIANTS} and {MAX_VARIANTS} items."
        )

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid image type.")

    contents = await file.read()
    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image too large (max 10MB).")

    _validate_image_bytes(contents)

    _prov = deps.llm_client.provider_name
    _mdl = deps.llm_client.model

    results: List[Dict[str, Any]] = []
    for variant in parsed_variants:
        style = str(variant.get("style", ""))
        tone = str(variant.get("tone", ""))
        quality = str(variant.get("quality", "high"))

        try:
            cached = deps.llm_cache.get(contents, None, style, tone, quality, provider=_prov, model=_mdl)
            if cached is not None:
                result = cached
            else:
                result = await run_in_threadpool(
                    deps.prompt_generator.generate_prompts,
                    contents,
                    style=style,
                    tone=tone,
                    quality=quality,
                )
                if result.get("status") == "success":
                    deps.llm_cache.set(contents, None, style, tone, quality, result, provider=_prov, model=_mdl)

            if result.get("status") == "error":
                results.append(
                    {
                        "style": style,
                        "tone": tone,
                        "quality": quality,
                        "success": False,
                        "error": result.get("error", "unknown error"),
                    }
                )
                continue

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

            results.append(
                {
                    "style": style,
                    "tone": tone,
                    "quality": quality,
                    "success": True,
                    "positive": result["positive"],
                    "negative": result["negative"],
                    "history_id": history_id,
                }
            )
        except Exception as e:
            logger.error("generate_prompts_compare variant error: %s", str(e))
            results.append(
                {
                    "style": style,
                    "tone": tone,
                    "quality": quality,
                    "success": False,
                    "error": str(e),
                }
            )

    return {"success": True, "results": results}


# ------------------------------------------------------------------ #
# A/B テスト（画像生成の2案比較）
# ------------------------------------------------------------------ #


@router.post("/compare/ab-generate")
async def ab_generate(request: ABGenerateRequest):
    seed = request.seed
    if seed == -1:
        seed = random.randint(0, 2**31 - 1)

    config_a = request.config_a
    config_b = request.config_b

    try:
        images_a = await run_in_threadpool(
            deps.sd_client.txt2img,
            positive=config_a.positive,
            negative=config_a.negative,
            width=config_a.width,
            height=config_a.height,
            steps=config_a.steps,
            cfg_scale=config_a.cfg_scale,
            sampler=config_a.sampler,
            seed=seed,
        )
        images_b = await run_in_threadpool(
            deps.sd_client.txt2img,
            positive=config_b.positive,
            negative=config_b.negative,
            width=config_b.width,
            height=config_b.height,
            steps=config_b.steps,
            cfg_scale=config_b.cfg_scale,
            sampler=config_b.sampler,
            seed=seed,
        )
    except ConnectionError:
        raise HTTPException(status_code=502, detail="Stable Diffusion API is not available.")
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Generation timed out.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    config_a_dict = config_a.model_dump()
    config_b_dict = config_b.model_dump()
    config_a_dict["seed"] = seed
    config_b_dict["seed"] = seed

    comparison_id = hist.save_ab_comparison(config_a_dict, config_b_dict)

    return {
        "success": True,
        "comparison_id": comparison_id,
        "seed": seed,
        "a": {"images": images_a},
        "b": {"images": images_b},
    }


@router.post("/compare/ab/{comparison_id}/vote")
def ab_vote(comparison_id: int, request: ABVoteRequest):
    if request.winner not in ("a", "b"):
        raise HTTPException(status_code=400, detail="winner must be 'a' or 'b'.")

    ok = hist.set_ab_winner(comparison_id, request.winner, request.note)
    if not ok:
        raise HTTPException(status_code=404, detail="Comparison not found.")

    return {"success": True}


@router.get("/compare/ab-history")
def ab_history(limit: int = 50):
    comparisons = hist.get_ab_comparisons(limit=limit)
    return {"success": True, "comparisons": comparisons}
