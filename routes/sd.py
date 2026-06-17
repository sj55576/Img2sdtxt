"""Stable Diffusion endpoints."""

import asyncio
import base64
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from config import ALLOWED_IMAGE_TYPES, MAX_IMAGE_SIZE
from deps import sd_client, _as_int, _as_float, _validate_image_bytes

logger = logging.getLogger("img2sdtxt.sd")

router = APIRouter(prefix="/api/sd", tags=["sd"])


@router.get("/status")
async def sd_status():
    available = await run_in_threadpool(sd_client.is_available)
    model = ""
    samplers = []
    models = []
    upscalers = []
    loras = []
    if available:
        try:
            model, samplers, models, upscalers, loras = await asyncio.gather(
                run_in_threadpool(sd_client.get_current_model),
                run_in_threadpool(sd_client.get_samplers),
                run_in_threadpool(sd_client.get_model_list),
                run_in_threadpool(sd_client.get_upscalers),
                run_in_threadpool(sd_client.get_loras),
            )
        except Exception:
            pass
    return {
        "available": available,
        "model": model,
        "samplers": samplers,
        "models": models,
        "upscalers": upscalers,
        "loras": loras,
    }


@router.get("/progress")
def sd_progress():
    """Return SD WebUI generation progress; no exception if SD is unreachable."""
    data = sd_client.get_progress()
    if data is None:
        return {"available": False, "progress": 0.0, "eta_relative": 0.0, "state": {}}
    return {
        "available": True,
        "progress": float(data.get("progress", 0.0)),
        "eta_relative": float(data.get("eta_relative", 0.0)),
        "state": data.get("state", {}),
    }


@router.websocket("/progress/ws")
async def sd_progress_ws(websocket: WebSocket):
    """WebSocket endpoint for real-time SD generation progress.
    Pushes progress data every 500ms until the client disconnects."""
    await websocket.accept()
    logger.info("WebSocket progress client connected")
    try:
        while True:
            data = await run_in_threadpool(sd_client.get_progress)
            if data is None:
                msg = {"available": False, "progress": 0.0, "eta_relative": 0.0, "state": {}}
            else:
                msg = {
                    "available": True,
                    "progress": float(data.get("progress", 0.0)),
                    "eta_relative": float(data.get("eta_relative", 0.0)),
                    "state": data.get("state", {}),
                }
            await websocket.send_json(msg)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        logger.info("WebSocket progress client disconnected")
    except Exception:
        logger.debug("WebSocket progress connection closed")


@router.get("/loras")
def sd_loras_list():
    try:
        loras = sd_client.get_loras()
        return {"success": True, "loras": loras}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/upscalers")
def sd_upscalers():
    try:
        upscalers = sd_client.get_upscalers()
        return {"success": True, "upscalers": upscalers}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/models")
def sd_models():
    try:
        models = sd_client.get_models()
        return {"success": True, "models": [m.get("model_name", m.get("title", "")) for m in models]}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/generate")
async def sd_generate(request_data: dict):
    positive = request_data.get("positive", "").strip()
    negative = request_data.get("negative", "").strip()
    if not positive:
        raise HTTPException(status_code=400, detail="Positive prompt is required.")

    width = _as_int(request_data, "width", 512)
    height = _as_int(request_data, "height", 512)
    steps = _as_int(request_data, "steps", 20)
    cfg_scale = _as_float(request_data, "cfg_scale", 7.0)
    sampler = request_data.get("sampler", "Euler a")
    seed = _as_int(request_data, "seed", -1)
    batch_size = min(_as_int(request_data, "batch_size", 1), 4)
    model = request_data.get("model", "")
    loras = request_data.get("loras", "")
    enable_hr = bool(request_data.get("enable_hr", False))
    hr_scale = _as_float(request_data, "hr_scale", 2.0)
    hr_upscaler = request_data.get("hr_upscaler", "R-ESRGAN 4x+")
    hr_second_pass_steps = _as_int(request_data, "hr_second_pass_steps", 0)
    hr_denoising_strength = _as_float(request_data, "hr_denoising_strength", 0.7)

    try:
        images = await run_in_threadpool(
            sd_client.txt2img,
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
            hr_denoising_strength=hr_denoising_strength,
        )

        saved_files = await run_in_threadpool(
            sd_client.save_images,
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
        )

        return {
            "success": True,
            "images": images,
            "count": len(images),
            "saved_files": saved_files,
        }
    except ConnectionError:
        raise HTTPException(status_code=503, detail="Stable Diffusion API is not available.")
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Generation timed out.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/img2img")
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

    _validate_image_bytes(contents)

    init_image = base64.b64encode(contents).decode("utf-8")

    try:
        images = await run_in_threadpool(
            sd_client.img2img,
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
            hr_denoising_strength=hr_denoising_strength,
        )

        saved_files = await run_in_threadpool(
            sd_client.save_images,
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
            denoising_strength=denoising_strength,
        )

        return {
            "success": True,
            "images": images,
            "count": len(images),
            "saved_files": saved_files,
        }
    except ConnectionError:
        raise HTTPException(status_code=503, detail="Stable Diffusion API is not available.")
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Generation timed out.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/inpaint")
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

    _validate_image_bytes(contents)

    init_image = base64.b64encode(contents).decode("utf-8")

    try:
        images = await run_in_threadpool(
            sd_client.inpaint,
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
            loras=loras,
        )

        saved_files = await run_in_threadpool(
            sd_client.save_images,
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
            denoising_strength=denoising_strength,
        )

        return {
            "success": True,
            "images": images,
            "count": len(images),
            "saved_files": saved_files,
        }
    except ConnectionError:
        raise HTTPException(status_code=503, detail="Stable Diffusion API is not available.")
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Generation timed out.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-multi-model")
async def sd_generate_multi_model(request_data: dict):
    models = request_data.get("models", [])
    if not models:
        raise HTTPException(status_code=400, detail="At least one model is required.")

    positive = request_data.get("positive", "").strip()
    if not positive:
        raise HTTPException(status_code=400, detail="Positive prompt is required.")

    negative = request_data.get("negative", "").strip()
    width = _as_int(request_data, "width", 512)
    height = _as_int(request_data, "height", 512)
    steps = _as_int(request_data, "steps", 20)
    cfg_scale = _as_float(request_data, "cfg_scale", 7.0)
    sampler = request_data.get("sampler", "Euler a")
    seed = _as_int(request_data, "seed", -1)
    batch_size = min(_as_int(request_data, "batch_size", 1), 4)
    loras = request_data.get("loras", "")
    enable_hr = bool(request_data.get("enable_hr", False))
    hr_scale = _as_float(request_data, "hr_scale", 2.0)
    hr_upscaler = request_data.get("hr_upscaler", "R-ESRGAN 4x+")
    hr_second_pass_steps = _as_int(request_data, "hr_second_pass_steps", 0)
    hr_denoising_strength = _as_float(request_data, "hr_denoising_strength", 0.7)

    results = []
    for model in models:
        try:
            images = await run_in_threadpool(
                sd_client.txt2img,
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
                hr_denoising_strength=hr_denoising_strength,
            )
            saved_files = await run_in_threadpool(
                sd_client.save_images,
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
            )
            results.append({
                "model": model,
                "success": True,
                "images": images,
                "count": len(images),
                "saved_files": saved_files,
            })
        except Exception as e:
            results.append({
                "model": model,
                "success": False,
                "error": str(e),
            })

    return {"success": True, "results": results, "total_models": len(models)}
