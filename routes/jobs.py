"""Job queue endpoints for async generation."""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from deps import sd_client
from job_queue import JobStatus, job_queue, register_job_handler

logger = logging.getLogger("img2sdtxt.jobs")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@register_job_handler("txt2img")
async def handle_txt2img(job, update_progress):
    p = job.params
    await update_progress(0.05)

    images = await run_in_threadpool(
        sd_client.txt2img,
        positive=p["positive"],
        negative=p.get("negative", ""),
        width=p.get("width", 512),
        height=p.get("height", 512),
        steps=p.get("steps", 20),
        cfg_scale=p.get("cfg_scale", 7.0),
        sampler=p.get("sampler", "Euler a"),
        seed=p.get("seed", -1),
        batch_size=min(p.get("batch_size", 1), 4),
        model=p.get("model", ""),
        loras=p.get("loras", ""),
        enable_hr=p.get("enable_hr", False),
        hr_scale=p.get("hr_scale", 2.0),
        hr_upscaler=p.get("hr_upscaler", "R-ESRGAN 4x+"),
        hr_second_pass_steps=p.get("hr_second_pass_steps", 0),
        hr_denoising_strength=p.get("hr_denoising_strength", 0.7),
    )
    await update_progress(0.8)

    saved_files = await run_in_threadpool(
        sd_client.save_images,
        images=images,
        positive=p["positive"],
        negative=p.get("negative", ""),
        width=p.get("width", 512),
        height=p.get("height", 512),
        steps=p.get("steps", 20),
        cfg_scale=p.get("cfg_scale", 7.0),
        sampler=p.get("sampler", "Euler a"),
        seed=p.get("seed", -1),
        model=p.get("model", ""),
        loras=p.get("loras", ""),
    )
    await update_progress(1.0)

    return {
        "images": images,
        "count": len(images),
        "saved_files": saved_files,
    }


@register_job_handler("multi_model")
async def handle_multi_model(job, update_progress):
    p = job.params
    models = p.get("models", [])
    if not models:
        raise ValueError("No models specified")

    results = []
    for i, model in enumerate(models):
        await update_progress(i / len(models))
        try:
            images = await run_in_threadpool(
                sd_client.txt2img,
                positive=p["positive"],
                negative=p.get("negative", ""),
                width=p.get("width", 512),
                height=p.get("height", 512),
                steps=p.get("steps", 20),
                cfg_scale=p.get("cfg_scale", 7.0),
                sampler=p.get("sampler", "Euler a"),
                seed=p.get("seed", -1),
                batch_size=min(p.get("batch_size", 1), 4),
                model=model,
                loras=p.get("loras", ""),
                enable_hr=p.get("enable_hr", False),
                hr_scale=p.get("hr_scale", 2.0),
                hr_upscaler=p.get("hr_upscaler", "R-ESRGAN 4x+"),
                hr_second_pass_steps=p.get("hr_second_pass_steps", 0),
                hr_denoising_strength=p.get("hr_denoising_strength", 0.7),
            )
            saved_files = await run_in_threadpool(
                sd_client.save_images,
                images=images,
                positive=p["positive"],
                negative=p.get("negative", ""),
                width=p.get("width", 512),
                height=p.get("height", 512),
                steps=p.get("steps", 20),
                cfg_scale=p.get("cfg_scale", 7.0),
                sampler=p.get("sampler", "Euler a"),
                seed=p.get("seed", -1),
                model=model,
                loras=p.get("loras", ""),
            )
            results.append(
                {
                    "model": model,
                    "success": True,
                    "images": images,
                    "count": len(images),
                    "saved_files": saved_files,
                }
            )
        except Exception as e:
            results.append({"model": model, "success": False, "error": str(e)})

    return {"results": results, "total_models": len(models)}


# ------------------------------------------------------------------ #
# REST endpoints
# ------------------------------------------------------------------ #


def _clamp_priority(raw_priority: Any) -> int:
    if not isinstance(raw_priority, int) or isinstance(raw_priority, bool):
        raise HTTPException(status_code=400, detail="priority must be an integer")
    return max(-10, min(10, raw_priority))


@router.post("/submit")
async def submit_job(request_data: dict):
    job_type = request_data.get("job_type", "")
    params = request_data.get("params", {})
    priority = _clamp_priority(request_data.get("priority", 0))

    if not job_type:
        raise HTTPException(status_code=400, detail="job_type is required")
    if job_type not in ("txt2img", "multi_model"):
        raise HTTPException(status_code=400, detail=f"Unknown job_type: {job_type}")

    if job_type == "txt2img" and not params.get("positive", "").strip():
        raise HTTPException(status_code=400, detail="positive prompt is required")
    if job_type == "multi_model" and not params.get("models"):
        raise HTTPException(status_code=400, detail="models list is required")

    job = await job_queue.submit(job_type, params, priority=priority)
    return {"success": True, "job": job_queue.job_info(job)}


@router.get("/queue/stats")
async def queue_stats():
    return {"success": True, "stats": job_queue.stats()}


@router.get("/{job_id}")
async def get_job(job_id: str):
    job = job_queue.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "job": job_queue.job_info(job)}


@router.get("")
async def list_jobs(limit: int = 20, status: str = ""):
    jobs = job_queue.list_jobs(limit=limit, status=status or None)
    return {"success": True, "jobs": jobs}


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str):
    cancelled = await job_queue.cancel_job(job_id)
    if not cancelled:
        raise HTTPException(status_code=400, detail="Cannot cancel job (not found or already finished)")
    return {"success": True}


@router.post("/{job_id}/priority")
async def set_job_priority(job_id: str, request_data: dict):
    priority = _clamp_priority(request_data.get("priority"))
    success = await job_queue.set_priority(job_id, priority)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot set priority (job not found or not pending)")
    job = job_queue.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": True, "job": job_queue.job_info(job)}


# ------------------------------------------------------------------ #
# WebSocket for real-time job updates
# ------------------------------------------------------------------ #


@router.websocket("/{job_id}/ws")
async def job_ws(websocket: WebSocket, job_id: str):
    job = job_queue.get_job(job_id)
    if job is None:
        await websocket.close(code=4004)
        return

    await websocket.accept()
    logger.info("WebSocket job subscriber connected (job=%s)", job_id)

    sub_queue = await job_queue.subscribe(job_id)

    # Send current state immediately
    await websocket.send_json(job.to_dict())

    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        await websocket.close()
        return

    try:
        while True:
            try:
                msg = await asyncio.wait_for(sub_queue.get(), timeout=30.0)
                await websocket.send_json(msg)
                if msg.get("status") in ("completed", "failed", "cancelled"):
                    break
            except asyncio.TimeoutError:
                await websocket.send_json({"heartbeat": True})
    except WebSocketDisconnect:
        logger.info("WebSocket job subscriber disconnected (job=%s)", job_id)
    finally:
        job_queue.unsubscribe(job_id, sub_queue)
