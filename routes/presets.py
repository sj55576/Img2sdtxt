"""Preset management endpoints."""

from fastapi import APIRouter, HTTPException

import presets as preset_mgr
from models import PresetCreateRequest

router = APIRouter(prefix="/api", tags=["presets"])


@router.get("/presets")
def get_presets():
    return {"success": True, "presets": preset_mgr.get_all_presets()}


@router.post("/presets")
def create_preset(preset: PresetCreateRequest):
    try:
        new_preset = preset_mgr.add_preset(preset.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"success": True, "preset": new_preset}


@router.delete("/presets/{preset_id}")
def delete_preset(preset_id: str):
    deleted = preset_mgr.delete_preset(preset_id)
    if not deleted:
        raise HTTPException(status_code=400, detail="Cannot delete default preset or not found.")
    return {"success": True}
